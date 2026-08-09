"""Tests for chain snapshot recording: Tradier does not retain historical
data for expired options, so the only way to ever analyze "would a
different strike have done better" is capturing decision-time context as
it happens. Purely a recording step - must never block or alter an actual
trade if it fails."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import spy_scanner


def _with_temp_snapshot_dir():
    class _Swap:
        def __enter__(self):
            self.original = spy_scanner.CHAIN_SNAPSHOT_DIR
            self.tmp = tempfile.TemporaryDirectory()
            spy_scanner.CHAIN_SNAPSHOT_DIR = Path(self.tmp.name) / "chain-snapshots"
            return spy_scanner.CHAIN_SNAPSHOT_DIR

        def __exit__(self, *exc):
            spy_scanner.CHAIN_SNAPSHOT_DIR = self.original
            self.tmp.cleanup()

    return _Swap()


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": "T-SNAP-1", "ticker": "F", "play_type": "REGULAR",
        "call_or_put": "call", "strike": "12", "expiration": "2026-08-21",
        "entry_price": "0.50", "delta_at_entry": "0.55", "iv_at_entry": "0.40",
        "setup_score": "3.0",
    })
    row.update(overrides)
    return row


def test_writes_a_snapshot_file_named_by_trade_id():
    with _with_temp_snapshot_dir() as snapshot_dir:
        row = _row()
        spy_scanner.save_chain_snapshot(row, all_candidates=[], timestamp=spy_scanner.now_ct())
        assert (snapshot_dir / "T-SNAP-1.json").exists()


def test_the_snapshot_contains_the_chosen_contracts_key_details():
    with _with_temp_snapshot_dir() as snapshot_dir:
        row = _row()
        spy_scanner.save_chain_snapshot(row, all_candidates=[], timestamp=spy_scanner.now_ct())
        payload = json.loads((snapshot_dir / "T-SNAP-1.json").read_text())
        assert payload["chosen"]["strike"] == "12"
        assert payload["chosen"]["delta_at_entry"] == "0.55"
        assert payload["ticker"] == "F"


def test_other_qualifying_candidates_from_the_same_cycle_are_recorded():
    with _with_temp_snapshot_dir() as snapshot_dir:
        row = _row()
        other_candidates = [
            {"play_type": "REGULAR", "call_or_put": "call", "strike": "13",
             "expiration": "2026-08-21", "entry_price": 0.45, "delta": 0.50, "score": 2.5},
            {"play_type": "REGULAR", "call_or_put": "call", "strike": "12",
             "expiration": "2026-08-21", "entry_price": 0.50, "delta": 0.55, "score": 3.0},  # this is the chosen one
        ]
        spy_scanner.save_chain_snapshot(row, other_candidates, timestamp=spy_scanner.now_ct())
        payload = json.loads((snapshot_dir / "T-SNAP-1.json").read_text())
        # The chosen contract itself must not be duplicated into "other" -
        # only the genuinely different candidate should appear.
        assert len(payload["other_candidates_this_cycle"]) == 1
        assert payload["other_candidates_this_cycle"][0]["strike"] == "13"


def test_a_write_failure_never_raises_or_blocks_the_trade():
    row = _row()
    with mock.patch.object(Path, "write_text", side_effect=OSError("disk full")):
        # Must not raise - this is called from the live trade-entry loop
        # and a failure here can never be allowed to break entry itself.
        spy_scanner.save_chain_snapshot(row, all_candidates=[], timestamp=spy_scanner.now_ct())


def test_missing_trade_id_never_raises():
    row = _row(trade_id="")
    with _with_temp_snapshot_dir():
        spy_scanner.save_chain_snapshot(row, all_candidates=[], timestamp=spy_scanner.now_ct())
