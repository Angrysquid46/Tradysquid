from __future__ import annotations

import tempfile
from datetime import date, datetime
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
        lambda symbols, include_greeks=True: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
        collector.market_data, "get_expirations", lambda symbol: ["2026-08-24"]
    )
    monkeypatch.setattr(
        collector.market_data, "get_chain",
        lambda symbol, expiration: [{
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
        lambda symbols, include_greeks=True: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
        collector.market_data, "get_expirations", lambda symbol: ["2026-08-25"]
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
    monkeypatch.setattr(collector.market_data, "get_expirations", lambda symbol: [])
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
    monkeypatch.setattr(collector.market_data, "get_expirations", lambda symbol: [])
    monkeypatch.setattr(market_api_budget, "request_allowed", lambda priority: False)

    summary = collector.capture_cycle_job(manifest_db)
    assert "quote=MISS" in summary
    assert "errors=1" in summary
    row = manifest_db.execute(
        "SELECT api_errors FROM daily_data_manifest WHERE trading_day=?", ("2026-08-24",)
    ).fetchone()
    assert row[0] == 1


def test_capture_cycle_job_skips_chain_call_when_options_gate_blocks(
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
        lambda symbols, include_greeks=True: {"SPY": {
            "symbol": "SPY", "bid": 763.0, "ask": 763.05, "bid_date": 1, "ask_date": 2,
        }},
    )
    monkeypatch.setattr(
        collector.market_data, "get_expirations", lambda symbol: ["2026-08-24"]
    )

    def boom_if_called(*args, **kwargs):
        raise AssertionError("get_chain should not be called while the budget gate blocks")

    monkeypatch.setattr(collector.market_data, "get_chain", boom_if_called)
    monkeypatch.setattr(
        market_api_budget, "request_allowed",
        lambda priority: priority != market_api_budget.PRIORITY_SHARED_OPTIONS_COLLECTION,
    )

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

    monkeypatch.setattr(collector.market_data, "get_recent_intraday_history", boom_if_called)
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
        collector.market_data, "get_recent_intraday_history",
        lambda symbol, interval, calendar_days: all_bars,
    )

    first = collector.bars_capture_job(None)
    assert "2 new bars written" in first

    # Second run sees the same two bars again (overlapping pull window) -
    # both should be deduped against what is already on disk.
    second = collector.bars_capture_job(None)
    assert "0 new bars written" in second
