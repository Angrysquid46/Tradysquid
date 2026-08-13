"""Tests for the time-of-day entry exclusion: the opening minutes carry
elevated volatility as the market digests overnight news, so entries are
still blocked there. The midday liquidity-lull exclusion was removed
2026-08-13 (owner: real, rare TradingView alerts were getting lost to
this window with no way to recover them once it cleared) - entries are
allowed there now, tested explicitly below so a future change can't
silently reintroduce the block without a visible test failure. This
only ever blocks new entries, never exits or position management."""

from __future__ import annotations

from datetime import datetime

import spy_scanner


def _ct(hour: int, minute: int) -> datetime:
    # A Wednesday - matches market_is_open_now's weekday check.
    return datetime(2026, 8, 5, hour, minute, tzinfo=spy_scanner.now_ct().tzinfo)


def test_right_at_the_open_is_blocked():
    reason = spy_scanner.entry_window_blocked(_ct(8, 30))
    assert reason != ""
    assert "first" in reason


def test_just_before_the_opening_exclusion_ends_is_still_blocked():
    reason = spy_scanner.entry_window_blocked(_ct(8, 44))  # 14 min in, exclusion is 15
    assert reason != ""


def test_right_after_the_opening_exclusion_ends_is_allowed():
    reason = spy_scanner.entry_window_blocked(_ct(8, 46))  # 16 min in
    assert reason == ""


def test_midmorning_well_clear_of_both_windows_is_allowed():
    reason = spy_scanner.entry_window_blocked(_ct(9, 30))
    assert reason == ""


def test_the_former_midday_lull_window_is_now_allowed():
    """Regression guard: the midday liquidity-lull exclusion (10:30am-
    12:00pm CT) was deliberately removed 2026-08-13 - a real TradingView
    alert landed inside this window and was lost, since by the time the
    window cleared the alert had already gone stale. Entries must stay
    allowed here unless the owner explicitly asks for this back."""
    reason = spy_scanner.entry_window_blocked(_ct(11, 0))
    assert reason == ""


def test_afternoon_is_allowed():
    reason = spy_scanner.entry_window_blocked(_ct(13, 30))
    assert reason == ""


def test_outside_market_hours_is_not_specifically_blocked_by_this_check():
    # The normal closed-market handling covers this elsewhere - this check
    # returning "" here just means it isn't the one doing the blocking.
    reason = spy_scanner.entry_window_blocked(_ct(20, 0))
    assert reason == ""


def test_a_weekend_is_not_specifically_blocked_by_this_check():
    saturday = datetime(2026, 8, 8, 10, 0, tzinfo=spy_scanner.now_ct().tzinfo)
    reason = spy_scanner.entry_window_blocked(saturday)
    assert reason == ""
