from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import backtest_lab as lab
import market_data_store as store


@pytest.fixture
def scratch(monkeypatch):
    monkeypatch.setattr(store, "DATA_ROOT", Path(tempfile.mkdtemp()) / "market")
    monkeypatch.setattr(lab, "BACKTEST_DIR", Path(tempfile.mkdtemp()) / "backtests")
    return None


def _quote_row(captured_at: datetime, *, data_class=store.VERIFIED_REAL, bid=100.0, ask=100.05):
    return {
        "captured_at": captured_at.isoformat(), "symbol": "SPY",
        "bid": bid, "ask": ask, "last": (bid + ask) / 2,
        "bid_size": 10, "ask_size": 10, "change": 0.0, "change_percentage": 0.0,
        "volume": 1000, "trade_date_ms": 0, "bid_date_ms": 0, "ask_date_ms": 0,
        "provider": "tradier", "collector_version": "test", "data_class": data_class,
    }


def _chain_row(captured_at: datetime, symbol: str, *, data_class=store.VERIFIED_REAL, bid=1.0, ask=1.05):
    return {
        "captured_at": captured_at.isoformat(), "underlying_symbol": "SPY",
        "underlying_bid": 100.0, "underlying_ask": 100.05, "underlying_last": 100.02,
        "option_symbol": symbol, "expiration": captured_at.date().isoformat(),
        "strike": 500.0, "side": "call", "bid": bid, "ask": ask, "last": (bid + ask) / 2,
        "bid_size": 5, "ask_size": 5, "volume": 10, "open_interest": 100,
        "iv": 0.2, "delta": 0.5, "gamma": 0.01, "theta": -0.05, "vega": 0.1,
        "bid_date_ms": 0, "ask_date_ms": 0, "provider": "tradier",
        "collector_version": "test", "data_class": data_class,
    }


def _bar_row(bar_time: str, bar_timestamp: int, close: float, *, high=None, low=None, volume=1000):
    return {
        "bar_time": bar_time, "bar_timestamp": bar_timestamp, "symbol": "SPY",
        "open": close, "high": high if high is not None else close + 0.5,
        "low": low if low is not None else close - 0.5, "close": close,
        "price": close, "volume": volume, "vwap": close,
        "provider": "tradier", "collector_version": "test",
        "data_class": store.VERIFIED_REAL, "captured_at": bar_time,
    }


# --- market_as_of ------------------------------------------------------------

def test_market_as_of_returns_tier_a_for_recent_verified_quote(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now)])
    result = lab.MarketView("SPY").market_as_of(now + timedelta(seconds=30))
    assert result["tier"] == lab.TIER_A
    assert result["quote"]["bid"] == 100.0


def test_market_as_of_returns_tier_c_when_no_data_exists(scratch):
    result = lab.MarketView("SPY").market_as_of(datetime(2026, 8, 24, 9, 31, 0))
    assert result["tier"] == lab.TIER_C
    assert result["reason"] == lab.INSUFFICIENT_DATA


def test_market_as_of_returns_tier_c_when_stale_beyond_tolerance(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now)])
    result = lab.MarketView("SPY", tolerance_minutes=5).market_as_of(now + timedelta(minutes=10))
    assert result["tier"] == lab.TIER_C


def test_limited_underlying_quote_is_never_promoted_to_tier_a(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now, data_class=store.REAL_WITH_LIMITATIONS)])
    assert lab.MarketView("SPY").market_as_of(now)["tier"] == lab.TIER_C


# --- options_as_of -------------------------------------------------------------

