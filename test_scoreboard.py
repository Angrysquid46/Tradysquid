from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import scoreboard as sb


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(sb, "DB_PATH", Path(tempfile.mkdtemp()) / "scoreboard.db")
    connection = sb.connect_db()
    yield connection
    connection.close()


def _open(db, trade_id, *, bot="AXIOM", generation=1, entry_bankroll, opened_at="2026-08-24T09:00:00"):
    sb.record_trade_open(
        db, trade_id=trade_id, bot=bot, generation=generation, opened_at=opened_at,
        side="CALL", contract_symbol="SPY260824C00500000", entry_price=1.0,
        contracts=1, entry_bankroll=entry_bankroll,
    )


def _close(db, trade_id, pnl_usd, *, closed_at="2026-08-24T09:05:00"):
    sb.record_trade_close(db, trade_id=trade_id, closed_at=closed_at, exit_price=1.0 + pnl_usd / 100, pnl_usd=pnl_usd)


# --- write-path guards --------------------------------------------------------

def test_record_trade_open_rejects_duplicate_trade_id(db):
    _open(db, "t1", entry_bankroll=1000)
    with pytest.raises(ValueError, match="already recorded"):
        _open(db, "t1", entry_bankroll=1000)


def test_record_trade_open_rejects_second_concurrent_open_trade(db):
    _open(db, "t1", entry_bankroll=1000)
    with pytest.raises(ValueError, match="already has an open trade"):
        _open(db, "t2", entry_bankroll=1000)


def test_record_trade_open_rejects_second_open_trade_in_a_different_generation(db):
    """Phase 14 audit finding: max_open_trades_per_bot is global per bot
    (IMMUTABLE_RULES.json has no generation qualifier) - a bot must not be
    able to hold an open trade in one generation while opening another in
    the next."""
    _open(db, "t1", generation=1, entry_bankroll=1000)
    with pytest.raises(ValueError, match="already has an open trade"):
        _open(db, "t2", generation=2, entry_bankroll=1000)


def test_record_trade_close_rejects_pnl_that_does_not_match_the_math(db):
    """Phase 14 audit finding: the referee must compute P&L itself, not
    trust whatever the calling trader announces."""
    _open(db, "t1", entry_bankroll=1000)  # entry_price=1.0, contracts=1
    with pytest.raises(ValueError, match="does not match"):
        sb.record_trade_close(
            db, trade_id="t1", closed_at="2026-08-24T09:05:00",
            exit_price=1.5, pnl_usd=9999.0,  # real math is (1.5-1.0)*100=50
        )


def test_record_trade_close_stores_the_computed_pnl_not_the_caller_value(db):
    _open(db, "t1", entry_bankroll=1000)  # entry_price=1.0, contracts=1
    sb.record_trade_close(
        db, trade_id="t1", closed_at="2026-08-24T09:05:00",
        exit_price=1.5, pnl_usd=50.0,
    )
    assert sb.total_pnl(db, "AXIOM") == pytest.approx(50.0)


def test_record_trade_open_allows_new_trade_after_prior_one_closes(db):
    _open(db, "t1", entry_bankroll=1000)
    _close(db, "t1", 50)
    _open(db, "t2", entry_bankroll=1050)  # does not raise


def test_record_trade_close_rejects_nonexistent_trade(db):
    with pytest.raises(ValueError, match="never opened"):
        _close(db, "ghost", 10)


def test_record_trade_close_rejects_already_closed_trade(db):
    _open(db, "t1", entry_bankroll=1000)
    _close(db, "t1", 50)
    with pytest.raises(ValueError, match="already closed and immutable"):
        _close(db, "t1", 999)


def test_record_generation_event_rejects_unknown_bot_and_event(db):
    with pytest.raises(ValueError, match="Unknown bot"):
        sb.record_generation_event(db, bot="Nobody", generation=1, event="STARTED")
    with pytest.raises(ValueError, match="Unknown generation event"):
        sb.record_generation_event(db, bot="AXIOM", generation=1, event="WHATEVER")


# --- hand-calculated metrics ---------------------------------------------------

@pytest.fixture
def five_trade_generation(db):
    """entry_bankroll=1000, pnl sequence [+100, -50, +200, -30, +80] ->
    total 300, 3 wins/2 losses, equity curve [1000,1100,1050,1250,1220,1300]."""
    bankroll = 1000.0
    for i, pnl in enumerate([100, -50, 200, -30, 80]):
        _open(db, f"t{i}", entry_bankroll=bankroll, opened_at=f"2026-08-24T09:0{i}:00")
        _close(db, f"t{i}", pnl, closed_at=f"2026-08-24T09:0{i}:30")
        bankroll += pnl
    return db


def test_scoreboard_snapshot_keys_constant_matches_the_real_return_shape(five_trade_generation):
    """rivalry.py's public_score_snapshot schema check trusts this
    constant to match reality - if scoreboard_snapshot()'s shape ever
    changes without updating SCOREBOARD_SNAPSHOT_KEYS, this must fail."""
    snapshot = sb.scoreboard_snapshot(five_trade_generation, "AXIOM")
    assert set(snapshot.keys()) == sb.SCOREBOARD_SNAPSHOT_KEYS


def test_trade_count_and_total_pnl(five_trade_generation):
    assert sb.trade_count(five_trade_generation, "AXIOM") == 5
    assert sb.total_pnl(five_trade_generation, "AXIOM") == pytest.approx(300)


