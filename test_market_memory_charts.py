"""Tests for market_memory_charts.py - the read-only rendering layer.

These exercise real behavior rather than "it ran": that the reader
genuinely cannot write, that lines are not drawn across data gaps, that
VWAP is never joined across a session boundary, that dense series keep
their extremes, and that the summary card reports pattern performance as
edge over the base rate rather than a misleading raw win rate.
"""

from __future__ import annotations

import math
import sqlite3
import tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest import mock

import pytest

import market_memory as mm
import market_memory_charts as mmc
import market_data as spy_scanner
import discord_transport


def _build_db(db_path: Path, *, daily: int = 400, sessions: int = 3, with_features: bool = True) -> None:
    """A realistic synthetic store built through market_memory's own
    ingestion, so the fixture cannot drift from the real schema."""
    with mock.patch.object(mm, "DB_PATH", db_path):
        conn = mm.connect()
        price = 100.0
        daily_rows = []
        for i in range(daily):
            price += 0.35 + 1.6 * math.sin(i / 9.0)
            daily_rows.append((
                f"{2020 + i // 252:04d}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" if False else f"d{i:05d}",
                price - 0.4, price + 1.4 + abs(math.sin(i / 4.0)), price - 1.4 - abs(math.cos(i / 6.0)),
                price, 1_000_000 + (i % 23) * 40_000,
            ))
        # Daily bar_times must look like real dates for date labelling.
        daily_rows = [
            (f"20{20 + i // 252:02d}-{((i // 21) % 12) + 1:02d}-{(i % 28) + 1:02d}", *row[1:])
            for i, row in enumerate(daily_rows)
        ]
        # De-duplicate any synthetic collisions.
        seen, unique = set(), []
        for row in daily_rows:
            if row[0] in seen:
                continue
            seen.add(row[0])
            unique.append(row)

        intraday_rows = []
        for session in range(sessions):
            base = 500.0 + session * 3
            for i in range(78):
                hour, minute = divmod(i * 5, 60)
                stamp = f"2026-08-{10 + session:02d}T{9 + hour:02d}:{minute:02d}:00"
                value = base + math.sin(i / 6.0) * 2
                intraday_rows.append((stamp, value - 0.2, value + 0.6, value - 0.6, value, 50_000 + i * 500))

        if with_features:
            mm._ingest_and_process(conn, "SPY", "daily", unique)
            mm._ingest_and_process(conn, "SPY", "5min", intraday_rows)
            mm.backfill_pattern_outcomes(conn, "SPY", "daily")
        else:
            mm.store_bars(conn, "SPY", "daily", unique)
            mm.store_bars(conn, "SPY", "5min", intraday_rows)
        conn.commit()
        conn.close()


@contextmanager
def _store(**kwargs):
    """Builds a temp market-memory store and yields (read-only conn,
    output dir). Uses tempfile directly rather than pytest's tmp_path -
    this checkout hits PermissionError on pytest's own tmpdir root (see
    CLAUDE.md's documented environment note), and every existing test in
    this repo works around it the same way."""
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "mm.db"
        out_dir = Path(temp) / "charts"
        _build_db(db_path, **kwargs)
        with mock.patch.object(mmc, "DB_PATH", db_path), mock.patch.object(mmc, "CHART_DIR", out_dir):
            conn = mmc.open_readonly()
            try:
                yield conn, out_dir, db_path
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------

def test_reader_physically_cannot_write():
    """The chart job runs inside the live information engine. If this
    handle could write, a rendering bug could corrupt the research
    store; market_memory.connect() by contrast opens read-write and runs
    executescript(SCHEMA)."""
    with _store() as (conn, _out, _db):
        with pytest.raises(sqlite3.OperationalError) as exc:
            conn.execute("INSERT INTO bars (ticker, timeframe, bar_time, open, high, low, close, volume) "
                         "VALUES ('SPY','daily','9999-01-01',1,1,1,1,1)")
        assert "readonly" in str(exc.value).lower()


def test_charts_module_does_not_import_market_memory():
    """Isolation invariant documented in run_market_memory_collection.ps1:
    the live engine must not import market_memory."""
    source = Path("market_memory_charts.py").read_text(encoding="utf-8")
    assert "import market_memory" not in source


# ---------------------------------------------------------------------------
# Series shaping - the corrections that matter
# ---------------------------------------------------------------------------

def test_segments_never_bridges_a_none_gap():
    """sma_200 is NULL for the first 199 bars. Drawing straight through
    that gap would imply history that does not exist."""
    assert mmc._segments([None, None, 1.0, 2.0, None, 3.0, 4.0]) == [
        [(2, 1.0), (3, 2.0)],
        [(5, 3.0), (6, 4.0)],
    ]


