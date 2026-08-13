from __future__ import annotations
import tempfile
from pathlib import Path
from unittest import mock

import backtest
import spy_scanner as s


def _bar(minute_offset: int, close: float, high: float | None = None, low: float | None = None) -> dict:
    hour = 13 + (30 + minute_offset) // 60
    minute = (30 + minute_offset) % 60
    return {
        "timestamp": f"2026-07-06T{hour:02d}:{minute:02d}:00Z",
        "open": close, "high": high if high is not None else close,
        "low": low if low is not None else close, "close": close, "volume": 100,
    }


def _bullish_day_bars() -> list[dict]:
    # 30 opening-range bars flat between 599.5 and 600.5.
    opening_range = [_bar(i, 600.0, high=600.5, low=599.5) for i in range(30)]
    # Breakout bar at minute 30 clears the range high.
    breakout = [_bar(30, 601.0)]
    # A clear upward move afterward - should push a Black-Scholes call
    # premium up enough to trip a take-profit under a loose variant.
    after = [_bar(31 + i, 601.0 + (i + 1) * 3.0) for i in range(8)]
    return opening_range + breakout + after


def _flat_daily_history(trading_day: str, days: int = 5) -> list[dict]:
    # Small real day-to-day variance so estimate_implied_volatility returns
    # a usable positive vol - an exactly-flat series gives 0.0 vol, which
    # collapses every synthetic delta to 0/1 and no candidate ever
    # qualifies for the 0.40-0.60 delta band.
    closes = [598.0, 601.0, 599.0, 602.0, 600.0][:days]
    return [
        {"date": f"2026-07-0{d+1}", "open": str(c), "high": str(c + 1), "low": str(c - 1), "close": str(c)}
        for d, c in enumerate(closes)
    ]


def test_daily_bars_through_requests_enough_runway_for_an_old_trading_day():
    """Regression guard: lookback_days is measured back from TODAY, not
    from trading_day, so a too-small default silently starves an older
    trading_day of enough history for MARKET_CONDITION_VOL_LOOKBACK_DAYS
    (20 trading days) - this bit for real on the earliest cached day
    (2026-07-06) with the old default of 60, producing an UNKNOWN
    market_condition with no test failure to catch it."""
    with mock.patch.object(backtest.s, "get_daily_history", return_value=[]) as fake:
        backtest._daily_bars_through("2026-07-06")
    fake.assert_called_once_with(backtest.s.TICKER, days=150)


def test_find_breakout_index_locates_the_first_bar_past_the_range():
    bars = _bullish_day_bars()
    assert backtest._find_breakout_index(bars) == 30


def test_find_breakout_index_returns_none_when_not_enough_bars():
    assert backtest._find_breakout_index([_bar(0, 600.0)]) is None


def test_run_backtest_for_day_returns_no_rows_when_uncached():
    with mock.patch.object(backtest.robinhood_cache, "load_equity_bars", return_value=[]):
        assert backtest.run_backtest_for_day("2026-07-06") == []


def test_run_backtest_for_day_returns_no_rows_when_range_never_breaks():
    flat_bars = [_bar(i, 600.0, high=600.5, low=599.5) for i in range(60)]
    with mock.patch.object(backtest.robinhood_cache, "load_equity_bars", return_value=flat_bars):
        assert backtest.run_backtest_for_day("2026-07-06") == []


def test_run_backtest_for_day_generates_rows_for_a_qualified_bullish_day():
    bars = _bullish_day_bars()
    with (
        mock.patch.object(backtest.robinhood_cache, "load_equity_bars", return_value=bars),
        mock.patch.object(backtest.robinhood_cache, "load_option_bars", return_value=None),
        mock.patch.object(backtest.s, "get_daily_history", return_value=_flat_daily_history("2026-07-06")),
        mock.patch.object(backtest.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(backtest.market_features, "vix_on_or_before", return_value=16.2),
        mock.patch.object(backtest.market_features, "market_sentiment_for_date", return_value=0.05),
    ):
        rows = backtest.run_backtest_for_day("2026-07-06")

    assert rows
    assert all(row["call_or_put"] == "call" for row in rows)
    assert all(row["price_source_at_entry"] == "synthetic" for row in rows)
    variant_labels = {row["variant_label"] for row in rows}
    assert variant_labels == {v["label"] for v in backtest.DEFAULT_VARIANTS}
    # Every candidate x every variant.
    candidate_symbols = {row["option_symbol"] for row in rows}
    assert len(rows) == len(candidate_symbols) * len(backtest.DEFAULT_VARIANTS)
    assert all(row["vix_at_entry"] == 16.2 for row in rows)
    assert all(row["sentiment_at_entry"] == 0.05 for row in rows)
    assert all(row["put_call_ratio_at_entry"] == "" for row in rows)


def test_run_backtest_for_day_uses_real_price_when_cached():
    bars = _bullish_day_bars()

    def fake_option_bars(symbol):
        # Real print far above what synthetic pricing would produce, so a
        # test can tell the real-price path was actually taken.
        return [{"timestamp": "2026-07-06T14:01:00Z", "open": 50.0, "high": 50.0, "low": 50.0, "close": 50.0, "volume": 1}]

    with (
        mock.patch.object(backtest.robinhood_cache, "load_equity_bars", return_value=bars),
        mock.patch.object(backtest.robinhood_cache, "load_option_bars", side_effect=fake_option_bars),
        mock.patch.object(backtest.s, "get_daily_history", return_value=_flat_daily_history("2026-07-06")),
        mock.patch.object(backtest.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(backtest.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(backtest.market_features, "market_sentiment_for_date", return_value=None),
    ):
        rows = backtest.run_backtest_for_day("2026-07-06")

    assert rows
    # A $50 real mark against a small entry price is a massive gain -
    # every variant should read this as a WIN via TAKE PROFIT.
    assert all(row["outcome"] == "WIN" for row in rows)
    assert all(row["last_signal"] == "TAKE PROFIT" for row in rows)


def test_run_backtest_is_idempotent_on_rerun():
    bars = _bullish_day_bars()
    with tempfile.TemporaryDirectory() as temp:
        trades_path = Path(temp) / "backtest_trades.csv"
        with (
            mock.patch.object(backtest, "BACKTEST_TRADES_PATH", trades_path),
            mock.patch.object(backtest.robinhood_cache, "load_equity_bars", return_value=bars),
            mock.patch.object(backtest.robinhood_cache, "load_option_bars", return_value=None),
            mock.patch.object(backtest.s, "get_daily_history", return_value=_flat_daily_history("2026-07-06")),
            mock.patch.object(backtest.market_features, "fetch_vix_series", return_value=[]),
            mock.patch.object(backtest.market_features, "vix_on_or_before", return_value=None),
            mock.patch.object(backtest.market_features, "market_sentiment_for_date", return_value=None),
        ):
            first = backtest.run_backtest(["2026-07-06"])
            second = backtest.run_backtest(["2026-07-06"])

    assert first["rows_written_this_run"] == second["rows_written_this_run"]
    assert first["total_rows_in_file"] == second["total_rows_in_file"]
    assert first["trading_days_with_a_qualified_entry"] == 1
