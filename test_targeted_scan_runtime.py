from __future__ import annotations

import tempfile
import unittest

import targeted_scan_runtime


class TargetedScanRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = targeted_scan_runtime.Path(self.temp.name)
        self.original_db = targeted_scan_runtime.DB_PATH
        self.original_state = targeted_scan_runtime.STATE_PATH
        targeted_scan_runtime.DB_PATH = root / "targeted.db"
        targeted_scan_runtime.STATE_PATH = root / "status.json"

    def tearDown(self) -> None:
        targeted_scan_runtime.DB_PATH = self.original_db
        targeted_scan_runtime.STATE_PATH = self.original_state
        self.temp.cleanup()

    def test_event_queue_deduplicates_and_claims_symbol(self) -> None:
        first = targeted_scan_runtime.enqueue(
            "F",
            provider="tradingview",
            event_type="breakout",
            priority=100,
            reason="test",
        )
        second = targeted_scan_runtime.enqueue(
            "F",
            provider="tradingview",
            event_type="breakout",
            priority=100,
            reason="test",
        )
        self.assertTrue(first)
        self.assertFalse(second)
        claimed = targeted_scan_runtime.claim(limit=2)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["symbol"], "F")

        targeted_scan_runtime._finish(
            claimed[0], result="OK", detail="test completed"
        )
        summary = targeted_scan_runtime.status()
        self.assertEqual(summary["counts"].get("DONE"), 1)
        self.assertEqual(summary["recent"][0]["result"], "OK")


if __name__ == "__main__":
    unittest.main()
