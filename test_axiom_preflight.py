"""Real tests for bots/claude/preflight.py's readiness gate - each check
must independently fail closed, and the gate only reports READY when
every real condition is genuinely met. No check here is allowed to change
state; these tests confirm that too (scoreboard state is untouched by
running the gate)."""

from __future__ import annotations

from datetime import datetime

import market_data
import scoreboard

import bots.claude.preflight as preflight


def _setup_clean_scoreboard(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    scoreboard.connect_db()  # AXIOM's starting snapshot: Gen 1, $1,000, 0 trades, FLAT


def _mock_all_pass(monkeypatch):
    monkeypatch.setattr(preflight, "_git", lambda *a: "abc123")
    monkeypatch.setattr(preflight, "_port_is_free", lambda host, port: True)
    monkeypatch.setattr(market_data, "get_quote", lambda symbol: {"last": 500.0})
    monkeypatch.setattr(market_data, "get_expirations", lambda symbol: [market_data.now_ct().date().isoformat()])
    monkeypatch.setattr(market_data, "market_is_open_now", lambda: (True, market_data.now_ct()))


def test_all_checks_pass_when_everything_is_genuinely_ready(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    assert preflight.main() == 0


def test_fails_on_deploy_drift(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    calls = {"n": 0}

    def _git(*args):
        calls["n"] += 1
        return "aaa111" if "origin/main" not in args else "bbb222"

    monkeypatch.setattr(preflight, "_git", _git)
    assert preflight.main() == 1


def test_fails_when_instance_lock_port_is_taken(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    monkeypatch.setattr(preflight, "_port_is_free", lambda host, port: False)
    assert preflight.main() == 1


def test_fails_on_provider_error(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)

    def _boom(symbol):
        raise market_data.TradierError("down")

    monkeypatch.setattr(market_data, "get_quote", _boom)
    assert preflight.main() == 1


def test_fails_when_no_0dte_expiration_today(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    monkeypatch.setattr(market_data, "get_expirations", lambda symbol: ["2099-01-01"])
    assert preflight.main() == 1


def test_fails_when_axiom_already_has_an_open_trade(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    sb = scoreboard.connect_db()
    scoreboard.record_trade_open(
        sb, trade_id="t1", bot="AXIOM", generation=1,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol="SPY260825C00500000", entry_price=4.0,
        contracts=1, entry_bankroll=1000.0,
    )
    assert preflight.main() == 1


def test_fails_when_axiom_has_prior_trade_history(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    sb = scoreboard.connect_db()
    scoreboard.record_trade_open(
        sb, trade_id="t1", bot="AXIOM", generation=1,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol="SPY260825C00500000", entry_price=4.0,
        contracts=1, entry_bankroll=1000.0,
    )
    scoreboard.record_trade_close(
        sb, trade_id="t1", closed_at="2026-08-25T10:00:00", exit_price=4.5, pnl_usd=50.0,
    )
    assert preflight.main() == 1  # bankroll is $1,050 / 1 trade now, not a fresh start


def test_fails_when_market_is_closed(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    monkeypatch.setattr(market_data, "market_is_open_now", lambda: (False, market_data.now_ct()))
    assert preflight.main() == 1


def test_never_changes_scoreboard_state(tmp_path, monkeypatch):
    _setup_clean_scoreboard(tmp_path, monkeypatch)
    _mock_all_pass(monkeypatch)
    preflight.main()
    sb = scoreboard.connect_db()
    snapshot = scoreboard.scoreboard_snapshot(sb, "AXIOM")
    assert snapshot["generation"] == 1
    assert snapshot["current_bankroll"] == scoreboard.STARTING_BANKROLL_USD
    assert snapshot["trade_count_lifetime"] == 0
