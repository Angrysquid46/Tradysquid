from __future__ import annotations

import json
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


def _open(db, trade_id, *, bot="BLACKTIDE", generation=1, entry_bankroll, opened_at="2026-08-24T09:00:00"):
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
    with pytest.raises(ValueError, match="not authoritative"):
        _open(db, "t2", generation=2, entry_bankroll=1000)


def test_record_trade_open_rejects_generation_jump_and_fake_bankroll(db):
    with pytest.raises(ValueError, match="not authoritative"):
        _open(db, "jump", generation=999, entry_bankroll=1000)
    with pytest.raises(ValueError, match="referee bankroll"):
        _open(db, "fake", generation=1, entry_bankroll=5000)


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
    assert sb.total_pnl(db, "BLACKTIDE") == pytest.approx(50.0)


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
        sb.record_generation_event(db, bot="BLACKTIDE", generation=1, event="WHATEVER")


def test_generation_transitions_are_sequential_and_referee_enforced(db):
    with pytest.raises(ValueError, match="positive-bankroll bust"):
        sb.record_generation_event(db, bot="BLACKTIDE", generation=1, event="BUSTED")
    sb.record_generation_event(
        db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1001,
    )
    with pytest.raises(ValueError, match="duplicate"):
        sb.record_generation_event(
            db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1001,
        )
    with pytest.raises(ValueError, match="advance exactly one"):
        sb.record_generation_event(db, bot="BLACKTIDE", generation=999, event="STARTED")
    sb.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")
    with pytest.raises(ValueError, match="advance exactly one"):
        sb.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")


def test_generation_transition_rejected_while_position_open(db):
    _open(db, "open", entry_bankroll=1000)
    with pytest.raises(ValueError, match="position is open"):
        sb.record_generation_event(
            db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1001,
        )


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
    snapshot = sb.scoreboard_snapshot(five_trade_generation, "BLACKTIDE")
    assert set(snapshot.keys()) == sb.SCOREBOARD_SNAPSHOT_KEYS


def test_summary_snapshot_stays_compact_while_position_api_exposes_facts(db):
    _open(db, "secret-live", entry_bankroll=1000)
    snapshot = sb.scoreboard_snapshot(db, "BLACKTIDE")
    assert snapshot["current_position_status"] == "OPEN"
    serialized = json.dumps(snapshot)
    assert "SPY260824C00500000" not in serialized
    assert "entry_price" not in serialized
    position = sb.current_position_status(db, "BLACKTIDE")
    assert position["contract_symbol"] == "SPY260824C00500000"
    assert position["entry_price"] == 1.0


def test_open_position_marks_use_bid_and_track_high_low(db):
    _open(db, "marked", entry_bankroll=1000)
    assert sb.record_trade_mark(
        db, trade_id="marked", bid=0.90,
        marked_at="2026-08-24T09:01:00-05:00",
    ) is True
    assert sb.record_trade_mark(
        db, trade_id="marked", bid=1.15,
        marked_at="2026-08-24T09:02:00-05:00",
    ) is True
    assert sb.record_trade_mark(
        db, trade_id="marked", bid=0.80,
        marked_at="2026-08-24T09:03:00-05:00",
    ) is True
    position = sb.current_position_status(db, "BLACKTIDE")
    assert position["last_mark_price"] == pytest.approx(0.80)
    assert position["mark_high_price"] == pytest.approx(1.15)
    assert position["mark_low_price"] == pytest.approx(0.80)
    assert position["last_marked_at"] == "2026-08-24T09:03:00-05:00"


def test_late_mark_cannot_mutate_closed_trade(db):
    _open(db, "closed", entry_bankroll=1000)
    _close(db, "closed", 10)
    assert sb.record_trade_mark(
        db, trade_id="closed", bid=9.99,
        marked_at="2026-08-24T09:06:00-05:00",
    ) is False
    row = db.execute(
        "SELECT last_mark_price FROM official_trades WHERE trade_id='closed'"
    ).fetchone()
    assert row["last_mark_price"] is None


def test_position_mark_rejects_nonpositive_bid(db):
    _open(db, "marked", entry_bankroll=1000)
    with pytest.raises(ValueError, match="positive"):
        sb.record_trade_mark(
            db, trade_id="marked", bid=0,
            marked_at="2026-08-24T09:01:00-05:00",
        )


