"""Tests for the time-of-day entry exclusion: the opening minutes carry
elevated volatility as the market digests overnight news, and the midday
window sees materially thinner participation - both distort entries for
reasons unrelated to the actual thesis. This only ever blocks new entries,
never exits or position management."""

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


def test_inside_the_midday_lull_is_blocked():
    reason = spy_scanner.entry_window_blocked(_ct(11, 0))
    assert reason != ""
    assert "lull" in reason


def test_afternoon_after_the_lull_is_allowed_again():
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
