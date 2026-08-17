"""Tests for spy_intraday_features.py - Phase 2 intraday feature engine.

The no-lookahead tests are the point of this file. Every feature here is
meant to be computable in real time at the bar it is stamped on, and a
leak would produce a backtest that looks profitable and cannot be traded.
The truncation test is the strongest available check: a feature's value at
bar i must be identical whether it was computed over the whole session or
over a session that ends at bar i, because in live trading only the latter
exists.

The build-path tests guard two optimisations that made a 40-session
rebuild go from "times out at 120s" to ~0.6s. Both changed *how much data
is read*, not what is computed, so they need a test proving results are
byte-identical either way.
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest

import spy_intraday_features as sif
import spy_research_data as srd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@contextmanager
def _db():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "research.db"
        with mock.patch.object(srd, "DB_PATH", path):
            conn = sif.connect()
            try:
                yield conn
            finally:
                conn.close()


def _bar(day: str, hh: int, mm: int, price: float, volume: float = 1000.0, spread: float = 0.10):
    return {
        "bar_time": f"{day}T{hh:02d}:{mm:02d}:00",
        "open": price,
        "high": price + spread,
        "low": price - spread,
        "close": price,
        "volume": volume,
        "regular_session": 1 if (9 * 60 + 30) <= (hh * 60 + mm) <= (15 * 60 + 59) else 0,
    }


def _session(day: str, prices, start_minute: int = 9 * 60 + 30, volume: float = 1000.0):
    """A regular-session bar sequence starting at the open."""
    bars = []
    for offset, price in enumerate(prices):
        hh, mm = divmod(start_minute + offset, 60)
        bars.append(_bar(day, hh, mm, price, volume=volume))
    return bars


def _insert_bars(conn, bars, ticker="SPY"):
    conn.executemany(
        "INSERT OR REPLACE INTO minute_bars "
        "(ticker, bar_time, open, high, low, close, volume, bar_count, average, regular_session) "
        "VALUES (?,?,?,?,?,?,?,NULL,NULL,?)",
        [(ticker, b["bar_time"], b["open"], b["high"], b["low"], b["close"],
          b["volume"], b["regular_session"]) for b in bars],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# No-lookahead - the core guarantee
# ---------------------------------------------------------------------------

def test_every_feature_is_identical_when_the_session_is_truncated_at_that_bar():
    """The strongest no-lookahead check there is.

    Live, at 10:15, bars after 10:15 do not exist. So the row stamped
    10:15 must be unchanged when the later bars are removed. Any feature
    that peeks forward - a session high computed over the whole day, an
    opening range that used the eventual close - fails here."""
    prices = [500 + (i % 17) * 0.4 - (i % 7) * 0.3 for i in range(120)]
    bars = _session("2024-03-14", prices)
    context = sif.SessionContext(
        prev_day_high=505.0, prev_day_low=495.0, prev_day_close=499.0, atr_14=4.0
    )

    full = sif.compute_session_features(bars, context)
    assert len(full) == len(bars)

    for index in (0, 1, 5, 15, 30, 45, 90, 119):
        truncated = sif.compute_session_features(bars[: index + 1], context)
        assert truncated[index] == full[index], (
            f"bar {index} ({full[index]['bar_time']}) changed when later bars were "
            f"removed - a feature is reading the future"
        )


def test_session_context_never_sees_the_session_it_describes():
    """ContextBuilder must hand out a context built only from earlier
    sessions. Observing the current session before asking for its context
    would leak that day's own high/low into prev-day levels."""
    builder = sif.ContextBuilder()
    builder.observe("2024-03-12", {"open": 100, "high": 110, "low": 90, "close": 105})
    builder.observe("2024-03-13", {"open": 105, "high": 120, "low": 100, "close": 118})

    context = builder.context_for("2024-03-14")
    assert context.prev_day_high == 120       # from 03-13, the last observed
    assert context.prev_day_low == 100
    assert context.prev_day_close == 118

    # Observing 03-14 must not retroactively change what 03-14 was told.
    builder.observe("2024-03-14", {"open": 118, "high": 200, "low": 50, "close": 60})
    assert context.prev_day_high == 120


def test_opening_range_is_flagged_forming_until_its_window_completes():
    """While the window is still open the level is the running extreme -
    legitimately knowable, no lookahead - but `state` must say FORMING so
    no ORB strategy trades a level that has not finished forming."""
    bars = _session("2024-03-14", [500 + i * 0.1 for i in range(60)])
    rows = sif.compute_session_features(bars, sif.SessionContext(atr_14=4.0))

    assert rows[10]["or30_state"] == "FORMING"
    assert rows[10]["or30_high"] == pytest.approx(501.1)   # running high, not the final level
    assert rows[5]["or5_state"] != "FORMING", "5-min range completes at minute 5"


