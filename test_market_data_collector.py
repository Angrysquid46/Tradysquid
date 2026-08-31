from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import pytest

import local_information_engine as engine
import market_api_budget
import market_data_collector as collector
import market_data_store as store


# --- market_data_store.py ---------------------------------------------------

@pytest.fixture
def scratch_data_root(monkeypatch):
    root = Path(tempfile.mkdtemp()) / "market"
    monkeypatch.setattr(store, "DATA_ROOT", root)
    return root


def test_write_rows_creates_a_readable_parquet_file(scratch_data_root):
    rows = [
        {"symbol": "SPY", "bid": 763.0, "ask": 763.05},
        {"symbol": "SPY", "bid": 763.1, "ask": 763.15},
    ]
    path = store.write_quote("SPY", date(2026, 8, 24), datetime(2026, 8, 24, 9, 31, 0), rows)
    assert path is not None
    assert path.exists()
    glob = store.dataset_glob(store.QUOTES_DATASET, "SPY", date(2026, 8, 24))
    result = store.query(f"SELECT bid, ask FROM read_parquet('{glob}') ORDER BY bid")
    assert result == [{"bid": 763.0, "ask": 763.05}, {"bid": 763.1, "ask": 763.15}]


def test_write_rows_with_no_rows_writes_nothing(scratch_data_root):
    path = store.write_quote("SPY", date(2026, 8, 24), datetime(2026, 8, 24, 9, 31, 0), [])
    assert path is None
    assert not (scratch_data_root / "quotes").exists()


def test_partition_dir_layout_matches_instrument_year_month_day(scratch_data_root):
    result = store.partition_dir(store.CHAIN_DATASET, "SPY", date(2026, 8, 24))
    assert result == scratch_data_root / "chain" / "SPY" / "2026" / "08" / "2026-08-24"


def test_multiple_cycles_produce_multiple_immutable_part_files(scratch_data_root):
    store.write_quote("SPY", date(2026, 8, 24), datetime(2026, 8, 24, 9, 31, 0, 0), [{"a": 1}])
    store.write_quote("SPY", date(2026, 8, 24), datetime(2026, 8, 24, 9, 32, 0, 0), [{"a": 2}])
    directory = store.partition_dir(store.QUOTES_DATASET, "SPY", date(2026, 8, 24))
    files = sorted(directory.glob("*.parquet"))
    assert len(files) == 2


# --- classify_* --------------------------------------------------------------

def test_classify_quote_row_verified_real_for_clean_data():
    raw = {
        "symbol": "SPY", "bid": 763.0, "ask": 763.05, "last": 763.02,
        "bidsize": 100, "asksize": 50, "bid_date": 111, "ask_date": 112,
    }
    row, cls = collector.classify_quote_row(raw, datetime(2026, 8, 24, 9, 31))
    assert cls == collector.VERIFIED_REAL
    assert row["symbol"] == "SPY"
    assert row["bid"] == 763.0


def test_classify_quote_row_limited_when_dates_missing():
    raw = {"symbol": "SPY", "bid": 763.0, "ask": 763.05}
    _, cls = collector.classify_quote_row(raw, datetime(2026, 8, 24, 9, 31))
    assert cls == collector.REAL_WITH_LIMITATIONS


def test_classify_quote_row_rejected_when_bid_exceeds_ask():
    raw = {"symbol": "SPY", "bid": 764.0, "ask": 763.0, "bid_date": 1, "ask_date": 2}
    _, cls = collector.classify_quote_row(raw, datetime(2026, 8, 24, 9, 31))
    assert cls == collector.REJECTED


def test_classify_chain_row_carries_synchronized_underlying_price():
    contract = {
        "symbol": "SPY260824C00500000", "expiration_date": "2026-08-24",
        "strike": 500.0, "option_type": "call", "bid": 1.0, "ask": 1.05,
        "bid_date": 1, "ask_date": 2, "greeks": {"delta": 0.5},
    }
    underlying = {"bid": 763.0, "ask": 763.05, "last": 763.02}
    row, cls = collector.classify_chain_row(contract, underlying, datetime(2026, 8, 24, 9, 31))
    assert cls == collector.VERIFIED_REAL
    assert row["underlying_bid"] == 763.0
    assert row["delta"] == 0.5
    assert row["option_symbol"] == "SPY260824C00500000"


def test_classify_chain_row_rejected_when_bid_exceeds_ask():
    contract = {"symbol": "X", "bid": 5.0, "ask": 1.0, "bid_date": 1, "ask_date": 2}
    _, cls = collector.classify_chain_row(contract, {}, datetime(2026, 8, 24, 9, 31))
    assert cls == collector.REJECTED


