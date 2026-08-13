from __future__ import annotations

from datetime import date
from unittest import mock

import tradier_equity_cache


def test_tradier_bar_to_robinhood_shape_uses_the_real_utc_epoch():
    """Tradier's own 'time' field is an unlabeled ET wall-clock string;
    mixing that with Robinhood's real UTC 'begins_at' timestamps would
    silently shift every bar by the ET/UTC offset. The unambiguous
    'timestamp' (unix epoch) field is what has to drive this, not
    'time'."""
    bar = {
        "time": "2026-08-13T09:30:00",
        "timestamp": 1786627800,
        "open": 774.87, "high": 774.95, "low": 774.111, "close": 774.35,
        "volume": 323766,
    }
    converted = tradier_equity_cache._tradier_bar_to_robinhood_shape(bar)
    assert converted["begins_at"] == "2026-08-13T13:30:00Z"
    assert converted["open_price"] == 774.87
    assert converted["high_price"] == 774.95
    assert converted["low_price"] == 774.111
    assert converted["close_price"] == 774.35
    assert converted["volume"] == 323766


def test_recent_real_trading_days_pulls_from_tradier_daily_history():
    daily = [
        {"date": "2026-08-07"}, {"date": "2026-08-10"}, {"date": "2026-08-11"},
        {"date": "2026-08-12"}, {"date": "2026-08-13"},
    ]
    with mock.patch.object(tradier_equity_cache.s, "get_daily_history", return_value=daily):
        days = tradier_equity_cache.recent_real_trading_days("SPY", n=3)
    assert days == ["2026-08-11", "2026-08-12", "2026-08-13"]


def test_fill_missing_recent_days_only_fetches_days_not_already_cached():
    """owner: "I'd like it automated so I don't have to ask for it to do
    its job ... so we don't miss anything" - a day already cached (by an
    earlier manual Robinhood pull, or a prior automated run) must be
    left untouched, both to avoid needless API calls and so a real
    Robinhood option-priced pull for that day is never silently
    clobbered."""
    with (
        mock.patch.object(
            tradier_equity_cache, "recent_real_trading_days",
            return_value=["2026-08-11", "2026-08-12", "2026-08-13"],
        ),
        mock.patch.object(
            tradier_equity_cache.robinhood_cache, "cached_equity_days", return_value=["2026-08-11"]
        ),
        mock.patch.object(
            tradier_equity_cache, "_fetch_tradier_intraday_bars_for_day",
            return_value=[{"time": "2026-08-12T09:30:00", "timestamp": 1786541400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        ) as fake_fetch,
        mock.patch.object(tradier_equity_cache.robinhood_cache, "save_equity_bars") as fake_save,
    ):
        result = tradier_equity_cache.fill_missing_recent_days("SPY")

    assert result["checked"] == ["2026-08-12", "2026-08-13"]
    assert result["filled"] == ["2026-08-12", "2026-08-13"]
    assert fake_fetch.call_count == 2
    assert fake_fetch.call_args_list[0].args == ("SPY", date(2026, 8, 12))
    assert fake_save.call_count == 2


def test_fill_missing_recent_days_skips_a_day_tradier_returns_nothing_for():
    """A day with no real bars back (market holiday miscounted as a
    trading day, or a real Tradier gap) must not get "cached" as an
    empty day - that would look identical to a real 0-volume day
    downstream and get silently trusted as complete."""
    with (
        mock.patch.object(
            tradier_equity_cache, "recent_real_trading_days", return_value=["2026-08-13"]
        ),
        mock.patch.object(tradier_equity_cache.robinhood_cache, "cached_equity_days", return_value=[]),
        mock.patch.object(tradier_equity_cache, "_fetch_tradier_intraday_bars_for_day", return_value=[]),
        mock.patch.object(tradier_equity_cache.robinhood_cache, "save_equity_bars") as fake_save,
    ):
        result = tradier_equity_cache.fill_missing_recent_days("SPY")

    assert result["checked"] == ["2026-08-13"]
    assert result["filled"] == []
    fake_save.assert_not_called()


def test_fill_missing_recent_days_does_nothing_when_everything_is_already_cached():
    with (
        mock.patch.object(
            tradier_equity_cache, "recent_real_trading_days", return_value=["2026-08-12", "2026-08-13"]
        ),
        mock.patch.object(
            tradier_equity_cache.robinhood_cache, "cached_equity_days",
            return_value=["2026-08-12", "2026-08-13"],
        ),
        mock.patch.object(tradier_equity_cache, "_fetch_tradier_intraday_bars_for_day") as fake_fetch,
    ):
        result = tradier_equity_cache.fill_missing_recent_days("SPY")

    assert result == {"checked": [], "filled": []}
    fake_fetch.assert_not_called()