def test_segments_drops_isolated_single_points():
    assert mmc._segments([None, 5.0, None]) == []


def test_session_segments_splits_vwap_at_every_session_open():
    rows = [{"bar_time": f"2026-08-1{d}T09:{m:02d}:00"} for d in (0, 0, 1, 1) for m in (30, 35)][:4]
    rows = [
        {"bar_time": "2026-08-10T09:30:00"},
        {"bar_time": "2026-08-10T09:35:00"},
        {"bar_time": "2026-08-11T09:30:00"},
        {"bar_time": "2026-08-11T09:35:00"},
    ]
    runs = mmc._session_segments(rows, [10.0, 11.0, 90.0, 91.0])
    assert len(runs) == 2
    assert runs[0] == [(0, 10.0), (1, 11.0)]
    assert runs[1] == [(2, 90.0), (3, 91.0)]


def test_decimation_preserves_a_single_bar_spike():
    """Stride-sampling would delete it; min/max bucketing must not."""
    points = [(i, 100.0) for i in range(4000)]
    points[1234] = (1234, 900.0)
    reduced = mmc._decimate(points, 300)
    assert len(reduced) < len(points)
    assert any(value == 900.0 for _, value in reduced)


def test_display_time_normalizes_both_stored_encodings_to_the_same_label():
    """The store holds Robinhood 'Z' (UTC) bars and Tradier naive-ET
    bars. The same session open must label identically in both."""
    assert mmc._display_time("2026-03-02T14:30:00Z") == "09:30"
    assert mmc._display_time("2026-08-14T09:30:00") == "09:30"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_renders_focused_phone_readable_charts_from_a_real_synthetic_store():
    from PIL import Image

    with _store() as (conn, out_dir, _db):
        boards = mmc.render_all(conn, "SPY", out_dir)
        assert {key for key, _, _ in boards} == {
            "session-price", "intraday-momentum", "short-trend", "macd",
            "year-trend", "volatility", "five-year-trend", "full-history",
        }
        for _, path, caption in boards:
            assert path.exists()
            assert path.stat().st_size > 10_000
            with Image.open(path) as image:
                assert image.size == (mmc.PANEL_W * 2, mmc.PANEL_H * 2)
            assert caption.strip()


def test_sparse_history_degrades_instead_of_raising():
    """Three daily bars and no intraday at all - the realistic first-run
    case. Nothing may raise."""
    with tempfile.TemporaryDirectory() as temp:
      db_path = Path(temp) / "sparse.db"
      out_dir = Path(temp) / "charts"
      with mock.patch.object(mm, "DB_PATH", db_path):
        conn = mm.connect()
        mm.store_bars(conn, "SPY", "daily", [
            ("2026-08-10", 100, 101, 99, 100, 1000),
            ("2026-08-11", 100, 102, 99, 101, 1000),
            ("2026-08-12", 101, 103, 100, 102, 1000),
        ])
        conn.commit()
        conn.close()
      with mock.patch.object(mmc, "DB_PATH", db_path):
        conn = mmc.open_readonly()
        boards = mmc.render_all(conn, "SPY", out_dir)
        conn.close()

    keys = {key for key, _, _ in boards}
    assert "session-price" not in keys  # no intraday bars at all -> skipped, not broken
    assert {"short-trend", "year-trend", "five-year-trend"} <= keys


def test_renders_when_every_feature_column_is_null():
    """Bars stored but features never computed - LEFT JOIN yields all
    None. This is the most likely crash and must not be one."""
    with _store(daily=120, sessions=2, with_features=False) as (conn, out_dir, _db):
        boards = mmc.render_all(conn, "SPY", out_dir)
        assert boards  # produced something rather than raising
        for _, path, _ in boards:
            assert path.exists()


# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------

def test_card_parses_into_a_discord_embed():
    with _store() as (conn, _out, _db):
        text = mmc.technicals_card_text(mmc.summarize(conn, "SPY"))
    embed = discord_transport.discord_card(text, footer_suffix="spy-technicals")
    assert "Technicals" in embed["title"]
    assert embed["fields"]
    for field in embed["fields"]:
        assert len(field["value"]) <= 1024, f"{field['name']} exceeds Discord's field limit"
    assert len(text) <= 5900