def test_options_as_of_returns_tier_a_for_clean_snapshot(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_chain_snapshot("SPY", now.date(), now, [_chain_row(now, "SPY_EARLY")])
    result = lab.MarketView("SPY").options_as_of(now + timedelta(seconds=10))
    assert result["tier"] == lab.TIER_A
    assert len(result["contracts"]) == 1
    assert result["contracts"][0]["option_symbol"] == "SPY_EARLY"


def test_options_as_of_never_leaks_a_later_snapshot(scratch):
    """The core no-lookahead guarantee: querying a point in time between
    two real snapshots must only ever see the earlier one's contracts."""
    earlier = datetime(2026, 8, 24, 9, 31, 0)
    later = datetime(2026, 8, 24, 9, 35, 0)
    store.write_chain_snapshot("SPY", earlier.date(), earlier, [_chain_row(earlier, "SPY_EARLY")])
    store.write_chain_snapshot("SPY", later.date(), later, [_chain_row(later, "SPY_LATE")])

    between = datetime(2026, 8, 24, 9, 33, 0)
    result = lab.MarketView("SPY", tolerance_minutes=10).options_as_of(between)
    symbols = {c["option_symbol"] for c in result["contracts"]}
    assert symbols == {"SPY_EARLY"}
    assert "SPY_LATE" not in symbols


def test_options_as_of_tier_b_when_only_limited_data(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_chain_snapshot(
        "SPY", now.date(), now,
        [_chain_row(now, "SPY_LIMITED", data_class=store.REAL_WITH_LIMITATIONS)],
    )
    result = lab.MarketView("SPY").options_as_of(now + timedelta(seconds=10))
    assert result["tier"] == lab.TIER_B


def test_mixed_quality_chain_is_not_labeled_tier_a(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_chain_snapshot("SPY", now.date(), now, [
        _chain_row(now, "CLEAN"),
        _chain_row(now, "LIMITED", data_class=store.REAL_WITH_LIMITATIONS),
    ])
    assert lab.MarketView("SPY").options_as_of(now)["tier"] == lab.TIER_B


def test_options_as_of_tier_c_with_no_snapshot(scratch):
    result = lab.MarketView("SPY").options_as_of(datetime(2026, 8, 24, 9, 31, 0))
    assert result["tier"] == lab.TIER_C
    assert result["contracts"] == []


# --- events_as_of --------------------------------------------------------------

def test_events_as_of_always_tier_c(scratch):
    result = lab.MarketView("SPY").events_as_of(datetime(2026, 8, 24, 9, 31, 0))
    assert result["tier"] == lab.TIER_C
    assert result["events"] == []


# --- bars_as_of / compute_features ----------------------------------------------

def test_bars_as_of_only_returns_bars_at_or_before_timestamp(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    anchor = int(now.timestamp())
    bars = [
        _bar_row("2026-08-24T09:29:00", anchor - 120, 100.0),
        _bar_row("2026-08-24T09:30:00", anchor - 60, 101.0),
        _bar_row("2026-08-24T09:32:00", anchor + 60, 102.0),
    ]
    store.write_bars("SPY", now.date(), now, bars)
    result = lab.MarketView("SPY").bars_as_of(now, lookback_minutes=120)
    timestamps = [row["bar_timestamp"] for row in result]
    assert timestamps == [anchor - 120, anchor - 60]


def test_bars_as_of_excludes_a_bar_captured_after_the_query_timestamp(scratch):
    """Phase 14 audit finding: bars_as_of only filtered on bar_timestamp,
    not captured_at - a bar for an in-window time that was actually
    backfilled/captured LATER must still not appear "as of" a moment
    before it was really known, matching market_as_of/options_as_of's
    own no-lookahead discipline."""
    now = datetime(2026, 8, 24, 9, 31, 0)
    anchor = int(now.timestamp())
    backfilled = _bar_row("2026-08-24T09:30:00", anchor - 60, 101.0)
    backfilled["captured_at"] = "2026-08-24T10:00:00"  # captured AFTER `now`
    bars = [
        _bar_row("2026-08-24T09:29:00", anchor - 120, 100.0),
        backfilled,
    ]
    store.write_bars("SPY", now.date(), now, bars)
    result = lab.MarketView("SPY").bars_as_of(now, lookback_minutes=120)
    timestamps = [row["bar_timestamp"] for row in result]
    assert timestamps == [anchor - 120]  # the backfilled bar is excluded


def test_compute_features_returns_none_for_empty_bars():
    assert lab.compute_features([]) is None


def test_compute_features_matches_market_memory_directly(scratch):
    import market_memory

    bars = [
        _bar_row(f"2026-08-24T09:{30+i:02d}:00", 1000 + i * 60, 100.0 + i * 0.1)
        for i in range(25)
    ]
    result = lab.compute_features(bars)
    direct = market_memory.compute_features_for_window(bars, len(bars) - 1)

    assert result["feature_version"] == lab.FEATURE_VERSION
    for key, value in direct.items():
        assert result[key] == value, key


# --- dataset_fingerprint ---------------------------------------------------------

def test_formal_backtest_rejects_incomplete_bar_session(monkeypatch):
    monkeypatch.setattr(
        lab.market_data_collector,
        "session_bar_completeness",
        lambda symbol, day: {
            "trading_day": day.isoformat(), "expected": 390,
            "received": 389, "missing": 1, "missing_periods": [],
            "complete": False,
        },
    )
    with pytest.raises(ValueError, match="INCOMPLETE_BAR_SESSION.*missing 1"):
        lab.require_complete_bar_sessions("SPY", {date(2026, 8, 24)})


def test_formal_backtest_accepts_only_complete_bar_sessions(monkeypatch):
    monkeypatch.setattr(
        lab.market_data_collector,
        "session_bar_completeness",
        lambda symbol, day: {
            "trading_day": day.isoformat(), "expected": 390,
            "received": 390, "missing": 0, "missing_periods": [],
            "complete": True,
        },
    )
    result = lab.require_complete_bar_sessions(
        "SPY", {date(2026, 8, 25), date(2026, 8, 24)}
    )
    assert [item["trading_day"] for item in result] == ["2026-08-24", "2026-08-25"]


# --- dataset_fingerprint ---------------------------------------------------------

def test_dataset_fingerprint_stable_across_repeat_calls(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now)])
    day = date(2026, 8, 24)
    first = lab.dataset_fingerprint("SPY", day, day)
    second = lab.dataset_fingerprint("SPY", day, day)
    assert first == second


def test_dataset_fingerprint_changes_after_new_data_appended(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now)])
    day = date(2026, 8, 24)
    before = lab.dataset_fingerprint("SPY", day, day)

    later = datetime(2026, 8, 24, 9, 32, 0)
    store.write_quote("SPY", later.date(), later, [_quote_row(later)])
    after = lab.dataset_fingerprint("SPY", day, day)
    assert before != after


