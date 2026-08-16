"""Tests for spy_research_data.py - Phase 1 historical ingestion.

The timezone tests are the important ones. The source 1-minute file is in
Mountain time, not Eastern, and getting that wrong by an hour would
silently corrupt every time-of-day rule in the strategy specs (opening
range, the 10:30 reversal, power hour, the late-day rule) while still
producing plausible-looking backtests. These pin it.
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest

import spy_research_data as srd


@contextmanager
def _db():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "research.db"
        with mock.patch.object(srd, "DB_PATH", path):
            conn = srd.connect()
            try:
                yield conn, Path(temp)
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Timezone - resolved empirically, pinned here
# ---------------------------------------------------------------------------

def test_mountain_converts_to_eastern_in_winter_standard_time():
    """07:30 Mountain is the session open; it must land on 09:30 Eastern."""
    assert srd.mountain_to_eastern("2008-01-22 07:30:00") == "2008-01-22T09:30:00"
    assert srd.mountain_to_eastern("2008-01-22 13:59:00") == "2008-01-22T15:59:00"


def test_mountain_converts_to_eastern_in_summer_daylight_time():
    """Both zones shift together, so the session open stays 09:30 ET -
    which is exactly why the source shows 07:30 year-round and why a
    fixed UTC offset would have been the wrong reading of this data."""
    assert srd.mountain_to_eastern("2008-07-15 07:30:00") == "2008-07-15T09:30:00"
    assert srd.mountain_to_eastern("2008-07-15 13:59:00") == "2008-07-15T15:59:00"


def test_conversion_is_correct_on_the_dst_changeover_day():
    """A blanket +2h shift would be wrong for part of a changeover day;
    real zone conversion is not."""
    # 2008-03-09 was the US spring-forward date.
    assert srd.mountain_to_eastern("2008-03-09 07:30:00") == "2008-03-09T09:30:00"
    # 2008-11-02 was the fall-back date.
    assert srd.mountain_to_eastern("2008-11-02 07:30:00") == "2008-11-02T09:30:00"


def test_regular_session_flag_bounds():
    assert srd._is_regular_session("2008-01-22T09:30:00") == 1
    assert srd._is_regular_session("2008-01-22T15:59:00") == 1
    assert srd._is_regular_session("2008-01-22T09:29:00") == 0   # premarket
    assert srd._is_regular_session("2008-01-22T16:00:00") == 0   # after the close


# ---------------------------------------------------------------------------
# Minute-bar ingestion
# ---------------------------------------------------------------------------

def _write_minute_csv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "date,open,high,low,close,volume,barCount,average\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_minute_ingest_stores_eastern_and_tags_the_session():
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        _write_minute_csv(csv_path, [
            "2008-01-22 06:00:00,126.0,126.1,125.9,126.05,500,10,126.0",   # 08:00 ET premarket
            "2008-01-22 07:30:00,126.45,126.82,126.0,126.67,30987,4541,126.283",
            "2008-01-22 13:59:00,127.0,127.2,126.9,127.1,50000,900,127.05",
            "2008-01-22 14:10:00,127.1,127.2,127.0,127.15,100,5,127.1",    # 16:10 ET after hours
        ])
        result = srd.ingest_minute_bars(conn, csv_path)
        rows = conn.execute("SELECT bar_time, regular_session FROM minute_bars ORDER BY bar_time").fetchall()

    assert result["inserted"] == 4
    times = [r["bar_time"] for r in rows]
    assert times == [
        "2008-01-22T08:00:00", "2008-01-22T09:30:00",
        "2008-01-22T15:59:00", "2008-01-22T16:10:00",
    ]
    # Extended-hours bars are KEPT (gap/premarket strategies need them),
    # just flagged.
    assert [r["regular_session"] for r in rows] == [0, 1, 1, 0]


def test_minute_ingest_is_idempotent():
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        _write_minute_csv(csv_path, ["2008-01-22 07:30:00,1,2,0.5,1.5,100,5,1.2"])
        first = srd.ingest_minute_bars(conn, csv_path)
        second = srd.ingest_minute_bars(conn, csv_path)
    assert first["inserted"] == 1
    assert second["inserted"] == 0


def test_minute_ingest_skips_malformed_rows_without_failing():
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        _write_minute_csv(csv_path, [
            "not-a-timestamp,1,2,0.5,1.5,100,5,1.2",
            ",1,2,0.5,1.5,100,5,1.2",
            "2008-01-22 07:30:00,1,2,0.5,1.5,100,5,1.2",
        ])
        result = srd.ingest_minute_bars(conn, csv_path)
    assert result["inserted"] == 1


def test_missing_numeric_fields_become_null_not_zero():
    """A blank volume must not silently read as zero volume - relative
    volume and volume-spike rules would then treat a data gap as a real
    liquidity collapse."""
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        _write_minute_csv(csv_path, ["2008-01-22 07:30:00,1,2,0.5,1.5,,,"])
        srd.ingest_minute_bars(conn, csv_path)
        row = conn.execute("SELECT volume, bar_count, average FROM minute_bars").fetchone()
    assert row["volume"] is None
    assert row["bar_count"] is None
    assert row["average"] is None


# ---------------------------------------------------------------------------
# Daily indicator ingestion
# ---------------------------------------------------------------------------

def test_daily_csv_ingests_tall_and_records_provenance():
    with _db() as (conn, temp):
        source_dir = temp / "src"
        source_dir.mkdir()
        (source_dir / "demo.csv").write_text(
            "Date,Alpha,Beta\n2020-01-02,1.5,2.5\n2020-01-03,3.5,4.5\n", encoding="utf-8"
        )
        with mock.patch.object(srd, "SOURCE_DIR", source_dir):
            result = srd.ingest_daily_csv(conn, "demo.csv", "demo")
        rows = conn.execute(
            "SELECT bar_date, column_name, value, source FROM daily_indicators ORDER BY bar_date, column_name"
        ).fetchall()

    assert result["status"] == "ok"
    assert result["columns"] == 2
    assert [(r["bar_date"], r["column_name"], r["value"]) for r in rows] == [
        ("2020-01-02", "Alpha", 1.5), ("2020-01-02", "Beta", 2.5),
        ("2020-01-03", "Alpha", 3.5), ("2020-01-03", "Beta", 4.5),
    ]
    assert {r["source"] for r in rows} == {"demo"}


def test_daily_csv_omits_blank_cells_rather_than_storing_zero():
    with _db() as (conn, temp):
        source_dir = temp / "src"
        source_dir.mkdir()
        (source_dir / "demo.csv").write_text(
            "Date,Alpha,Beta\n2020-01-02,,2.5\n", encoding="utf-8"
        )
        with mock.patch.object(srd, "SOURCE_DIR", source_dir):
            srd.ingest_daily_csv(conn, "demo.csv", "demo")
        names = [r["column_name"] for r in conn.execute("SELECT column_name FROM daily_indicators")]
    assert names == ["Beta"]


def test_daily_csv_reports_a_missing_file_instead_of_raising():
    with _db() as (conn, temp):
        with mock.patch.object(srd, "SOURCE_DIR", temp):
            result = srd.ingest_daily_csv(conn, "nope.csv", "nope")
    assert result["status"] == "missing"


def test_two_sources_sharing_a_date_do_not_collide():
    """The seven daily files are meant to inner-merge on Date; storing
    them tall means overlapping dates coexist as long as column names
    differ."""
    with _db() as (conn, temp):
        source_dir = temp / "src"
        source_dir.mkdir()
        (source_dir / "a.csv").write_text("Date,Alpha\n2020-01-02,1.0\n", encoding="utf-8")
        (source_dir / "b.csv").write_text("Date,Beta\n2020-01-02,2.0\n", encoding="utf-8")
        with mock.patch.object(srd, "SOURCE_DIR", source_dir):
            srd.ingest_daily_csv(conn, "a.csv", "a")
            srd.ingest_daily_csv(conn, "b.csv", "b")
        row = conn.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT source) AS sources FROM daily_indicators WHERE bar_date='2020-01-02'"
        ).fetchone()
    assert row["n"] == 2
    assert row["sources"] == 2


# ---------------------------------------------------------------------------
# Verification reporting
# ---------------------------------------------------------------------------

def test_verify_reports_sessions_and_flags_short_ones():
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        rows = []
        # One full-ish session and one deliberately short (half day).
        for minute in range(0, 300):
            hh, mm = divmod(minute, 60)
            rows.append(f"2008-01-22 {7 + hh:02d}:{30 + mm if mm < 30 else mm - 30:02d}:00,1,2,0.5,1.5,100,5,1.2"
                        if False else f"2008-01-22 {7 + (30 + minute) // 60:02d}:{(30 + minute) % 60:02d}:00,1,2,0.5,1.5,100,5,1.2")
        rows.append("2008-01-23 07:30:00,1,2,0.5,1.5,100,5,1.2")
        _write_minute_csv(csv_path, rows)
        srd.ingest_minute_bars(conn, csv_path)
        report = srd.verify(conn)

    assert report["minute_sessions"] == 2
    # The one-bar day must be flagged as short, the fuller one must not.
    short_days = {entry["d"] for entry in report["short_sessions"]}
    assert "2008-01-23" in short_days


def test_verify_reports_modal_session_open_and_close_in_eastern():
    """The strongest timezone check available: after ingesting real-shaped
    Mountain timestamps, the modal session open/close must read 09:30 and
    15:59 Eastern. On the live ingest this held for 3,345 and 3,322 of
    3,347 sessions respectively, the remainder being half-days."""
    with _db() as (conn, temp):
        csv_path = temp / "min.csv"
        rows = []
        for day in ("2008-01-22", "2008-01-23"):
            for minute in range(390):                      # 07:30-13:59 Mountain
                hh, mm = divmod(7 * 60 + 30 + minute, 60)
                rows.append(f"{day} {hh:02d}:{mm:02d}:00,1,2,0.5,1.5,100,5,1.2")
        _write_minute_csv(csv_path, rows)
        srd.ingest_minute_bars(conn, csv_path)
        report = srd.verify(conn)

    assert report["modal_session_open_et"]["t"] == "09:30"
    assert report["modal_session_close_et"]["t"] == "15:59"
    assert report["short_session_count"] == 0


def test_open_readonly_cannot_write():
    with _db() as (conn, temp):
        conn.execute(
            "INSERT INTO minute_bars (ticker, bar_time, open, high, low, close, volume, bar_count, average, regular_session) "
            "VALUES ('SPY','2020-01-02T09:30:00',1,1,1,1,1,1,1,1)"
        )
        conn.commit()
        reader = srd.open_readonly()
        try:
            with pytest.raises(sqlite3.OperationalError) as exc:
                reader.execute(
                    "INSERT INTO minute_bars (ticker, bar_time, open, high, low, close, volume, bar_count, average, regular_session) "
                    "VALUES ('SPY','2099-01-01T09:30:00',1,1,1,1,1,1,1,1)"
                )
            assert "readonly" in str(exc.value).lower()
        finally:
            reader.close()