def test_current_bankroll(five_trade_generation):
    assert sb.current_bankroll(five_trade_generation, "AXIOM") == pytest.approx(1300)


def test_win_rate(five_trade_generation):
    assert sb.win_rate(five_trade_generation, "AXIOM") == pytest.approx(0.6)


def test_profit_factor(five_trade_generation):
    assert sb.profit_factor(five_trade_generation, "AXIOM") == pytest.approx(380 / 80)


def test_expectancy(five_trade_generation):
    assert sb.expectancy(five_trade_generation, "AXIOM") == pytest.approx(60)


def test_average_and_largest_winner_loser(five_trade_generation):
    assert sb.average_winner(five_trade_generation, "AXIOM") == pytest.approx(380 / 3)
    assert sb.average_loser(five_trade_generation, "AXIOM") == pytest.approx(-40)
    assert sb.largest_winner(five_trade_generation, "AXIOM") == pytest.approx(200)
    assert sb.largest_loser(five_trade_generation, "AXIOM") == pytest.approx(-50)


def test_max_and_current_drawdown(five_trade_generation):
    assert sb.max_drawdown(five_trade_generation, "AXIOM") == pytest.approx(-50)
    assert sb.current_drawdown(five_trade_generation, "AXIOM") == pytest.approx(0)


def test_current_streak(five_trade_generation):
    streak = sb.current_streak(five_trade_generation, "AXIOM")
    assert streak == {"type": "WIN", "length": 1}


def test_profit_factor_none_when_no_losses(db):
    _open(db, "t1", entry_bankroll=1000)
    _close(db, "t1", 100)
    assert sb.profit_factor(db, "AXIOM") is None


def test_metrics_none_for_bot_with_no_trades(db):
    assert sb.trade_count(db, "BLACKTIDE") == 0
    assert sb.win_rate(db, "BLACKTIDE") is None
    assert sb.expectancy(db, "BLACKTIDE") is None
    assert sb.max_drawdown(db, "BLACKTIDE") is None
    assert sb.current_streak(db, "BLACKTIDE") is None


# --- generation / bust behavior -----------------------------------------------

def test_bust_and_new_generation_resets_bankroll_but_keeps_lifetime_history(five_trade_generation):
    db = five_trade_generation
    sb.record_generation_event(db, bot="AXIOM", generation=1, event="BUSTED")
    sb.record_generation_event(db, bot="AXIOM", generation=2, event="STARTED")
    _open(db, "t5", bot="AXIOM", generation=2, entry_bankroll=1000, opened_at="2026-08-24T10:00:00")
    _close(db, "t5", -200, closed_at="2026-08-24T10:05:00")

    assert sb.current_generation(db, "AXIOM") == 2
    assert sb.current_bankroll(db, "AXIOM") == pytest.approx(800)  # 1000 - 200, not 1300 - 200
    assert sb.lifetime_pnl(db, "AXIOM") == pytest.approx(100)      # 300 - 200
    assert sb.bust_count(db, "AXIOM") == 1


def test_best_worst_generation_and_generation_over_generation_improvement(five_trade_generation):
    db = five_trade_generation
    sb.record_generation_event(db, bot="AXIOM", generation=1, event="BUSTED")
    sb.record_generation_event(db, bot="AXIOM", generation=2, event="STARTED")
    _open(db, "t5", bot="AXIOM", generation=2, entry_bankroll=1000, opened_at="2026-08-24T10:00:00")
    _close(db, "t5", -200, closed_at="2026-08-24T10:05:00")

    assert sb.best_generation(db, "AXIOM") == 1
    assert sb.worst_generation(db, "AXIOM") == 2
    assert sb.generation_over_generation_improvement(db, "AXIOM") == pytest.approx(-200 - 300)


def test_generation_over_generation_improvement_none_with_only_one_generation(five_trade_generation):
    assert sb.generation_over_generation_improvement(five_trade_generation, "AXIOM") is None


# --- current_position_status / snapshot / leader ------------------------------

def test_current_position_status_reflects_the_open_trade(db):
    assert sb.current_position_status(db, "AXIOM") is None
    _open(db, "t1", entry_bankroll=1000)
    status = sb.current_position_status(db, "AXIOM")
    assert status["trade_id"] == "t1"
    assert status["closed_at"] is None


def test_scoreboard_snapshot_bundles_every_metric(five_trade_generation):
    snapshot = sb.scoreboard_snapshot(five_trade_generation, "AXIOM")
    assert snapshot["bot"] == "AXIOM"
    assert snapshot["generation"] == 1
    assert snapshot["current_bankroll"] == pytest.approx(1300)
    assert snapshot["lifetime_pnl"] == pytest.approx(300)
    assert snapshot["win_rate"] == pytest.approx(0.6)
    assert snapshot["current_position_status"] is None


def test_current_leader_none_when_no_trades_exist(db):
    assert sb.current_leader(db) is None


def test_current_leader_picks_the_higher_lifetime_pnl(five_trade_generation):
    assert sb.current_leader(five_trade_generation) == "AXIOM"


def test_current_leader_none_on_a_tie(db):
    _open(db, "t1", bot="AXIOM", entry_bankroll=1000)
    _close(db, "t1", 100)
    _open(db, "t2", bot="BLACKTIDE", entry_bankroll=1000)
    _close(db, "t2", 100)
    assert sb.current_leader(db) is None
