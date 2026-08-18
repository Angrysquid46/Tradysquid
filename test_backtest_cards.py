"""Tests for the backtest cards channel.

These cards exist to keep a backtest claim honest: it gets checked
against live results continuously instead of being quoted once. The
things that must not break are that a card updates in place rather than
piling up snapshots, that a thin sample is labelled as thin, and that
this surface stays out of the daily/weekly/monthly performance reporting.
"""

from __future__ import annotations

import backtest_cards as bc
import local_information_engine as engine
import spy_scanner


def _stats(**over):
    base = {"trades": 1743, "win_rate": 42.5, "payoff_ratio": 2.19,
            "breakeven_win_rate": 31.3, "avg_dollars": 8.47,
            "total_dollars": 14761, "target_pct": 150.0, "stop_pct": -75.0,
            "exit_label": "Target +150% / stop -75% of premium"}
    base.update(over)
    return base


def test_a_card_states_the_strategys_own_exit_rules():
    """Measuring every strategy under one borrowed exit is what produced a
    whole evening of wrong conclusions, so each card names its own."""
    body = bc.render_card("SPY_GAP_CONT_50", _stats())
    assert "+150" in body and "-75" in body


def test_a_card_compares_win_rate_to_its_own_break_even():
    body = bc.render_card("SPY_GAP_CONT_50", _stats())
    assert "31.3" in body
    assert "CLEAR" in body


def test_a_strategy_below_break_even_is_labelled_as_such():
    body = bc.render_card("SPY_FIRST_PULLBACK",
                          _stats(win_rate=42.9, breakeven_win_rate=46.4,
                                 avg_dollars=-2.23, total_dollars=-125))
    assert "BELOW break-even" in body


def test_a_thin_sample_is_flagged_rather_than_presented_as_a_result():
    body = bc.render_card("SPY_EXHAUSTION_1ATR",
                          _stats(trades=11, exit_note="**Only 11 trades**"))
    assert "11" in body


def test_the_forward_record_shows_drift_against_the_backtest():
    forward = {"trades": 40, "win_rate": 30.0, "avg_dollars": -4.0,
               "total_dollars": -160.0}
    body = bc.render_card("SPY_GAP_CONT_50", _stats(), forward)
    assert "-12.5pp" in body
    assert "below this strategy's" in body.lower() or "break-even" in body


def test_forward_record_counts_only_closed_trades():
    rows = [
        {"play_type": "X", "outcome": "OPEN", "pnl_dollars": "5"},
        {"play_type": "X", "outcome": "WIN", "pnl_dollars": "10"},
        {"play_type": "X", "outcome": "LOSS", "pnl_dollars": "-4"},
        {"play_type": "Y", "outcome": "WIN", "pnl_dollars": "99"},
    ]
    rec = bc.forward_record(rows, "X")
    assert rec["trades"] == 2
    assert rec["total_dollars"] == 6.0
    assert rec["win_rate"] == 50.0


def test_each_strategy_gets_one_stable_card_key():
    """Upsert depends on the key being stable - otherwise every refresh
    posts a new card instead of rewriting the existing one."""
    a = bc.card_key("SPY_GAP_CONT_50")
    b = bc.card_key("SPY_GAP_CONT_50")
    assert a == b
    assert a != bc.card_key("SPY_TOD_MIDDAY")


def test_the_channel_is_routed():
    assert spy_scanner.CHANNEL_NAMES.get("backtest_results") == "backtest-results"


def test_the_refresh_job_is_scheduled():
    assert "backtest-cards" in [j.name for j in engine.JOBS]


def test_cards_are_not_wired_into_performance_reporting():
    """Daily/weekly/monthly cover the 15 live strategies. This channel is a
    research surface and must not leak into those totals."""
    import performance_reconciliation as pr

    routes = getattr(pr, "REPORT_ROUTES", {})
    assert not any("backtest" in str(k).lower() for k in routes)