def test_classify_bar_row_verified_real_for_complete_bar():
    raw = {"time": "t", "timestamp": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "vwap": 1.2}
    _, cls = collector.classify_bar_row(raw, "SPY", datetime(2026, 8, 24, 9, 31))
    assert cls == collector.VERIFIED_REAL


def test_classify_bar_row_limited_when_vwap_missing():
    raw = {"time": "t", "timestamp": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "vwap": None}
    _, cls = collector.classify_bar_row(raw, "SPY", datetime(2026, 8, 24, 9, 31))
    assert cls == collector.REAL_WITH_LIMITATIONS


def test_classify_bar_row_rejected_when_close_missing():
    raw = {"time": "t", "timestamp": 1, "open": 1, "high": 2, "low": 0.5, "close": None, "volume": 100, "vwap": 1.2}
    _, cls = collector.classify_bar_row(raw, "SPY", datetime(2026, 8, 24, 9, 31))
    assert cls == collector.REJECTED


# --- manifest bookkeeping -----------------------------------------------------

@pytest.fixture
def manifest_db(monkeypatch):
    engine.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    connection = engine.connect_db()
    yield connection
    connection.close()


def test_record_cycle_result_creates_row_and_increments_counters(manifest_db):
    collector.record_cycle_result(
        manifest_db, "2026-08-24", quote_written=True, chain_written=True
    )
    collector.record_cycle_result(
        manifest_db, "2026-08-24", quote_written=True, chain_written=False, api_errors=1
    )
    row = manifest_db.execute(
        "SELECT received_quote_minutes, received_chain_snapshots, api_errors "
        "FROM daily_data_manifest WHERE trading_day=?",
        ("2026-08-24",),
    ).fetchone()
    assert tuple(row) == (2, 1, 1)


def test_grade_day_a_for_near_complete_clean_day(manifest_db):
    for _ in range(390):
        collector.record_cycle_result(
            manifest_db, "2026-08-24", quote_written=True, chain_written=True
        )
    assert collector.grade_day(manifest_db, "2026-08-24") == "A"


def test_grade_day_b_for_ninety_percent(manifest_db):
    for _ in range(351):  # 90% of 390
        collector.record_cycle_result(
            manifest_db, "2026-08-24", quote_written=True, chain_written=True
        )
    assert collector.grade_day(manifest_db, "2026-08-24") == "B"


def test_grade_day_reject_when_manifest_row_missing(manifest_db):
    assert collector.grade_day(manifest_db, "2026-08-24") == "REJECT"


def test_grade_day_reject_when_mostly_missing(manifest_db):
    for _ in range(10):
        collector.record_cycle_result(
            manifest_db, "2026-08-24", quote_written=True, chain_written=True
        )
    assert collector.grade_day(manifest_db, "2026-08-24") == "REJECT"


# --- capture_cycle_job / bars_capture_job (mocked market_data) ---------------

def test_capture_cycle_job_writes_quote_and_chain_and_updates_manifest(
    manifest_db, monkeypatch, scratch_data_root
):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 31)
    )
    monkeypatch.setattr(
        collector.market_data, "get_quotes",
            lambda symbols, include_greeks=True, **kwargs: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
            collector.market_data, "get_expirations", lambda symbol, **kwargs: ["2026-08-24"]
    )
    monkeypatch.setattr(
        collector.market_data, "get_chain",
            lambda symbol, expiration, **kwargs: [{
            "symbol": "SPY260824C00500000", "expiration_date": "2026-08-24",
            "strike": 500.0, "option_type": "call", "bid": 1.0, "ask": 1.05,
            "bid_date": 1, "ask_date": 2, "greeks": {},
        }],
    )

    summary = collector.capture_cycle_job(manifest_db)
    assert "quote=OK" in summary
    assert "chain=OK" in summary

    row = manifest_db.execute(
        "SELECT received_quote_minutes, received_chain_snapshots FROM daily_data_manifest WHERE trading_day=?",
        ("2026-08-24",),
    ).fetchone()
    assert tuple(row) == (1, 1)


def test_capture_cycle_job_skips_chain_when_no_zero_dte_expiration(
    manifest_db, monkeypatch, scratch_data_root
):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 31)
    )
    monkeypatch.setattr(
        collector.market_data, "get_quotes",
            lambda symbols, include_greeks=True, **kwargs: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
            collector.market_data, "get_expirations", lambda symbol, **kwargs: ["2026-08-25"]
    )
    summary = collector.capture_cycle_job(manifest_db)
    assert "quote=OK" in summary
    assert "chain=MISS" in summary


