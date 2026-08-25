"""Real test for the bust protocol: bankroll hitting <= 0 must freeze the
generation, write a postmortem, start a fresh generation at $1,000, and
never double-fire for the same generation."""

from __future__ import annotations

import json

import rivalry
import scoreboard

import bots.claude.runtime as runtime
import bots.claude.scheduler as scheduler


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(rivalry, "DB_PATH", tmp_path / "rivalry.db")
    monkeypatch.setattr(runtime, "POSTMORTEM_DIR", tmp_path / "postmortems")
    scheduler.DB_PATH = tmp_path / "axiom.db"
    return scheduler.connect_db()


def _bust_generation_1(sb) -> None:
    scoreboard.record_trade_open(
        sb, trade_id="t1", bot="AXIOM", generation=1,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol="SPY260825C00500000", entry_price=4.0,
        contracts=2, entry_bankroll=1000.0,
    )
    scoreboard.record_trade_close(
        sb, trade_id="t1", closed_at="2026-08-25T10:00:00",
        exit_price=0.0, pnl_usd=-1000.0,
    )


def test_bust_writes_postmortem_and_starts_new_generation(tmp_path, monkeypatch):
    sched_conn = _setup(tmp_path, monkeypatch)
    sb = scoreboard.connect_db()
    _bust_generation_1(sb)

    result = runtime.bust_check_job(sched_conn)

    assert "busted" in result
    assert scoreboard.current_generation(sb, "AXIOM") == 2
    assert scoreboard.current_bankroll(sb, "AXIOM") == 1000.0

    postmortem_path = runtime.POSTMORTEM_DIR / "generation_1.json"
    assert postmortem_path.exists()
    data = json.loads(postmortem_path.read_text(encoding="utf-8"))
    assert data["generation"] == 1
    assert data["total_pnl_usd"] == -1000.0
    assert data["trade_count"] == 1


def test_bust_does_not_double_fire_for_the_same_generation(tmp_path, monkeypatch):
    sched_conn = _setup(tmp_path, monkeypatch)
    sb = scoreboard.connect_db()
    _bust_generation_1(sb)

    first = runtime.bust_check_job(sched_conn)
    second = runtime.bust_check_job(sched_conn)

    assert "busted" in first
    # Generation 2 has a fresh positive bankroll, so the second call
    # correctly finds nothing to bust rather than re-processing
    # generation 1 - the idempotency guard means it's never even
    # re-examined, not that it returns a stale "already handled" verdict.
    assert "no bust" in second
    # Generation never advances past 2 - no double STARTED/BUSTED pair.
    assert scoreboard.current_generation(sb, "AXIOM") == 2
    busted_events = sched_conn.execute(
        "SELECT COUNT(*) FROM engine_state WHERE key=?", ("busted:generation:1",)
    ).fetchone()[0]
    assert busted_events == 1


def test_no_bust_when_bankroll_is_positive(tmp_path, monkeypatch):
    sched_conn = _setup(tmp_path, monkeypatch)
    sb = scoreboard.connect_db()
    scoreboard.record_trade_open(
        sb, trade_id="t1", bot="AXIOM", generation=1,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol="SPY260825C00500000", entry_price=4.0,
        contracts=1, entry_bankroll=1000.0,
    )
    scoreboard.record_trade_close(
        sb, trade_id="t1", closed_at="2026-08-25T10:00:00",
        exit_price=5.0, pnl_usd=100.0,
    )

    result = runtime.bust_check_job(sched_conn)

    assert "no bust" in result
    assert scoreboard.current_generation(sb, "AXIOM") == 1
    assert not (runtime.POSTMORTEM_DIR / "generation_1.json").exists()