def test_trade_count_and_total_pnl(five_trade_generation):
    assert sb.trade_count(five_trade_generation, "BLACKTIDE") == 5
    assert sb.total_pnl(five_trade_generation, "BLACKTIDE") == pytest.approx(300)


def test_current_bankroll(five_trade_generation):
    assert sb.current_bankroll(five_trade_generation, "BLACKTIDE") == pytest.approx(1300)


def test_win_rate(five_trade_generation):
    assert sb.win_rate(five_trade_generation, "BLACKTIDE") == pytest.approx(0.6)


def test_profit_factor(five_trade_generation):
    assert sb.profit_factor(five_trade_generation, "BLACKTIDE") == pytest.approx(380 / 80)


def test_expectancy(five_trade_generation):
    assert sb.expectancy(five_trade_generation, "BLACKTIDE") == pytest.approx(60)


def test_average_and_largest_winner_loser(five_trade_generation):
    assert sb.average_winner(five_trade_generation, "BLACKTIDE") == pytest.approx(380 / 3)
    assert sb.average_loser(five_trade_generation, "BLACKTIDE") == pytest.approx(-40)
    assert sb.largest_winner(five_trade_generation, "BLACKTIDE") == pytest.approx(200)
    assert sb.largest_loser(five_trade_generation, "BLACKTIDE") == pytest.approx(-50)


def test_max_and_current_drawdown(five_trade_generation):
    assert sb.max_drawdown(five_trade_generation, "BLACKTIDE") == pytest.approx(-50)
    assert sb.current_drawdown(five_trade_generation, "BLACKTIDE") == pytest.approx(0)


def test_current_streak(five_trade_generation):
    streak = sb.current_streak(five_trade_generation, "BLACKTIDE")
    assert streak == {"type": "WIN", "length": 1}


def test_profit_factor_none_when_no_losses(db):
    _open(db, "t1", entry_bankroll=1000)
    _close(db, "t1", 100)
    assert sb.profit_factor(db, "BLACKTIDE") is None


def test_metrics_none_for_bot_with_no_trades(db):
    assert sb.trade_count(db, "BLACKTIDE") == 0
    assert sb.win_rate(db, "BLACKTIDE") is None
    assert sb.expectancy(db, "BLACKTIDE") is None
    assert sb.max_drawdown(db, "BLACKTIDE") is None
    assert sb.current_streak(db, "BLACKTIDE") is None


# --- generation / bust behavior -----------------------------------------------

def test_bust_and_new_generation_resets_bankroll_but_keeps_lifetime_history(five_trade_generation):
    db = five_trade_generation
    sb.record_generation_event(db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1301)
    sb.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")
    _open(db, "t5", bot="BLACKTIDE", generation=2, entry_bankroll=1000, opened_at="2026-08-24T10:00:00")
    _close(db, "t5", -200, closed_at="2026-08-24T10:05:00")

    assert sb.current_generation(db, "BLACKTIDE") == 2
    assert sb.current_bankroll(db, "BLACKTIDE") == pytest.approx(800)  # 1000 - 200, not 1300 - 200
    assert sb.lifetime_pnl(db, "BLACKTIDE") == pytest.approx(100)      # 300 - 200
    assert sb.bust_count(db, "BLACKTIDE") == 1


def test_new_generation_dashboard_curve_and_drawdown_exclude_prior_generation(five_trade_generation):
    db = five_trade_generation
    sb.record_generation_event(db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1301)
    sb.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")

    empty_curve = sb.bankroll_history(db, "BLACKTIDE", generation=2)
    assert empty_curve == [{"at": None, "bankroll": 1000.0, "generation": 2}]
    assert sb.scoreboard_snapshot(db, "BLACKTIDE")["current_drawdown"] is None

    _open(db, "g2-loss", generation=2, entry_bankroll=1000, opened_at="2026-08-24T10:00:00")
    _close(db, "g2-loss", -200, closed_at="2026-08-24T10:05:00")
    curve = sb.bankroll_history(db, "BLACKTIDE", generation=2)
    assert [round(point["bankroll"]) for point in curve] == [1000, 1000, 800]
    assert {point["generation"] for point in curve} == {2}
    assert sb.scoreboard_snapshot(db, "BLACKTIDE")["current_drawdown"] == pytest.approx(-200)