def test_opening_range_level_freezes_once_its_window_closes():
    """The contract every ORB strategy depends on: after the window
    closes the level never moves again, so a break is measured against a
    fixed reference rather than a high-water mark that keeps rising."""
    bars = _session("2024-03-14", [500 + i * 0.1 for i in range(60)])
    rows = sif.compute_session_features(bars, sif.SessionContext(atr_14=4.0))

    settled = rows[30]["or30_high"]
    assert settled == pytest.approx(503.0)
    for row in rows[30:]:
        assert row["or30_high"] == pytest.approx(settled), "opening range moved after forming"
    assert rows[35]["or30_state"] == "BROKEN_UP"


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------

def test_vwap_matches_a_hand_computed_typical_price_average():
    bars = _session("2024-03-14", [100.0, 102.0], volume=1000.0)
    rows = sif.compute_session_features(bars, sif.SessionContext())

    first_typical = (100.10 + 99.90 + 100.0) / 3
    assert rows[0]["vwap"] == pytest.approx(first_typical)

    second_typical = (102.10 + 101.90 + 102.0) / 3
    expected = (first_typical * 1000 + second_typical * 1000) / 2000
    assert rows[1]["vwap"] == pytest.approx(expected)


def test_vwap_restarts_each_session_rather_than_carrying_over():
    """Session-anchored VWAP is the one traders actually use; a running
    VWAP that never resets would drift permanently away from price."""
    day_one = sif.compute_session_features(
        _session("2024-03-14", [100.0] * 30), sif.SessionContext()
    )
    day_two = sif.compute_session_features(
        _session("2024-03-15", [200.0] * 30), sif.SessionContext()
    )
    assert day_one[-1]["vwap"] == pytest.approx(100.0, abs=0.01)
    assert day_two[0]["vwap"] == pytest.approx(200.0, abs=0.01)


# ---------------------------------------------------------------------------
# Prior-week levels - incremental tracking must match brute force
# ---------------------------------------------------------------------------

def test_prev_week_levels_match_a_brute_force_recomputation():
    """ContextBuilder tracks the previous week incrementally in O(1). The
    original O(N) rescan was correct but far too slow; this pins the fast
    version to the same answers."""
    from datetime import date, timedelta

    sessions = []
    start = date(2024, 3, 4)          # a Monday
    day, index = start, 0
    while len(sessions) < 20:
        if day.weekday() < 5:
            sessions.append((day.isoformat(), {
                "open": 100 + index, "high": 105 + index,
                "low": 95 + index, "close": 102 + index,
            }))
            index += 1
        day += timedelta(days=1)

    builder = sif.ContextBuilder()
    for position, (session, ohlc) in enumerate(sessions):
        context = builder.context_for(session)

        current_week = date.fromisoformat(session).isocalendar()[:2]
        earlier = [(d, o) for d, o in sessions[:position]
                   if date.fromisoformat(d).isocalendar()[:2] < current_week]
        if earlier:
            last_week = date.fromisoformat(earlier[-1][0]).isocalendar()[:2]
            week = [o for d, o in earlier
                    if date.fromisoformat(d).isocalendar()[:2] == last_week]
            assert context.prev_week_high == max(o["high"] for o in week)
            assert context.prev_week_low == min(o["low"] for o in week)
            assert context.prev_week_close == week[-1]["close"]
        else:
            assert context.prev_week_high is None

        builder.observe(session, ohlc)


# ---------------------------------------------------------------------------
# Build path - the two performance fixes must not change results
# ---------------------------------------------------------------------------

def test_load_session_bars_does_not_leak_into_the_neighbouring_day():
    """Bars are fetched by a text range on the primary key rather than
    substr(), because substr() defeated the index. The range bound must
    still stop exactly at midnight."""
    with _db() as conn:
        _insert_bars(conn, _session("2024-03-14", [100.0] * 5) + _session("2024-03-15", [200.0] * 5))
        bars = sif.load_session_bars(conn, "2024-03-14")

    assert len(bars) == 5
    assert all(b["bar_time"].startswith("2024-03-14") for b in bars)


def test_building_a_subset_gives_the_same_rows_as_building_everything():
    """A subset build skips reading bars for sessions it is not building.
    If that skipping dropped context the rebuilt rows would differ from a
    full build - this proves they do not."""
    days = [f"2024-03-{d:02d}" for d in (11, 12, 13, 14, 15, 18, 19, 20)]
    with _db() as conn:
        for offset, day in enumerate(days):
            _insert_bars(conn, _session(day, [100 + offset + i * 0.05 for i in range(40)]))

        sif.build_features(conn, sessions=days, progress_every=0)
        full = {r["bar_time"]: dict(r) for r in
                conn.execute("SELECT * FROM minute_features ORDER BY bar_time")}

        conn.execute("DELETE FROM minute_features")
        conn.commit()
        sif.build_features(conn, sessions=days[-2:], progress_every=0)
        subset = {r["bar_time"]: dict(r) for r in
                  conn.execute("SELECT * FROM minute_features ORDER BY bar_time")}

    assert subset, "subset build produced nothing"
    assert set(subset) < set(full), "subset build wrote rows outside its target sessions"
    for bar_time, row in subset.items():
        assert row == full[bar_time], f"{bar_time} differs between subset and full build"