def test_card_states_pattern_edge_against_the_base_rate():
    """Regression guard for the reporting error this whole feature
    corrects: a bare win rate looks like an edge when SPY simply rises
    most windows. The card must show the base rate and express patterns
    relative to it."""
    with _store() as (conn, _out, _db):
        text = mmc.technicals_card_text(mmc.summarize(conn, "SPY"))
    assert "Base rate" in text
    assert "edge" in text.lower()
    assert "misleading" in text.lower()


def test_card_reports_market_condition_as_never_populated():
    """market_condition is genuinely never written by the collection
    cycle. Hiding that would misrepresent what is tracked."""
    with _store() as (conn, _out, _db):
        text = mmc.technicals_card_text(mmc.summarize(conn, "SPY"))
    assert "market_condition" in text
    assert "never written" in text


def test_summarize_on_an_empty_store_is_handled():
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "empty.db"
        with mock.patch.object(mm, "DB_PATH", db_path):
            mm.connect().close()
        with mock.patch.object(mmc, "DB_PATH", db_path):
            conn = mmc.open_readonly()
            summary = mmc.summarize(conn, "SPY")
            text = mmc.technicals_card_text(summary)
            conn.close()
    assert summary["empty"] is True
    assert "No stored history" in text


# ---------------------------------------------------------------------------
# Fingerprint - drives the job's "don't repost identical charts" guard
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_for_unchanged_data():
    with _store() as (conn, _out, _db):
        assert mmc.data_fingerprint(conn, "SPY") == mmc.data_fingerprint(conn, "SPY")


def test_fingerprint_changes_when_a_new_bar_arrives():
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "fp.db"
        _build_db(db_path, daily=60, sessions=1)
        with mock.patch.object(mmc, "DB_PATH", db_path):
            conn = mmc.open_readonly()
            before = mmc.data_fingerprint(conn, "SPY")
            conn.close()
        with mock.patch.object(mm, "DB_PATH", db_path):
            conn = mm.connect()
            mm.store_bars(conn, "SPY", "daily", [("2099-01-01", 900, 901, 899, 900, 1000)])
            conn.commit()
            conn.close()
        with mock.patch.object(mmc, "DB_PATH", db_path):
            conn = mmc.open_readonly()
            after = mmc.data_fingerprint(conn, "SPY")
            conn.close()
    assert before != after


def test_fingerprint_changes_when_render_version_is_bumped():
    """Without this, a fix to the drawing code would stay invisible
    until the next new bar arrived."""
    with _store() as (conn, _out, _db):
        before = mmc.data_fingerprint(conn, "SPY")
        with mock.patch.object(mmc, "RENDER_VERSION", "spy-technicals-test-bump"):
            after = mmc.data_fingerprint(conn, "SPY")
    assert before != after


# ---------------------------------------------------------------------------
# Job wiring
# ---------------------------------------------------------------------------

def test_spy_technicals_job_skips_discord_when_the_data_is_unchanged():
    """The whole cadence design rests on this: the job ticks every 20
    minutes but the underlying store refreshes once a day, so a second
    run against identical data must not repost five images."""
    import upgrade_batch_44

    state: dict = {}

    def fake_state_json(_conn, key):
        return dict(state.get(key, {}))

    def fake_set_state_json(_conn, key, value):
        state[key] = value

    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "mm.db"
        _build_db(db_path, daily=260, sessions=2)
        with (
            mock.patch.object(mmc, "DB_PATH", db_path),
            mock.patch.object(mmc, "CHART_DIR", Path(temp) / "charts"),
            mock.patch.object(upgrade_batch_44, "_state_json", fake_state_json),
            mock.patch.object(upgrade_batch_44, "_set_state_json", fake_set_state_json),
            mock.patch.object(upgrade_batch_44, "_require_dashboard", return_value=True) as card,
            mock.patch.object(upgrade_batch_44, "_replace_chart_message", return_value=True) as upload,
            mock.patch.object(upgrade_batch_44, "_engine") as engine,
        ):
            engine.return_value.store_observation = mock.Mock()
            first = upgrade_batch_44.spy_technicals_job(object())
            uploads_after_first = upload.call_count
            second = upgrade_batch_44.spy_technicals_job(object())

    assert uploads_after_first == 8
    assert card.call_count == 1
    assert upload.call_count == uploads_after_first  # no new uploads on the second run
    assert "no repost" in second
    assert "refreshed" in first


def test_spy_technicals_job_reports_softly_when_the_database_is_missing():
    """A research-store problem must never mark the live engine
    unhealthy - it has nothing to do with trading."""
    import upgrade_batch_44

    with mock.patch.object(mmc, "DB_PATH", Path("does-not-exist-anywhere.db")):
        result = upgrade_batch_44.spy_technicals_job(object())
    assert "unavailable" in result
