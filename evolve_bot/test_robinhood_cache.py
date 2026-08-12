from __future__ import annotations
import tempfile
from pathlib import Path
from unittest import mock

import robinhood_cache as cache


def test_normalize_bars_drops_interpolated_bars():
    raw = [
        {"begins_at": "t1", "open_price": "1.0", "high_price": "1.5", "low_price": "0.9", "close_price": "1.2", "volume": 10, "interpolated": False},
        {"begins_at": "t2", "open_price": "1.2", "high_price": "1.2", "low_price": "1.2", "close_price": "1.2", "volume": 0, "interpolated": True},
    ]
    normalized = cache.normalize_bars(raw)
    assert len(normalized) == 1
    assert normalized[0] == {"timestamp": "t1", "open": 1.0, "high": 1.5, "low": 0.9, "close": 1.2, "volume": 10}


def test_normalize_bars_drops_malformed_bars():
    raw = [{"begins_at": "t1", "open_price": "not-a-number", "high_price": "1", "low_price": "1", "close_price": "1"}]
    assert cache.normalize_bars(raw) == []


def test_save_and_load_equity_bars_round_trips():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "EQUITY_DIR", Path(temp)):
            raw = [{"begins_at": "t1", "open_price": "600", "high_price": "601", "low_price": "599", "close_price": "600.5", "volume": 100}]
            saved = cache.save_equity_bars("SPY", "2026-07-06", raw)
            loaded = cache.load_equity_bars("SPY", "2026-07-06")
    assert saved == loaded
    assert loaded[0]["close"] == 600.5


def test_load_equity_bars_returns_empty_list_when_never_cached():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "EQUITY_DIR", Path(temp)):
            assert cache.load_equity_bars("SPY", "2099-01-01") == []


def test_cached_equity_days_lists_sorted_dates():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "EQUITY_DIR", Path(temp)):
            cache.save_equity_bars("SPY", "2026-07-06", [])
            cache.save_equity_bars("SPY", "2026-06-01", [])
            days = cache.cached_equity_days("SPY")
    assert days == ["2026-06-01", "2026-07-06"]


def test_save_and_load_option_bars_round_trips():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "OPTION_DIR", Path(temp)):
            raw = [{"begins_at": "t1", "open_price": "0.5", "high_price": "0.6", "low_price": "0.4", "close_price": "0.55", "volume": 5}]
            cache.save_option_bars("SPY260706P00600000", raw)
            loaded = cache.load_option_bars("SPY260706P00600000")
    assert loaded[0]["close"] == 0.55


def test_load_option_bars_returns_none_when_never_cached():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "OPTION_DIR", Path(temp)):
            assert cache.load_option_bars("SPY260706P00600000") is None


def test_has_cached_option():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(cache, "OPTION_DIR", Path(temp)):
            before = cache.has_cached_option("SPY260706P00600000")
            cache.save_option_bars("SPY260706P00600000", [])
            after = cache.has_cached_option("SPY260706P00600000")
    assert before is False
    assert after is True