def test_all_session_ohlc_matches_per_session_aggregation():
    """The single windowed query replaced pulling every bar into Python."""
    days = ["2024-03-14", "2024-03-15"]
    with _db() as conn:
        for offset, day in enumerate(days):
            _insert_bars(conn, _session(day, [100 + offset * 10 + i * 0.5 for i in range(20)]))
        combined = dict(sif.all_session_ohlc(conn))
        for day in days:
            expected = sif._session_ohlc(sif.load_session_bars(conn, day))
            assert combined[day] == pytest.approx(expected)


def test_all_session_ohlc_ignores_extended_hours_bars():
    """Prior-day levels are regular-session levels; a thin premarket print
    must not become the day's high."""
    with _db() as conn:
        bars = _session("2024-03-14", [100.0] * 10)
        bars.append(_bar("2024-03-14", 8, 0, 500.0))      # premarket spike
        _insert_bars(conn, bars)
        ohlc = dict(sif.all_session_ohlc(conn))
    assert ohlc["2024-03-14"]["high"] == pytest.approx(100.10)


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

def test_connect_adds_columns_missing_from_an_existing_table():
    """CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so a
    newly declared feature column would otherwise be missing at insert
    time. This is the exact failure that broke market_memory's vwap
    rollout, hence a direct guard here."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "research.db"
        with mock.patch.object(srd, "DB_PATH", path):
            conn = sif.connect()
            conn.execute("DROP TABLE minute_features")
            conn.execute(
                "CREATE TABLE minute_features ("
                "ticker TEXT NOT NULL, bar_time TEXT NOT NULL, session_date TEXT NOT NULL, "
                "PRIMARY KEY (ticker, bar_time))"
            )
            conn.commit()

            added = sif._migrate_columns(conn)
            assert "close" in added and "vwap" in added and "regime" in added

            columns = {r["name"] for r in conn.execute("PRAGMA table_info(minute_features)")}
            for declared, _ in sif._declared_columns():
                assert declared in columns
            conn.close()


def test_schema_parser_ignores_sql_comments_and_rejects_odd_identifiers():
    """A `-- comment` line inside the table body was being parsed as a
    column, producing `ALTER TABLE ... ADD COLUMN --` and failing with a
    bare "incomplete input". Comments are valid SQL and the schema uses
    them, so the parser has to cope."""
    declared = dict(sif._declared_columns())
    assert "--" not in declared
    assert not any(name.startswith("-") for name in declared)
    for name, column_type in declared.items():
        assert name.replace("_", "").isalnum(), f"{name!r} is not a plain identifier"
        assert column_type.upper() in {"REAL", "INTEGER", "TEXT", "BLOB", "NUMERIC"}
    # The commented Tier-2 block must still have been picked up.
    assert declared.get("adx_14") == "REAL"
    assert declared.get("structure") == "TEXT"


def test_every_declared_column_is_actually_populated_by_the_engine():
    """Guards the gap that left `close` declared but never written: a
    column in FEATURE_COLUMNS that the compute step never produces would
    silently store NULL for all history."""
    bars = _session("2024-03-14", [500 + i * 0.2 for i in range(60)])
    row = sif.compute_session_features(bars, sif.SessionContext(atr_14=4.0))[-1]
    for column in sif.FEATURE_COLUMNS:
        assert column in row, f"{column} is declared but never computed"


def test_ohlcv_is_stored_so_consumers_need_no_join():
    with _db() as conn:
        _insert_bars(conn, _session("2024-03-14", [100.0, 101.0, 102.0]))
        sif.build_features(conn, sessions=["2024-03-14"], progress_every=0)
        row = conn.execute(
            "SELECT open, high, low, close, volume FROM minute_features ORDER BY bar_time"
        ).fetchone()
    assert row["close"] == pytest.approx(100.0)
    assert row["high"] == pytest.approx(100.10)
    assert row["volume"] == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_alignment_reports_strong_only_when_all_timeframes_agree():
    assert sif._alignment(["UP", "UP", "UP", "UP"])[0] == "STRONG_BULLISH"
    assert sif._alignment(["DOWN", "DOWN", "DOWN", "DOWN"])[0] == "STRONG_BEARISH"
    assert sif._alignment(["UP", "UP", "DOWN", "DOWN"])[0] == "NEUTRAL"


def test_unformed_timeframes_lean_directional_but_never_reach_strong():
    """Early in a session the 60-minute trend is UNKNOWN. An unknown must
    not count as disagreement - that would suppress every valid morning
    signal - but it must also not be counted as agreement, or two formed
    timeframes would claim the confidence of four."""
    label, score = sif._alignment(["UP", "UP", "UNKNOWN", "UNKNOWN"])
    assert label == "BULLISH"
    assert score > 0
    assert sif._alignment(["UNKNOWN"] * 4) == ("UNKNOWN", 0)


def test_day_type_stays_forming_until_there_is_enough_session_to_judge():
    early = sif.classify_day_type(
        minutes_since_open=3, gap_pct=0.1, session_open=500.0, close=500.2,
        session_high=500.3, session_low=499.9, atr=4.0, vwap_crosses=0,
        or30_state="FORMING",
    )
    assert early == "FORMING"
