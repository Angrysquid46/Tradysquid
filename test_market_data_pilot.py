from __future__ import annotations

import json

import pytest

import market_data_pilot as pilot
import market_data_pilot_report as report


# --- market_data_pilot.py ---------------------------------------------------

def test_measure_records_success_latency_bytes_and_rows():
    record = pilot._measure("get_quotes", lambda: {"SPY": {"last": 500.0}})
    assert record["label"] == "get_quotes"
    assert record["success"] is True
    assert record["rows"] == 1
    assert record["bytes"] > 0
    assert record["latency_ms"] >= 0
    assert record["error"] == ""


def test_measure_records_failure_without_raising():
    def boom():
        raise ValueError("provider unavailable")

    record = pilot._measure("get_chain", boom)
    assert record["success"] is False
    assert record["bytes"] == 0
    assert record["rows"] == 0
    assert "ValueError" in record["error"]
    assert "provider unavailable" in record["error"]


def test_measure_rows_count_matches_list_length():
    record = pilot._measure("get_chain", lambda: [{"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"}])
    assert record["rows"] == 3


def test_find_zero_dte_expiration_returns_today_when_listed(monkeypatch):
    monkeypatch.setattr(pilot.market_data, "now_ct", lambda: __import__("datetime").datetime(2026, 8, 24, 10, 0))
    monkeypatch.setattr(pilot.market_data, "get_expirations", lambda symbol: ["2026-08-24", "2026-08-25"])
    assert pilot.find_zero_dte_expiration("SPY") == "2026-08-24"


def test_find_zero_dte_expiration_returns_none_when_not_listed(monkeypatch):
    monkeypatch.setattr(pilot.market_data, "now_ct", lambda: __import__("datetime").datetime(2026, 8, 24, 10, 0))
    monkeypatch.setattr(pilot.market_data, "get_expirations", lambda symbol: ["2026-08-25"])
    assert pilot.find_zero_dte_expiration("SPY") is None


def test_find_zero_dte_expiration_returns_none_on_provider_error(monkeypatch):
    def boom(symbol):
        raise RuntimeError("provider down")

    monkeypatch.setattr(pilot.market_data, "get_expirations", boom)
    assert pilot.find_zero_dte_expiration("SPY") is None


def test_run_cycle_measures_quotes_and_chain_when_expiration_known(monkeypatch):
    monkeypatch.setattr(pilot.market_data, "get_quotes", lambda symbols, include_greeks=True: {"SPY": {}})
    monkeypatch.setattr(pilot.market_data, "get_chain", lambda symbol, expiration: [{"symbol": "SPY260824C00500000"}])
    records = pilot.run_cycle("SPY", "2026-08-24")
    assert [r["label"] for r in records] == ["get_quotes", "get_chain"]
    assert all(r["success"] for r in records)


def test_run_cycle_skips_chain_when_no_expiration(monkeypatch):
    monkeypatch.setattr(pilot.market_data, "get_quotes", lambda symbols, include_greeks=True: {"SPY": {}})
    records = pilot.run_cycle("SPY", None)
    assert [r["label"] for r in records] == ["get_quotes"]


def test_append_jsonl_writes_one_line_per_record(tmp_path):
    path = tmp_path / "pilot" / "out.jsonl"
    pilot.append_jsonl(path, [{"a": 1}, {"a": 2}])
    pilot.append_jsonl(path, [{"a": 3}])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["a"] for line in lines] == [1, 2, 3]


def test_run_stops_after_requested_cycles_without_sleeping(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot.market_data, "get_expirations", lambda symbol: [])
    monkeypatch.setattr(pilot.market_data, "get_quotes", lambda symbols, include_greeks=True: {"SPY": {}})
    monkeypatch.setattr(pilot.time, "sleep", lambda seconds: (_ for _ in ()).throw(AssertionError("should not sleep in a 1-cycle run")))
    output_path = tmp_path / "out.jsonl"
    pilot.run("SPY", interval_seconds=60, cycles=1, output_path=output_path)
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["label"] == "get_quotes"


# --- market_data_pilot_report.py --------------------------------------------

def test_load_records_parses_jsonl(tmp_path):
    path = tmp_path / "in.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    assert report.load_records(path) == [{"a": 1}, {"a": 2}]


def test_summarize_label_computes_projections():
    records = [
        {"label": "get_quotes", "success": True, "latency_ms": 100.0, "bytes": 1000, "rows": 1},
        {"label": "get_quotes", "success": True, "latency_ms": 200.0, "bytes": 1000, "rows": 1},
        {"label": "get_chain", "success": True, "latency_ms": 50.0, "bytes": 5000, "rows": 40},
    ]
    summary = report.summarize_label(records, "get_quotes", interval_seconds=60)
    assert summary["calls"] == 2
    assert summary["successes"] == 2
    assert summary["success_rate"] == 1.0
    assert summary["latency_ms_mean"] == 150.0
    assert summary["bytes_mean"] == 1000.0
    assert summary["rows_mean"] == 1.0
    # 6.5h RTH session at a 60s cadence = 390 calls/day
    assert summary["projected_calls_per_rth_day"] == pytest.approx(390.0)
    assert summary["projected_bytes_per_rth_day"] == pytest.approx(390000.0)


def test_summarize_label_counts_failures_in_success_rate_but_not_in_means():
    records = [
        {"label": "get_chain", "success": True, "latency_ms": 100.0, "bytes": 2000, "rows": 10},
        {"label": "get_chain", "success": False, "latency_ms": 500.0, "bytes": 0, "rows": 0, "error": "timeout"},
    ]
    summary = report.summarize_label(records, "get_chain", interval_seconds=60)
    assert summary["calls"] == 2
    assert summary["successes"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["latency_ms_mean"] == 100.0
    assert summary["bytes_mean"] == 2000.0


def test_summarize_label_handles_no_records_for_a_label():
    assert report.summarize_label([], "get_quotes", interval_seconds=60) == {
        "label": "get_quotes", "calls": 0,
    }


def test_summarize_covers_every_label_present():
    records = [
        {"label": "get_quotes", "success": True, "latency_ms": 1.0, "bytes": 10, "rows": 1},
        {"label": "get_chain", "success": True, "latency_ms": 1.0, "bytes": 10, "rows": 1},
    ]
    summary = report.summarize(records, interval_seconds=60)
    assert summary["total_records"] == 2
    assert {item["label"] for item in summary["by_label"]} == {"get_quotes", "get_chain"}
