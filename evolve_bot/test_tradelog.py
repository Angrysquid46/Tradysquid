from __future__ import annotations
import tempfile
from datetime import datetime
from pathlib import Path

import tradelog


def test_read_log_returns_empty_list_when_file_missing():
    with tempfile.TemporaryDirectory() as temp:
        assert tradelog.read_log(Path(temp) / "trades.csv") == []


def test_write_then_read_round_trips_every_field():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "trades.csv"
        row = tradelog.blank_row()
        row.update({"trade_id": "EVOLVE-20260812-001", "outcome": "OPEN", "entry_price": "0.50"})
        tradelog.write_log(path, [row])
        loaded = tradelog.read_log(path)
        assert len(loaded) == 1
        assert loaded[0]["trade_id"] == "EVOLVE-20260812-001"
        assert loaded[0]["entry_price"] == "0.50"
        assert set(loaded[0].keys()) == set(tradelog.HEADER)


def test_blank_row_has_every_header_field_present_and_empty():
    row = tradelog.blank_row()
    assert set(row.keys()) == set(tradelog.HEADER)
    assert all(value == "" for value in row.values())


def test_open_rows_filters_to_outcome_open_only():
    rows = [
        {**tradelog.blank_row(), "trade_id": "T1", "outcome": "OPEN"},
        {**tradelog.blank_row(), "trade_id": "T2", "outcome": "WIN"},
        {**tradelog.blank_row(), "trade_id": "T3", "outcome": "LOSS"},
    ]
    assert [row["trade_id"] for row in tradelog.open_rows(rows)] == ["T1"]


def test_closed_rows_includes_win_loss_and_scratch_not_open():
    rows = [
        {**tradelog.blank_row(), "trade_id": "T1", "outcome": "OPEN"},
        {**tradelog.blank_row(), "trade_id": "T2", "outcome": "WIN"},
        {**tradelog.blank_row(), "trade_id": "T3", "outcome": "LOSS"},
        {**tradelog.blank_row(), "trade_id": "T4", "outcome": "SCRATCH"},
    ]
    assert {row["trade_id"] for row in tradelog.closed_rows(rows)} == {"T2", "T3", "T4"}


def test_next_trade_id_starts_at_001_for_a_new_day():
    trade_id = tradelog.next_trade_id([], 1, datetime(2026, 8, 12))
    assert trade_id == "EVOLVE-20260812-001"


def test_next_trade_id_increments_within_the_same_day():
    rows = [{**tradelog.blank_row(), "trade_id": "EVOLVE-20260812-001"}]
    trade_id = tradelog.next_trade_id(rows, 1, datetime(2026, 8, 12))
    assert trade_id == "EVOLVE-20260812-002"


def test_next_trade_id_resets_sequence_for_a_new_day():
    rows = [{**tradelog.blank_row(), "trade_id": "EVOLVE-20260811-005"}]
    trade_id = tradelog.next_trade_id(rows, 1, datetime(2026, 8, 12))
    assert trade_id == "EVOLVE-20260812-001"


def test_write_log_is_atomic_no_partial_file_left_on_interruption():
    # A crash mid-write must never leave a truncated file - the temp file
    # gets cleaned up, the real path is left untouched.
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "trades.csv"
        tradelog.write_log(path, [{**tradelog.blank_row(), "trade_id": "T1"}])

        class ExplodingRow(dict):
            def get(self, *a, **k):
                raise RuntimeError("boom")

        try:
            tradelog.write_log(path, [ExplodingRow()])
        except RuntimeError:
            pass
        # Original file must still be intact, not truncated or corrupted.
        loaded = tradelog.read_log(path)
        assert len(loaded) == 1
        assert loaded[0]["trade_id"] == "T1"
        assert not any(p.suffix == ".tmp" for p in path.parent.iterdir())
