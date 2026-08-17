"""Tests for the recent-data refresh and the session window selector.

Both exist because of the same defect: every measurement taken from this
store was describing 2008-2009. `load_sessions` ordered by bar_time
ascending, so `limit=250` truncated at the far end of history, and the
store itself stopped at 2021-05-06.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

import spy_backtest as bt
import spy_research_refresh as rr


def _store(sessions):
    """A features table with one row per session, newest last."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cols = ", ".join(f"{c} REAL" for c in bt.BACKTEST_COLUMNS
                     if c not in ("ticker", "bar_time", "session_date"))
    conn.execute(
        f"CREATE TABLE minute_features (ticker TEXT, bar_time TEXT, "
        f"session_date TEXT, {cols}, PRIMARY KEY (ticker, bar_time))"
    )
    for day in sessions:
        for minute in range(3):
            conn.execute(
                "INSERT INTO minute_features (ticker, bar_time, session_date) "
                "VALUES (?,?,?)",
                ("SPY", f"{day}T09:3{minute}:00", day),
            )
    conn.commit()
    return conn


SESSIONS = [f"2026-08-{d:02d}" for d in range(1, 11)]


def test_limit_alone_still_takes_the_oldest_sessions():
    """Unchanged default - callers relying on it must not silently shift."""
    conn = _store(SESSIONS)
    got = [s for s, _rows in bt.load_sessions(conn, limit=3)]
    assert got == SESSIONS[:3]


def test_newest_takes_the_most_recent_sessions():
    """The actual defect: limit=250 sampled 2008-2009 because the scan is
    ordered ascending, so the limit truncates at the wrong end."""
    conn = _store(SESSIONS)
    got = [s for s, _rows in bt.load_sessions(conn, limit=3, newest=True)]
    assert got == SESSIONS[-3:]


def test_since_and_until_bound_the_window():
    conn = _store(SESSIONS)
    got = [s for s, _rows in bt.load_sessions(
        conn, since="2026-08-04", until="2026-08-06")]
    assert got == ["2026-08-04", "2026-08-05", "2026-08-06"]


def test_a_gap_in_the_data_never_yields_more_sessions_than_asked():
    """This store has a five-year hole in it. The scan spans first..last,
    which is only the requested set while those dates are contiguous - a
    window that quietly returned extra sessions would corrupt every number
    measured from it."""
    conn = _store(["2021-05-05", "2021-05-06"] + SESSIONS)
    got = [s for s, _rows in bt.load_sessions(conn, limit=4, newest=True)]
    assert len(got) == 4
    assert got == SESSIONS[-4:]


def test_every_yielded_session_carries_its_own_rows_only():
    conn = _store(SESSIONS)
    for session, rows in bt.load_sessions(conn, limit=4, newest=True):
        assert rows
        assert {r["session_date"] for r in rows} == {session}


def test_an_empty_window_yields_nothing_rather_than_everything():
    conn = _store(SESSIONS)
    assert list(bt.load_sessions(conn, since="2030-01-01")) == []


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def test_timesales_rows_are_converted_with_a_session_flag():
    rows = rr._rows_from_timesales([
        {"time": "2026-08-17T09:30:00", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 100, "vwap": 1.2},
    ])
    assert len(rows) == 1
    assert rows[0][0] == "SPY"
    assert rows[0][1] == "2026-08-17T09:30:00"
    assert rows[0][-1] in (0, 1, True, False)


def test_malformed_bars_are_skipped_not_fatal():
    """A provider hiccup must not abort an ingest midway and leave the
    store half-written."""
    rows = rr._rows_from_timesales([
        {"time": "2026-08-17T09:30:00", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 100},
        {"time": "bad"},
        {"open": 1.0},
        {"time": "2026-08-17T09:31:00", "open": None, "high": 2.0,
         "low": 0.5, "close": 1.5},
        {"time": "2026-08-17T09:32:00", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 10},
    ])
    assert [r[1] for r in rows] == [
        "2026-08-17T09:30:00", "2026-08-17T09:32:00"]


def test_refresh_on_no_bars_is_a_no_op():
    assert rr.refresh(None, [])["bars_new"] == 0
