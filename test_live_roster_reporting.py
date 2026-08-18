"""Reporting must count only strategies that still exist.

The trade log keeps closed rows forever, including rows belonging to
strategies since retired. Those were real paper trades, but a monthly
card that lists SPY_GAP_CONT_25 under "Top Strategies" is reporting a
strategy that cannot trade - it is not on the roster, has no channel, and
no card.

Separately, the Strategy Leaderboard could only ever show one strategy:
OTHER_STRATEGY_VARIANTS holds a single entry. It listed Key-Levels alone
at 0W/1L directly beneath a dashboard counting 14W/2L across the roster.
"""

from __future__ import annotations

import performance_reconciliation as pr
import spy_live_new_strategies as lns
import spy_scanner


RETIRED = ["SPY_GAP_CONT_25", "SPY_SWEEP_5", "SPY_GAP_CONT_100", "SPY_0DTE_5M"]


def _row(play, outcome="WIN", pnl="8"):
    # Closed rows must carry lifecycle timestamps or the reconciler
    # refuses them outright - it will not silently score a trade whose
    # open/close times are unknown.
    return {"play_type": play, "outcome": outcome, "pnl_dollars": pnl,
            "ticker": "SPY", "trade_id": f"T-{play}",
            "timestamp": "2026-08-17T09:35:00-05:00",
            "entry_time": "2026-08-17T09:35:00-05:00",
            "exit_time": "2026-08-17T10:05:00-05:00",
            "closed_at": "2026-08-17T10:05:00-05:00",
            "entry_price": "1.15", "exit_price": "1.27",
            "pnl_pct": "12", "call_or_put": "call", "strike": "770"}


def test_retired_strategies_are_not_counted():
    rows = [_row(p) for p in RETIRED] + [_row("SPY_GAP_CONT_50")]
    kept = pr.only_live_strategies(rows)
    assert [r["play_type"] for r in kept] == ["SPY_GAP_CONT_50"]


def test_every_live_strategy_is_counted():
    live = pr.live_play_types()
    for play in lns.NEW_STRATEGY_PLAY_TYPES:
        assert play in live, f"{play} would be dropped from reporting"
    assert spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE in live


def test_the_leaderboard_covers_more_than_one_strategy():
    """It showed Key-Levels alone while the dashboard above it counted 14
    wins across the roster."""
    rows = [_row(p) for p in lns.NEW_STRATEGY_PLAY_TYPES]
    body = pr.format_strategy_leaderboard(rows)
    named = sum(1 for p in lns.NEW_STRATEGY_PLAY_TYPES if p in body
                or p.replace("SPY_", "").replace("_", " ").title() in body)
    assert named >= 3, f"leaderboard named only {named} strategies"


def test_the_leaderboard_does_not_list_retired_strategies():
    rows = [_row(p) for p in RETIRED] + [_row("SPY_GAP_CONT_50")]
    body = pr.format_strategy_leaderboard(rows)
    for play in RETIRED:
        assert play not in body, f"{play} is retired but appears on the board"


def test_period_reports_drop_retired_rows():
    """daily/weekly/monthly all render through result_summary."""
    rows = [_row(p) for p in RETIRED] + [_row("SPY_GAP_CONT_50")]
    body = pr.result_summary("Test", rows, "period")
    for play in RETIRED:
        assert play not in body


# ---------------------------------------------------------------------------
# SPY_KEY_LEVELS stop width
# ---------------------------------------------------------------------------

def test_key_levels_stop_is_the_widened_setting():
    """0.45%, not the original 0.15%.

    Key-Levels exits on the UNDERLYING hitting a level with a 2R target,
    not on a percentage of premium. Measured under that real rule it is
    profitable at every stop distance tested, and widening the stop trades
    volume for edge:

        0.15%  4,472 trades  +$6.13/trade  +$27,423
        0.30%  2,209 trades  +$16.27/trade +$35,935
        0.45%  1,591 trades  +$26.86/trade +$42,740

    It had looked like the worst strategy in the set only because it was
    being measured with a borrowed +50/-50 option-premium exit it does not
    use, which is also what nearly got it deleted.
    """
    import spy_scanner

    assert spy_scanner.SPY_KEY_LEVELS_STOP_BUFFER_PCT == 0.45
    assert spy_scanner.SPY_KEY_LEVELS_TARGET_R_MULTIPLE == 2.0


def test_key_levels_is_still_on_the_live_roster():
    """It was proposed for removal on the strength of the broken
    measurement. Guard against that being reintroduced quietly."""
    import spy_scanner

    assert spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE in pr.live_play_types()
    assert spy_scanner.trade_types_enabled().get("spy_key_levels") is True