def test_best_worst_generation_and_generation_over_generation_improvement(five_trade_generation):
    db = five_trade_generation
    sb.record_generation_event(db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1301)
    sb.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")
    _open(db, "t5", bot="BLACKTIDE", generation=2, entry_bankroll=1000, opened_at="2026-08-24T10:00:00")
    _close(db, "t5", -200, closed_at="2026-08-24T10:05:00")

    assert sb.best_generation(db, "BLACKTIDE") == 1
    assert sb.worst_generation(db, "BLACKTIDE") == 2
    assert sb.generation_over_generation_improvement(db, "BLACKTIDE") == pytest.approx(-200 - 300)


def test_generation_over_generation_improvement_none_with_only_one_generation(five_trade_generation):
    assert sb.generation_over_generation_improvement(five_trade_generation, "BLACKTIDE") is None


# --- current_position_status / snapshot / leader ------------------------------

def test_current_position_status_reflects_the_open_trade(db):
    assert sb.current_position_status(db, "BLACKTIDE") is None
    _open(db, "t1", entry_bankroll=1000)
    status = sb.current_position_status(db, "BLACKTIDE")
    assert status["trade_id"] == "t1"
    assert status["closed_at"] is None


def test_scoreboard_snapshot_bundles_every_metric(five_trade_generation):
    snapshot = sb.scoreboard_snapshot(five_trade_generation, "BLACKTIDE")
    assert snapshot["bot"] == "BLACKTIDE"
    assert snapshot["generation"] == 1
    assert snapshot["current_bankroll"] == pytest.approx(1300)
    assert snapshot["lifetime_pnl"] == pytest.approx(300)
    assert snapshot["win_rate"] == pytest.approx(0.6)
    assert snapshot["current_position_status"] == "FLAT"


def test_current_leader_none_when_no_trades_exist(db):
    assert sb.current_leader(db) is None


def test_current_leader_picks_the_higher_lifetime_pnl(five_trade_generation):
    assert sb.current_leader(five_trade_generation) == "BLACKTIDE"


def test_current_leader_none_on_a_tie(db):
    _open(db, "t1", bot="BLACKTIDE", entry_bankroll=1000)
    _close(db, "t1", 100)
    _open(db, "t2", bot="RIPTIDE", entry_bankroll=1000)
    _close(db, "t2", 100)
    assert sb.current_leader(db) is None


# --- recent_closed_trades / bankroll_history -----------------------------------

def test_recent_closed_trades_outcome_filter_separates_wins_and_losses(five_trade_generation):
    wins = sb.recent_closed_trades(five_trade_generation, "BLACKTIDE", outcome="WIN")
    losses = sb.recent_closed_trades(five_trade_generation, "BLACKTIDE", outcome="LOSS")
    assert [round(t["pnl_usd"]) for t in wins] == [80, 200, 100]
    assert [round(t["pnl_usd"]) for t in losses] == [-30, -50]
    assert all(t["outcome"] == "WIN" for t in wins)
    assert all(t["outcome"] == "LOSS" for t in losses)


def test_recent_closed_trades_outcome_filter_respects_limit(five_trade_generation):
    wins = sb.recent_closed_trades(five_trade_generation, "BLACKTIDE", limit=1, outcome="WIN")
    assert len(wins) == 1
    assert round(wins[0]["pnl_usd"]) == 80


def test_bankroll_history_matches_the_hand_calculated_equity_curve(five_trade_generation):
    points = sb.bankroll_history(five_trade_generation, "BLACKTIDE")
    values = [round(p["bankroll"]) for p in points]
    assert values == [1000, 1000, 1100, 1100, 1050, 1050, 1250, 1250, 1220, 1220, 1300]


def test_bankroll_history_on_an_empty_bot_is_just_the_starting_point(db):
    points = sb.bankroll_history(db, "BLACKTIDE")
    assert points == [{"at": None, "bankroll": sb.STARTING_BANKROLL_USD, "generation": 1}]