def test_dataset_fingerprint_changes_when_existing_content_mutates(scratch):
    now = datetime(2026, 8, 24, 9, 31, 0)
    store.write_quote("SPY", now.date(), now, [_quote_row(now)])
    day = now.date()
    before = lab.dataset_fingerprint("SPY", day, day)
    path = next(store.partition_dir(store.QUOTES_DATASET, "SPY", day).glob("*.parquet"))
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)
    after = lab.dataset_fingerprint("SPY", day, day)
    assert before != after


def test_dataset_fingerprint_handles_no_data_at_all(scratch):
    day = date(2026, 8, 24)
    result = lab.dataset_fingerprint("SPY", day, day)
    assert isinstance(result, str) and len(result) == 64


# --- record_backtest / load_backtest_records --------------------------------------

def test_record_backtest_round_trips(scratch):
    record = lab.record_backtest(
        bot_version="test-v0", dataset_fingerprint="abc123",
        date_range=("2026-08-24", "2026-08-24"), evidence_tier="A",
        data_quality={"grade": "A"}, feature_versions={"features": lab.FEATURE_VERSION},
        execution_assumptions={"slippage": 0}, parameters={"x": 1}, random_seed=42,
        results={"pnl": 0},
    )
    assert record["engine_version"] == lab.ENGINE_VERSION
    loaded = lab.load_backtest_records(datetime.fromisoformat(record["recorded_at"]).date())
    assert len(loaded) == 1
    assert loaded[0]["bot_version"] == "test-v0"


def test_record_backtest_is_append_only(scratch):
    for i in range(3):
        lab.record_backtest(
            bot_version=f"test-v{i}", dataset_fingerprint="abc123",
            date_range=("2026-08-24", "2026-08-24"), evidence_tier="A",
            data_quality={}, feature_versions={}, execution_assumptions={},
            parameters={}, random_seed=None, results={},
        )
    loaded = lab.load_backtest_records(datetime.now().astimezone().date())
    assert len(loaded) == 3
    assert [r["bot_version"] for r in loaded] == ["test-v0", "test-v1", "test-v2"]


def test_load_backtest_records_returns_empty_for_missing_day(scratch):
    assert lab.load_backtest_records(date(2099, 1, 1)) == []
