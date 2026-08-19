"""A time stop must fire on the clock, not on the quote.

Real incident 2026-08-19. Three strategies with measured time stops sat far
past them and rode a position to -76%:

    SPY_OPENING_GAP_FADE   15-minute stop   held 127 minutes
    SPY_TOD_FINAL30        30-minute stop   held 127 minutes
    SPY_EXHAUSTION_1ATR    30-minute stop   held 127 minutes

SPY_FIRST_PULLBACK left the SAME contract at 13:02 for +98%.

evaluate_open_new_strategy_row returned HOLD whenever the option quote
failed quote_is_reliable_for_exit - and it did that BEFORE computing how
long the position had been open, so the time stop was never consulted. A
0DTE's spread widens as it decays toward zero, which is precisely when its
time stop matters most.

An earlier audit of mine reported "time stop 30min: fires=True" for all
three. That was measured by calling new_strategy_exit_signal directly with
minutes_held supplied - the unit worked; the live path never reached it.
These tests go through evaluate_open_row, the way production does.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

import spy_scanner as s
import spy_live_new_strategies as lns

TIME_STOPPED = [p for p in lns.NEW_STRATEGY_PLAY_TYPES
                if lns.exit_rules_for(p)[2] is not None]

# A decayed 0DTE: real bid, real ask, spread too wide to trust for pricing.
UNRELIABLE = {"bid": 0.05, "ask": 0.12, "last": 0.08}
RELIABLE = {"bid": 0.30, "ask": 0.33, "last": 0.31}
SYMBOL = "SPY260819C00770000"


def _row(play_type: str):
    row = {f: "" for f in s.LOG_HEADER}
    row.update({
        "trade_id": f"T-{play_type}", "ticker": "SPY", "play_type": play_type,
        "option_symbol": SYMBOL, "expiration": s.now_ct().date().isoformat(),
        "entry_price": "0.46", "outcome": "OPEN",
        "timestamp": s.now_ct().isoformat(),
        "current_pl_pct": "-40", "current_pl_dollars": "-18", "last_mark": "0.28",
    })
    return row


def test_there_are_strategies_with_time_stops_to_protect():
    assert TIME_STOPPED, "no strategy defines a time stop - this test is vacuous"


@pytest.mark.parametrize("play_type", TIME_STOPPED)
def test_time_stop_fires_even_when_the_quote_is_unreliable(play_type):
    """THE regression. This is the 2026-08-19 failure."""
    row = _row(play_type)
    time_stop = lns.exit_rules_for(play_type)[2]
    past = s.now_ct() + timedelta(minutes=time_stop + 5)

    result = s.evaluate_open_row(row, {SYMBOL: UNRELIABLE}, past)

    assert result["signal"] == "TIME STOP", (
        f"{play_type} held {time_stop + 5} minutes on a {time_stop}-minute "
        f"stop and returned {result['signal']!r} because the quote was "
        "unreliable - a time stop does not need a price"
    )


@pytest.mark.parametrize("play_type", TIME_STOPPED)
def test_time_stop_still_fires_on_a_good_quote(play_type):
    row = _row(play_type)
    time_stop = lns.exit_rules_for(play_type)[2]
    past = s.now_ct() + timedelta(minutes=time_stop + 5)
    result = s.evaluate_open_row(row, {SYMBOL: RELIABLE}, past)
    assert result["signal"] == "TIME STOP"


@pytest.mark.parametrize("play_type", TIME_STOPPED)
def test_it_does_not_fire_early(play_type):
    """The fix must not turn an unreliable quote into a premature exit."""
    row = _row(play_type)
    time_stop = lns.exit_rules_for(play_type)[2]
    early = s.now_ct() + timedelta(minutes=max(time_stop - 5, 1))
    result = s.evaluate_open_row(row, {SYMBOL: UNRELIABLE}, early)
    assert result["signal"] == "HOLD", (
        f"{play_type} exited before its {time_stop}-minute stop"
    )


def test_a_strategy_without_a_time_stop_still_holds_on_a_bad_quote():
    """Only the three with measured time stops may exit on the clock."""
    plain = [p for p in lns.NEW_STRATEGY_PLAY_TYPES
             if lns.exit_rules_for(p)[2] is None]
    assert plain
    row = _row(plain[0])
    later = s.now_ct() + timedelta(minutes=200)
    result = s.evaluate_open_row(row, {SYMBOL: UNRELIABLE}, later)
    assert result["signal"] == "HOLD"