def test_capture_cycle_job_counts_provider_failure_as_api_error_not_crash(
    manifest_db, monkeypatch, scratch_data_root
):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 31)
    )

    def boom(symbols, include_greeks=True):
        raise RuntimeError("provider down")

    monkeypatch.setattr(collector.market_data, "get_quotes", boom)
    monkeypatch.setattr(collector.market_data, "get_expirations", lambda symbol, **kwargs: [])
    summary = collector.capture_cycle_job(manifest_db)
    assert "errors=1" in summary
    row = manifest_db.execute(
        "SELECT api_errors FROM daily_data_manifest WHERE trading_day=?", ("2026-08-24",)
    ).fetchone()
    assert row[0] == 1


def test_capture_cycle_job_skips_quote_call_and_records_error_when_budget_gate_blocks(
    manifest_db, monkeypatch, scratch_data_root
):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 31)
    )

    def boom_if_called(*args, **kwargs):
        raise AssertionError("get_quotes should not be called while the budget gate blocks")

    monkeypatch.setattr(collector.market_data, "get_quotes", boom_if_called)
    monkeypatch.setattr(collector.market_data, "get_expirations", lambda symbol, **kwargs: [])
    monkeypatch.setattr(market_api_budget, "request_allowed", lambda priority: False)

    summary = collector.capture_cycle_job(manifest_db)
    assert "quote=MISS" in summary
    assert "errors=1" in summary
    row = manifest_db.execute(
        "SELECT api_errors FROM daily_data_manifest WHERE trading_day=?", ("2026-08-24",)
    ).fetchone()
    assert row[0] == 1


def test_capture_cycle_job_isolates_source_level_options_budget_denial(
    manifest_db, monkeypatch, scratch_data_root
):
    """Expiration lookup is real (not gated) so the block below is
    isolated to the chain-specific gate check, not incidental exception
    swallowing inside find_zero_dte_expiration."""
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 31)
    )
    monkeypatch.setattr(
        collector.market_data, "get_quotes",
            lambda symbols, include_greeks=True, **kwargs: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
            collector.market_data, "get_expirations", lambda symbol, **kwargs: ["2026-08-24"]
    )

    def boom_if_called(*args, **kwargs):
        raise collector.market_data.TradierError("shared budget denied")

    monkeypatch.setattr(collector.market_data, "get_chain", boom_if_called)
    summary = collector.capture_cycle_job(manifest_db)
    assert "quote=OK" in summary
    assert "chain=MISS" in summary
    assert "errors=1" in summary


def test_bars_capture_job_skipped_when_budget_gate_blocks(monkeypatch, scratch_data_root):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 33)
    )

    def boom_if_called(*args, **kwargs):
        raise AssertionError("Tradier should not be called while the budget gate blocks")

    monkeypatch.setattr(collector.market_data, "get_intraday_history_range", boom_if_called)
    monkeypatch.setattr(market_api_budget, "request_allowed", lambda priority: False)

    summary = collector.bars_capture_job(None)
    assert "skipped" in summary


def test_bars_capture_job_dedupes_against_already_written_bars(monkeypatch, scratch_data_root):
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 9, 33)
    )
    all_bars = [
        {"time": "t1", "timestamp": 100, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "vwap": 1.1},
        {"time": "t2", "timestamp": 160, "open": 1.5, "high": 2, "low": 1, "close": 1.8, "volume": 20, "vwap": 1.6},
    ]
    monkeypatch.setattr(
        collector.market_data, "get_intraday_history_range",
        lambda symbol, interval, start, end: all_bars,
    )

    first = collector.bars_capture_job(None)
    assert "2 new bars written" in first

    # Second run sees the same two bars again (overlapping pull window) -
    # both should be deduped against what is already on disk.
    second = collector.bars_capture_job(None)
    assert "0 new bars written" in second


def _bar(at: datetime, value: float = 1.0):
    return {
        "time": at.isoformat(), "timestamp": int(at.timestamp()),
        "open": value, "high": value + 1, "low": value - 0.5,
        "close": value + 0.25, "volume": 10, "vwap": value,
    }


