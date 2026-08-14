"""Tests for market_memory.py - the standalone, opt-in historical
bar/feature/pattern store. Owner: "I want it to remember chart patterns
and history and everything so when we make new strategies we can have
all this shit tracked already." Not imported by any live strategy, so
these tests exercise it entirely in isolation against a temp SQLite DB,
never the real state/market_memory.db."""

from __future__ import annotations

import tempfile
from datetime import datetime as real_datetime
from pathlib import Path
from unittest import mock

import spy_scanner
import market_memory as mm


def _bar(bar_time: str, o: float, h: float, l: float, c: float, v: float = 1_000_000.0) -> tuple:
    return (bar_time, o, h, l, c, v)


def _isolated_db():
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_market_memory.db"
    return temp_dir, mock.patch.object(mm, "DB_PATH", db_path)


# ---------------------------------------------------------------------------
# New shared-math primitives (spy_scanner.py)
# ---------------------------------------------------------------------------

def test_average_true_range_matches_hand_calculation():
    # Constant range of 2 every bar (high = close+1, low = close-1) with
    # no gaps -> true range is exactly 2 every bar -> ATR is exactly 2.
    closes = [100.0 + i for i in range(20)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    assert spy_scanner.average_true_range(highs, lows, closes, 14) == 2.0


def test_average_true_range_none_with_insufficient_data():
    assert spy_scanner.average_true_range([1, 2], [1, 2], [1, 2], 14) is None


def test_average_true_range_accounts_for_gaps_not_just_high_low():
    # A gap far above yesterday's close makes true range larger than the
    # bar's own high-low - this is exactly what plain high-low misses.
    closes = [100.0] * 14 + [110.0]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    atr = spy_scanner.average_true_range(highs, lows, closes, 14)
    assert atr is not None and atr > 1.0  # the gap bar alone has a true range of ~9.5-10.5


def test_bollinger_bands_matches_hand_calculation():
    closes = [100.0] * 19 + [110.0]
    upper, mid, lower = spy_scanner.bollinger_bands(closes, 20, 2.0)
    assert mid == sum(closes) / 20
    assert upper > mid > lower


def test_bollinger_bands_none_with_insufficient_data():
    assert spy_scanner.bollinger_bands([1, 2, 3], 20, 2.0) == (None, None, None)


# ---------------------------------------------------------------------------
# Bar storage
# ---------------------------------------------------------------------------

def test_store_bars_is_idempotent_on_rerun():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        rows = [_bar("2026-01-01", 100, 101, 99, 100.5), _bar("2026-01-02", 100.5, 102, 100, 101.5)]
        first = mm.store_bars(conn, "SPY", "daily", rows)
        second = mm.store_bars(conn, "SPY", "daily", rows)
        assert first == 2
        assert second == 0
        assert len(mm.load_bars(conn, "SPY", "daily")) == 2
        conn.close()


# ---------------------------------------------------------------------------
# Feature computation never looks ahead
# ---------------------------------------------------------------------------

def test_compute_features_never_looks_ahead():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        rows = [_bar(f"2026-01-{i+1:02d}", 100 + i, 101 + i, 99 + i, 100 + i) for i in range(25)]
        mm.store_bars(conn, "SPY", "daily", rows)
        bars = mm.load_bars(conn, "SPY", "daily")

        features_full = mm.compute_features_for_window(bars, 9)
        truncated_bars = bars[:10]
        features_truncated = mm.compute_features_for_window(truncated_bars, 9)
        assert features_full["ema_9"] == features_truncated["ema_9"]
        assert features_full["rsi_14"] == features_truncated["rsi_14"]
        conn.close()


def test_short_medium_long_term_trend_label_reflects_a_real_uptrend():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # A clean, steady uptrend - every moving average should agree.
        rows = [_bar(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", 100 + i * 0.5, 101 + i * 0.5, 99 + i * 0.5, 100 + i * 0.5)
                for i in range(220)]
        mm.store_bars(conn, "SPY", "daily", rows)
        bars = mm.load_bars(conn, "SPY", "daily")
        features = mm.compute_features_for_window(bars, len(bars) - 1)
        assert features["short_term_trend"] == "UP"
        assert features["medium_term_trend"] == "UP"
        assert features["long_term_trend"] == "UP"
        assert features["trend_label"] == "SHORT:UP MEDIUM:UP LONG:UP"
        conn.close()


def test_price_above_moving_average_flags():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        rows = [_bar(f"d{i:04d}", 100, 101, 99, 100) for i in range(210)]
        # Final bar closes well above the flat history.
        rows.append(_bar(f"d{210:04d}", 100, 130, 99, 125))
        mm.store_bars(conn, "SPY", "daily", rows)
        bars = mm.load_bars(conn, "SPY", "daily")
        features = mm.compute_features_for_window(bars, len(bars) - 1)
        assert features["price_above_sma_200"] == 1
        assert features["price_above_ema_200"] == 1
        conn.close()


def test_golden_cross_fires_only_on_the_bar_the_crossover_happens():
    """A synthetic series engineered so SMA50 crosses above SMA200
    exactly once - golden_cross must be True only on that specific bar,
    not on every subsequent bar where sma_50 > sma_200 stays true."""
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # 200 flat bars at 100 (both SMAs settle near 100), then a sharp
        # ramp so SMA50 pulls above SMA200 partway through.
        rows = [_bar(f"d{i:04d}", 100, 100, 100, 100) for i in range(200)]
        rows += [_bar(f"d{200+i:04d}", 100 + i * 2, 100 + i * 2, 100 + i * 2, 100 + i * 2) for i in range(60)]
        mm.store_bars(conn, "SPY", "daily", rows)
        bars = mm.load_bars(conn, "SPY", "daily")

        golden_cross_bars = []
        for i in range(len(bars)):
            features = mm.compute_features_for_window(bars, i)
            if features.get("golden_cross"):
                golden_cross_bars.append(i)
        assert len(golden_cross_bars) == 1
        conn.close()


def test_atr_percentile_ranks_a_volatility_spike_near_the_top():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # 50 calm bars (range of 1), then one wide bar (range of 20).
        rows = [_bar(f"d{i:03d}", 100, 100.5, 99.5, 100) for i in range(50)]
        rows.append(_bar("d050", 100, 110, 90, 100))
        mm.store_bars(conn, "SPY", "daily", rows)
        bars = mm.load_bars(conn, "SPY", "daily")
        features = mm.compute_features_for_window(bars, len(bars) - 1)
        assert features["atr_percentile"] is not None
        assert features["atr_percentile"] > 90
        conn.close()


# ---------------------------------------------------------------------------
# Structural pattern detectors
# ---------------------------------------------------------------------------

def _row_series(specs: list[tuple[float, float, float, float]]) -> list[dict]:
    """specs of (open, high, low, close) -> fake sqlite3.Row-like dicts."""
    return [{"bar_time": f"t{i}", "open": o, "high": h, "low": l, "close": c, "volume": 1000.0}
            for i, (o, h, l, c) in enumerate(specs)]


def test_inside_bar_detection():
    bars = _row_series([(100, 110, 90, 105), (100, 108, 92, 104)])
    features = {"inside_bar": 1}
    assert mm._detect_inside_bar(bars, features, 1) is True


def test_outside_bar_detection():
    bars = _row_series([(100, 105, 95, 102), (98, 112, 88, 108)])
    features = {"outside_bar": 1}
    assert mm._detect_outside_bar(bars, features, 1) is True


def test_gap_up_and_gap_down_detection():
    up = mm._detect_gap_up([], {"gap_pct": 1.0}, 0)
    down = mm._detect_gap_down([], {"gap_pct": -1.0}, 0)
    no_gap = mm._detect_gap_up([], {"gap_pct": 0.05}, 0)
    assert up is True
    assert down is True
    assert no_gap is False


def test_doji_detection_needs_a_tiny_body_relative_to_range():
    doji_bar = _row_series([(100, 110, 90, 100.5)])
    real_body_bar = _row_series([(100, 110, 90, 108)])
    assert mm._detect_doji(doji_bar, {}, 0) is True
    assert mm._detect_doji(real_body_bar, {}, 0) is False


def test_bullish_engulfing_detection():
    bars = _row_series([(105, 106, 99, 100), (99, 111, 98, 110)])
    assert mm._detect_bullish_engulfing(bars, {}, 1) is True
    assert mm._detect_bearish_engulfing(bars, {}, 1) is False


def test_bearish_engulfing_detection():
    bars = _row_series([(100, 106, 99, 105), (106, 107, 94, 95)])
    assert mm._detect_bearish_engulfing(bars, {}, 1) is True
    assert mm._detect_bullish_engulfing(bars, {}, 1) is False


def test_candlestick_patterns_carry_the_weak_evidence_note():
    """Owner-facing honesty requirement: a candlestick-category pattern
    must never look indistinguishable from a real structural one."""
    category, evidence_note, _ = mm.PATTERN_REGISTRY["doji"]
    assert category == "candlestick"
    assert "weak" in evidence_note.lower() or "folklore" in evidence_note.lower()


def test_structural_patterns_do_not_carry_the_weak_evidence_note():
    category, evidence_note, _ = mm.PATTERN_REGISTRY["inside_bar"]
    assert category == "structural"
    assert evidence_note == mm.STRUCTURAL_EVIDENCE_NOTE


# ---------------------------------------------------------------------------
# Pattern storage + outcome tracking, end to end against a real temp DB
# ---------------------------------------------------------------------------

def test_pattern_storage_is_deduplicated_on_rerun():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        first = mm.store_patterns(conn, "SPY", "daily", "2026-01-01", ["inside_bar"])
        second = mm.store_patterns(conn, "SPY", "daily", "2026-01-01", ["inside_bar"])
        assert len(first) == 1
        assert len(second) == 0  # INSERT OR IGNORE - already there
        count = conn.execute("SELECT COUNT(*) AS n FROM patterns").fetchone()["n"]
        assert count == 1
        conn.close()


def test_backfill_pattern_outcomes_computes_real_forward_return():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # 30 bars, closes rising by 1 each day starting at 100.
        rows = [_bar(f"2026-01-{i+1:02d}", 100 + i, 101 + i, 99 + i, 100 + i) for i in range(30)]
        mm.store_bars(conn, "SPY", "daily", rows)
        # Pattern detected on the very first bar (index 0, close=100).
        mm.store_patterns(conn, "SPY", "daily", "2026-01-01", ["inside_bar"])

        written = mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        assert written == len(mm.FORWARD_RETURN_HORIZONS)  # 5, 10, 20 bars all now exist

        stats = mm.pattern_stats("SPY", "daily", "inside_bar")
        assert stats["total_occurrences"] == 1
        five_bar = stats["by_horizon"][5]
        # close at index 5 is 105, entry close 100 -> +5%
        assert five_bar["n"] == 1
        assert round(five_bar["avg_return_pct"], 2) == 5.0
        assert five_bar["win_rate_pct"] == 100.0
        conn.close()


def test_backfill_pattern_outcomes_never_recomputes_an_existing_outcome():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        rows = [_bar(f"2026-01-{i+1:02d}", 100, 101, 99, 100) for i in range(25)]
        mm.store_bars(conn, "SPY", "daily", rows)
        mm.store_patterns(conn, "SPY", "daily", "2026-01-01", ["inside_bar"])
        first = mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        second = mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        assert first > 0
        assert second == 0  # nothing new to fill in
        conn.close()


def test_pattern_stats_reports_none_for_a_horizon_with_no_data_yet():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # Only 3 bars total - not enough for even the 5-bar horizon.
        rows = [_bar(f"2026-01-{i+1:02d}", 100, 101, 99, 100) for i in range(3)]
        mm.store_bars(conn, "SPY", "daily", rows)
        mm.store_patterns(conn, "SPY", "daily", "2026-01-01", ["inside_bar"])
        mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        stats = mm.pattern_stats("SPY", "daily", "inside_bar")
        assert stats["by_horizon"][5] is None
        conn.close()


# ---------------------------------------------------------------------------
# Collection cycle - safe to rerun, uses real spy_scanner history functions
# (mocked here, never a real network call in tests)
# ---------------------------------------------------------------------------

def _fake_daily_history(n_days: int) -> list[dict]:
    return [
        {"date": f"2026-01-{i+1:02d}", "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 1_000_000}
        for i in range(n_days)
    ]


def test_run_collection_cycle_is_safe_to_rerun():
    temp_dir, patcher = _isolated_db()
    with (
        temp_dir, patcher,
        mock.patch.object(spy_scanner, "get_daily_history", return_value=_fake_daily_history(25)),
        mock.patch.object(spy_scanner, "get_intraday_history", return_value=[]),
    ):
        first = mm.run_collection_cycle("SPY")
        second = mm.run_collection_cycle("SPY")

    assert first["daily"]["new_bars"] == 25
    assert first["daily"]["features_computed"] == 25
    assert second["daily"]["new_bars"] == 0
    assert second["daily"]["features_computed"] == 0


def test_run_collection_cycle_survives_intraday_fetch_failure():
    """A live-scanner-hours API hiccup on the intraday fetch must never
    prevent the daily layer (the deep, reliable history) from updating."""
    temp_dir, patcher = _isolated_db()
    with (
        temp_dir, patcher,
        mock.patch.object(spy_scanner, "get_daily_history", return_value=_fake_daily_history(5)),
        mock.patch.object(spy_scanner, "get_intraday_history", side_effect=RuntimeError("provider down")),
    ):
        result = mm.run_collection_cycle("SPY")

    assert result["daily"]["new_bars"] == 5
    assert result["intraday_5min"]["new_bars"] == 0


def test_run_collection_cycle_exports_a_real_csv():
    temp_dir, patcher = _isolated_db()
    csv_dir = tempfile.TemporaryDirectory()
    csv_path = Path(csv_dir.name) / "daily.csv"
    with (
        temp_dir, patcher, csv_dir,
        mock.patch.object(mm, "DAILY_CSV_PATH", csv_path),
        mock.patch.object(mm, "INTRADAY_CSV_PATH", Path(csv_dir.name) / "intraday.csv"),
        mock.patch.object(spy_scanner, "get_daily_history", return_value=_fake_daily_history(10)),
        mock.patch.object(spy_scanner, "get_intraday_history", return_value=[]),
    ):
        result = mm.run_collection_cycle("SPY")
        assert result["csv_exported"]["daily_rows"] == 10
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")

    assert "sma_20" in content  # header includes the new feature columns
    assert "trend_label" in content
    assert content.count("\n") == 11  # header + 10 data rows (+ trailing newline)


# ---------------------------------------------------------------------------
# Recent-vs-all-time comparison
# ---------------------------------------------------------------------------

def test_pattern_stats_recent_vs_all_time_separates_old_from_new_occurrences():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # 40 bars: an "old" pattern occurrence near the start, a "recent"
        # one near the end, both with enough forward bars to resolve.
        rows = [_bar(f"2020-01-{i+1:02d}" if i < 15 else f"2026-08-{i-14:02d}", 100 + i, 101 + i, 99 + i, 100 + i)
                for i in range(40)]
        mm.store_bars(conn, "SPY", "daily", rows)
        mm.store_patterns(conn, "SPY", "daily", "2020-01-01", ["inside_bar"])  # old
        mm.store_patterns(conn, "SPY", "daily", "2026-08-05", ["inside_bar"])  # recent
        mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        conn.close()

        with mock.patch.object(mm, "datetime") as fake_datetime:
            fake_datetime.now.return_value = real_datetime(2026, 8, 20)
            comparison = mm.pattern_stats_recent_vs_all_time("SPY", "daily", "inside_bar", recent_days=180)

    assert comparison["all_time"]["total_occurrences"] == 2
    assert comparison["recent"]["total_occurrences"] == 1


# ---------------------------------------------------------------------------
# Historical intraday backfill
# ---------------------------------------------------------------------------

def _fake_series_response(bar_times: list[str]) -> dict:
    data = [{"time": t, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0} for t in bar_times]
    return {"series": {"data": data if len(data) != 1 else data[0]}}


def test_fetch_intraday_for_day_parses_a_real_series_response():
    with mock.patch.object(spy_scanner, "tradier_get", return_value=_fake_series_response(["2026-08-10T09:30:00", "2026-08-10T09:35:00"])) as tradier_get:
        bars = mm._fetch_intraday_for_day("SPY", real_datetime(2026, 8, 10).date())
    assert len(bars) == 2
    assert bars[0]["time"] == "2026-08-10T09:30:00"
    # Confirms this actually asks for the requested PAST day, not "today".
    params = tradier_get.call_args[0][1]
    assert "2026-08-10" in params["start"]


def test_fetch_intraday_for_day_returns_empty_list_when_no_data():
    with mock.patch.object(spy_scanner, "tradier_get", return_value={"series": {}}):
        bars = mm._fetch_intraday_for_day("SPY", real_datetime(2026, 7, 4).date())  # a holiday
    assert bars == []


def test_intraday_history_start_boundary_parses_the_real_error_message():
    """Regression guard for the real bug this whole feature corrects:
    the module used to assume intraday history could only ever cover
    "today" - confirmed false live (Tradier's real error message states
    an actual retention boundary, ~2 months back, not zero)."""
    error = spy_scanner.TradierError(
        "Tradier HTTP 400 for /markets/timesales: Invalid parameter, "
        "start: must be on or after 2026-06-18 00:00:00."
    )
    with mock.patch.object(mm, "_fetch_intraday_for_day", side_effect=error):
        boundary = mm._intraday_history_start_boundary("SPY", today=real_datetime(2026, 8, 14).date())
    assert boundary == real_datetime(2026, 6, 18).date()


def test_intraday_history_start_boundary_returns_none_on_an_unrelated_error():
    error = spy_scanner.TradierError("Tradier HTTP 500 for /markets/timesales: internal error")
    with mock.patch.object(mm, "_fetch_intraday_for_day", side_effect=error):
        boundary = mm._intraday_history_start_boundary("SPY", today=real_datetime(2026, 8, 14).date())
    assert boundary is None


def test_backfill_historical_intraday_skips_dates_already_covered():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # A Monday already fully stored.
        mm.store_bars(conn, "SPY", "5min", [_bar("2026-08-10T09:30:00", 100, 101, 99, 100)])
        with (
            mock.patch.object(mm, "_intraday_history_start_boundary", return_value=real_datetime(2026, 8, 10).date()),
            mock.patch.object(mm, "_fetch_intraday_for_day") as fetch,
        ):
            mm.backfill_historical_intraday(conn, "SPY", today=real_datetime(2026, 8, 11).date())
        fetch.assert_not_called()  # only missing day in range is 8/10, which is already covered
        conn.close()


def test_backfill_historical_intraday_fetches_a_genuinely_missing_trading_day():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        with (
            mock.patch.object(mm, "_intraday_history_start_boundary", return_value=real_datetime(2026, 8, 10).date()),
            mock.patch.object(mm, "_fetch_intraday_for_day", return_value=[
                {"time": "2026-08-10T09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            ]) as fetch,
        ):
            result = mm.backfill_historical_intraday(conn, "SPY", today=real_datetime(2026, 8, 11).date())
        fetch.assert_called_once()
        assert fetch.call_args[0][1] == real_datetime(2026, 8, 10).date()
        assert result["new_bars"] == 1
        assert result["trading_days_with_data"] == 1
        conn.close()


def test_backfill_historical_intraday_skips_weekends():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        # 8/8/2026 and 8/9/2026 are a Saturday/Sunday.
        with (
            mock.patch.object(mm, "_intraday_history_start_boundary", return_value=real_datetime(2026, 8, 7).date()),
            mock.patch.object(mm, "_fetch_intraday_for_day", return_value=[]) as fetch,
        ):
            mm.backfill_historical_intraday(conn, "SPY", today=real_datetime(2026, 8, 10).date())
        fetched_days = {call.args[1] for call in fetch.call_args_list}
        assert real_datetime(2026, 8, 8).date() not in fetched_days
        assert real_datetime(2026, 8, 9).date() not in fetched_days
        assert real_datetime(2026, 8, 7).date() in fetched_days
        conn.close()


def test_backfill_historical_intraday_never_fetches_today():
    """Today is handled by run_collection_cycle's own regular intraday
    fetch - the historical backfill only ever covers yesterday and
    earlier, or it would duplicate that work."""
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        with (
            mock.patch.object(mm, "_intraday_history_start_boundary", return_value=real_datetime(2026, 8, 13).date()),
            mock.patch.object(mm, "_fetch_intraday_for_day", return_value=[]) as fetch,
        ):
            mm.backfill_historical_intraday(conn, "SPY", today=real_datetime(2026, 8, 14).date())
        fetched_days = {call.args[1] for call in fetch.call_args_list}
        assert real_datetime(2026, 8, 14).date() not in fetched_days
        conn.close()


def test_backfill_historical_intraday_reports_when_boundary_cannot_be_determined():
    temp_dir, patcher = _isolated_db()
    with temp_dir, patcher:
        conn = mm.connect()
        with mock.patch.object(mm, "_intraday_history_start_boundary", return_value=None):
            result = mm.backfill_historical_intraday(conn, "SPY", today=real_datetime(2026, 8, 14).date())
        assert result["status"] != "ok"
        conn.close()


def test_run_collection_cycle_includes_the_historical_backfill_and_survives_its_failure():
    temp_dir, patcher = _isolated_db()
    with (
        temp_dir, patcher,
        mock.patch.object(spy_scanner, "get_daily_history", return_value=_fake_daily_history(5)),
        mock.patch.object(spy_scanner, "get_intraday_history", return_value=[]),
        mock.patch.object(mm, "backfill_historical_intraday", side_effect=RuntimeError("provider hiccup")),
    ):
        result = mm.run_collection_cycle("SPY")

    # A backfill failure must never take down the whole cycle - the
    # daily layer (already proven reliable) still has to succeed.
    assert result["daily"]["new_bars"] == 5
    assert "failed" in result["intraday_historical_backfill"]["status"]
