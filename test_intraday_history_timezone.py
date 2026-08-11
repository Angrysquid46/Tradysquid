"""Tradier's /markets/timesales endpoint interprets naive start/end strings
in America/New_York, one hour ahead of this system's own America/Chicago
convention - confirmed live: requesting end="15:00" (intended as the 3pm CT
close) returned bars stopping exactly at 15:00 ET, an hour before the real
close, and requesting a later end (16:00/17:00/20:00) still topped out at
15:59 ET (the real close), while requesting an earlier end (15:30) cut the
data off exactly there - proving the endpoint takes start/end literally with
no conversion of its own. get_intraday_history/get_premarket_history/
get_recent_intraday_history must build their request strings through
_et_window_str() so the CT wall-clock bounds they mean land on the correct
ET-labeled moment Tradier expects.
"""

from __future__ import annotations
from datetime import date
from unittest import mock

import spy_scanner


def test_et_window_str_shifts_ct_wall_clock_forward_one_hour_to_et():
    day = date(2026, 8, 11)
    assert spy_scanner._et_window_str(day, 8, 30) == "2026-08-11 09:30"
    assert spy_scanner._et_window_str(day, 15, 0) == "2026-08-11 16:00"


def test_get_intraday_history_requests_the_et_equivalent_of_the_ct_session():
    with mock.patch.object(spy_scanner, "now_ct", return_value=mock.Mock(date=lambda: date(2026, 8, 11))), \
         mock.patch.object(spy_scanner, "tradier_get", return_value={}) as fake_get:
        spy_scanner.get_intraday_history("SPY", interval="1min")

    _, params = fake_get.call_args[0]
    assert params["start"] == "2026-08-11 09:30"
    assert params["end"] == "2026-08-11 16:00"


def test_get_premarket_history_requests_the_et_equivalent_of_the_ct_premarket_window():
    with mock.patch.object(spy_scanner, "now_ct", return_value=mock.Mock(date=lambda: date(2026, 8, 11))), \
         mock.patch.object(spy_scanner, "tradier_get", return_value={}) as fake_get:
        spy_scanner.get_premarket_history("SPY", interval="5min")

    _, params = fake_get.call_args[0]
    assert params["start"] == "2026-08-11 04:00"
    assert params["end"] == "2026-08-11 09:30"


def test_get_recent_intraday_history_requests_the_et_equivalent_across_the_full_date_range():
    with mock.patch.object(spy_scanner, "now_ct", return_value=mock.Mock(date=lambda: date(2026, 8, 11))), \
         mock.patch.object(spy_scanner, "tradier_get", return_value={}) as fake_get:
        spy_scanner.get_recent_intraday_history("SPY", "5min", calendar_days=5)

    _, params = fake_get.call_args[0]
    assert params["start"] == "2026-08-06 09:30"
    assert params["end"] == "2026-08-11 16:00"