def test_ingest_bar_rows_partitions_each_bar_by_its_market_date(scratch_data_root):
    ct = ZoneInfo("America/Chicago")
    captured = datetime(2026, 8, 25, 8, 31, tzinfo=ct)
    result = collector.ingest_bar_rows(
        "SPY",
        [
            _bar(datetime(2026, 8, 24, 14, 59, tzinfo=ct)),
            _bar(datetime(2026, 8, 25, 8, 30, tzinfo=ct)),
        ],
        captured,
    )
    assert result["partitions"] == {"2026-08-24": 1, "2026-08-25": 1}
    for day in (date(2026, 8, 24), date(2026, 8, 25)):
        assert list(store.partition_dir(store.BARS_DATASET, "SPY", day).glob("*.parquet"))


def test_bars_capture_always_requests_current_session_separately(monkeypatch, scratch_data_root):
    ct = ZoneInfo("America/Chicago")
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct",
        lambda: datetime(2026, 8, 31, 8, 31, tzinfo=ct),
    )
    calls = []
    monkeypatch.setattr(
        collector.market_data,
        "get_intraday_history_range",
        lambda symbol, interval, start, end: calls.append((start, end)) or [],
    )
    collector.bars_capture_job(None)
    assert calls == [(date(2026, 8, 31), date(2026, 8, 31))]


def test_bars_capture_audits_current_day_even_when_provider_returns_no_rows(
    manifest_db, monkeypatch, scratch_data_root
):
    ct = ZoneInfo("America/Chicago")
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct",
        lambda: datetime(2026, 8, 31, 15, 30, tzinfo=ct),
    )
    monkeypatch.setattr(
        collector.market_data, "get_intraday_history_range",
        lambda symbol, interval, start, end: [],
    )
    monkeypatch.setattr(
        collector, "session_bar_completeness",
        lambda symbol, day: {
            "trading_day": day.isoformat(), "expected": 390, "received": 385,
            "missing": 5, "missing_periods": [], "complete": False,
        },
    )
    manifest_db.execute(
        "INSERT INTO engine_state(key,value,updated_at) VALUES(?,?,?)",
        (collector.BAR_BACKFILL_STATE_KEY, "2026-08-31", "now"),
    )
    manifest_db.commit()
    summary = collector.bars_capture_job(manifest_db)
    assert "incomplete=2026-08-31:5" in summary
    row = manifest_db.execute(
        "SELECT received_bar_minutes,bar_grade FROM daily_data_manifest "
        "WHERE trading_day='2026-08-31'"
    ).fetchone()
    assert tuple(row) == (385, "REJECT")


def test_bars_capture_backfills_each_prior_day_once_without_provider_cap(
    manifest_db, monkeypatch, scratch_data_root
):
    ct = ZoneInfo("America/Chicago")
    monkeypatch.setattr(collector.market_data, "TICKER", "SPY")
    monkeypatch.setattr(
        collector.market_data, "now_ct",
        lambda: datetime(2026, 8, 31, 8, 31, tzinfo=ct),
    )
    monkeypatch.setattr(collector, "BAR_BACKFILL_CALENDAR_DAYS", 3)
    monkeypatch.setattr(collector, "session_bar_completeness", lambda symbol, day: {
        "trading_day": day.isoformat(), "expected": 390, "received": 390,
        "missing": 0, "missing_periods": [], "complete": True,
    })
    calls = []
    monkeypatch.setattr(
        collector.market_data, "get_intraday_history_range",
        lambda symbol, interval, start, end: calls.append((start, end)) or [],
    )
    collector.bars_capture_job(manifest_db)
    assert calls == [
        (date(2026, 8, 31), date(2026, 8, 31)),
        (date(2026, 8, 28), date(2026, 8, 28)),
        (date(2026, 8, 29), date(2026, 8, 29)),
        (date(2026, 8, 30), date(2026, 8, 30)),
    ]
    calls.clear()
    collector.bars_capture_job(manifest_db)
    assert calls == [(date(2026, 8, 31), date(2026, 8, 31))]


def test_session_bar_completeness_reports_exact_gap(monkeypatch, scratch_data_root):
    ct = ZoneInfo("America/Chicago")
    day = date(2026, 8, 24)
    start = datetime(2026, 8, 24, 8, 30, tzinfo=ct)
    monkeypatch.setattr(collector, "expected_session_minutes", lambda value: 3)
    collector.ingest_bar_rows("SPY", [_bar(start), _bar(start + timedelta(minutes=2))], start)
    result = collector.session_bar_completeness("SPY", day)
    assert result["received"] == 2
    assert result["missing"] == 1
    assert result["missing_periods"] == [{
        "start": "2026-08-24T08:31:00-05:00",
        "end": "2026-08-24T08:31:00-05:00",
    }]


