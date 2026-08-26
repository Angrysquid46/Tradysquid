"""Real test for bots/claude/runtime.py's entry_scan_job handling a
provider/budget failure cleanly - found missing during Phase 15 AXIOM
launch-readiness review. Stubs out the signal/contract-selection chain
(covered by their own dedicated tests) to isolate the get_quote failure
path specifically."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import market_data
import scoreboard

import bots.claude.runtime as runtime


class _FakeBars:
    def bars_as_of(self, now, lookback_minutes):
        return [{"close": 100.0, "bar_time": "2026-08-25T10:00:00", "bar_timestamp": 1}]

    def options_as_of(self, now):
        return {"tier": "A", "contracts": []}


@dataclass
class _FakeDecision:
    side: str = "CALL"
    rationale: str = "test"
    contributing_signals: dict = None

    def __post_init__(self):
        if self.contributing_signals is None:
            self.contributing_signals = {"confidence": 0.5}


@dataclass
class _FakeSelected:
    name: str = "trend_continuation"
    decision: _FakeDecision = None
    params: dict = None

    def __post_init__(self):
        if self.decision is None:
            self.decision = _FakeDecision()
        if self.params is None:
            self.params = {"delta_min": 0.35, "delta_max": 0.55, "premium_cap_usd": 450.0}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(runtime.evolution, "DB_PATH", tmp_path / "axiom_evolution.db")
    monkeypatch.setattr(runtime.backtest_lab, "MarketView", lambda symbol: _FakeBars())
    monkeypatch.setattr(runtime.backtest_lab, "compute_features", lambda bars: {})
    monkeypatch.setattr(runtime.signal, "entry_decision", lambda conn, price, features: _FakeSelected())
    monkeypatch.setattr(
        runtime.contract_selection, "select_contract",
        lambda contracts, side, today, params, confidence=0.5: {
            "option_symbol": "SPY260825C00500000", "ask": 4.0, "bid": 3.9, "delta": 0.45,
        },
    )


def test_entry_scan_job_handles_provider_failure_without_raising(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def _boom(symbol, priority=None):
        raise market_data.TradierError("provider down")

    monkeypatch.setattr(runtime.market_data, "get_quote", _boom)

    result = runtime.entry_scan_job(None)

    assert "provider/budget" in result
    sb = scoreboard.connect_db()
    assert scoreboard.current_position_status(sb, "AXIOM") is None  # no trade opened


def test_entry_scan_job_opens_when_safety_quote_available(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime.market_data, "get_quote", lambda symbol, priority=None: {"last": 100.0})
    monkeypatch.setattr(runtime, "_ensure_surface", lambda conn: None)
    monkeypatch.setattr(runtime.discord_surface_manifest, "record_surface_event", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "_post", lambda content: None)
    monkeypatch.setattr(
        runtime.evolution, "record_trade_attribution", lambda conn, **kwargs: None
    )

    result = runtime.entry_scan_job(None)

    assert "opened CALL" in result
    sb = scoreboard.connect_db()
    assert scoreboard.current_position_status(sb, "AXIOM") is not None


# --- restart-recovery drill (Phase 15, mirrors Codex's 15.5 requirement) ---
# "Kill and restart the entering bot once during the position... confirm
# it reconstructs the official position and cannot open another." AXIOM
# has no in-memory position cache - every job re-reads scoreboard.py/
# evolution.py fresh each call, so this proves that guarantee directly:
# nothing here shares Python state between the "open" step and the
# "restarted process monitors it" step except the on-disk DBs themselves.

def test_restart_recovery_position_monitor_finds_the_official_open_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(runtime.evolution, "DB_PATH", tmp_path / "axiom_evolution.db")
    monkeypatch.setattr(runtime.discord_surface_manifest, "DB_PATH", tmp_path / "surfaces.db")
    scheduler_connection = runtime.discord_surface_manifest.connect_db()
    monkeypatch.setattr(runtime, "_post", lambda content: None)

    # Step 1: a trade gets opened - stands in for "a prior AXIOM process
    # opened this, then the process died."
    sb = scoreboard.connect_db()
    scoreboard.record_trade_open(
        sb, trade_id="restart-drill-1", bot="AXIOM", generation=1,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol="SPY260825C00500000", entry_price=4.0,
        contracts=1, entry_bankroll=1000.0,
    )
    evo_conn = runtime.evolution.connect_db()
    runtime.evolution.record_trade_attribution(
        evo_conn, trade_id="restart-drill-1", hypothesis_name="trend_continuation", generation=1
    )
    del sb, evo_conn  # drop every reference - the next calls get their own fresh connections

    # Step 2: "the process restarts" - position_monitor_job is called with
    # zero carried-over state, exactly as a fresh `python -m bots.claude.runtime`
    # process's first cycle would call it. now_ct() is pinned mid-session so
    # this test is deterministic regardless of when it's actually run (real
    # wall-clock time would otherwise hit the force-close floor outside
    # market hours).
    monkeypatch.setattr(runtime.market_data, "now_ct", lambda: datetime(2026, 8, 25, 10, 0, 0))
    monkeypatch.setattr(
        runtime.backtest_lab, "MarketView",
        lambda symbol: type("V", (), {
            "options_as_of": lambda self, now: {
                "tier": "A",
                "contracts": [{"option_symbol": "SPY260825C00500000", "bid": 4.05, "ask": 4.10, "delta": 0.45}],
            }
        })(),
    )
    result = runtime.position_monitor_job(scheduler_connection)
    assert "holding" in result  # small unrealized gain, not at target/stop/time yet

    # Step 3: the still-open position correctly blocks a new entry on the
    # very next scan cycle - proves "cannot open another."
    entry_result = runtime.entry_scan_job(scheduler_connection)
    assert entry_result == "position already open"