def test_record_bar_completeness_has_independent_bar_grade(manifest_db, monkeypatch):
    manifest_db.execute(
        "INSERT INTO daily_data_manifest "
        "(trading_day, expected_minutes, received_quote_minutes, received_chain_snapshots, grade) "
        "VALUES ('2026-08-24', 390, 390, 390, 'A')"
    )
    manifest_db.commit()
    monkeypatch.setattr(
        collector.market_data, "now_ct", lambda: datetime(2026, 8, 24, 15, 1)
    )
    collector.record_bar_completeness(manifest_db, {
        "trading_day": "2026-08-24", "received": 363, "complete": False,
        "missing_periods": [{"start": "x", "end": "y"}],
    })
    row = manifest_db.execute(
        "SELECT grade, received_bar_minutes, bar_grade FROM daily_data_manifest "
        "WHERE trading_day='2026-08-24'"
    ).fetchone()
    assert tuple(row) == ("A", 363, "REJECT")


def test_repair_bar_partitions_adds_correct_copy_without_deleting_source(scratch_data_root):
    ct = ZoneInfo("America/Chicago")
    monday = datetime(2026, 8, 24, 14, 59, tzinfo=ct)
    captured = datetime(2026, 8, 25, 8, 31, tzinfo=ct)
    source = store.write_bars("SPY", date(2026, 8, 25), captured, [
        collector.classify_bar_row(_bar(monday), "SPY", captured)[0]
    ])
    repaired = collector.repair_bar_partitions("SPY", captured)
    assert repaired == {"2026-08-24": 1}
    assert source.exists()
    assert list(store.partition_dir(store.BARS_DATASET, "SPY", date(2026, 8, 24)).glob("*.parquet"))


# --- expected_session_minutes (Phase 14 audit finding) -----------------------

def test_expected_session_minutes_full_day(monkeypatch):
    payload = {
        "calendar": {"days": {"day": [
            {"date": "2026-08-24", "status": "open",
             "open": {"start": "08:30", "end": "15:00"}},
        ]}}
    }
    monkeypatch.setattr(collector.market_data, "tradier_get", lambda path, params, **kwargs: payload)
    assert collector.expected_session_minutes(date(2026, 8, 24)) == 390


def test_expected_session_minutes_early_close(monkeypatch):
    payload = {
        "calendar": {"days": {"day": [
            {"date": "2026-11-27", "status": "early-close",
             "open": {"start": "08:30", "end": "12:00"}},
        ]}}
    }
    monkeypatch.setattr(collector.market_data, "tradier_get", lambda path, params, **kwargs: payload)
    assert collector.expected_session_minutes(date(2026, 11, 27)) == 210


def test_expected_session_minutes_falls_back_on_fetch_failure(monkeypatch):
    def _boom(path, params):
        raise RuntimeError("network down")

    monkeypatch.setattr(collector.market_data, "tradier_get", _boom)
    assert collector.expected_session_minutes(date(2026, 8, 24)) == collector.EXPECTED_RTH_MINUTES


def test_expected_session_minutes_falls_back_when_day_not_found(monkeypatch):
    payload = {"calendar": {"days": {"day": [{"date": "2026-08-25", "status": "open"}]}}}
    monkeypatch.setattr(collector.market_data, "tradier_get", lambda path, params, **kwargs: payload)
    assert collector.expected_session_minutes(date(2026, 8, 24)) == collector.EXPECTED_RTH_MINUTES


def test_expected_session_minutes_falls_back_on_closed_day(monkeypatch):
    payload = {"calendar": {"days": {"day": [{"date": "2026-12-25", "status": "closed"}]}}}
    monkeypatch.setattr(collector.market_data, "tradier_get", lambda path, params, **kwargs: payload)
    assert collector.expected_session_minutes(date(2026, 12, 25)) == collector.EXPECTED_RTH_MINUTES


def test_ensure_manifest_row_uses_expected_session_minutes(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "DB_PATH", tmp_path / "engine.db")
    connection = engine.connect_db()
    monkeypatch.setattr(
        collector, "expected_session_minutes", lambda trading_day: 210
    )
    collector.ensure_manifest_row(connection, "2026-11-27")
    row = connection.execute(
        "SELECT expected_minutes FROM daily_data_manifest WHERE trading_day=?",
        ("2026-11-27",),
    ).fetchone()
    assert row[0] == 210


def test_live_bar_capture_runs_each_minute_for_minute_scale_traders():
    job = next(job for job in engine.JOBS if job.name == "spy-bars-capture")
    assert job.interval == timedelta(minutes=1)
    assert job.callback is collector.bars_capture_job
