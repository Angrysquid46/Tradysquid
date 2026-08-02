import tempfile
import unittest
from pathlib import Path
from unittest import mock

import outcome_learning
import trade_intelligence
import upgrade_impact


class TradeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = mock.patch.object(
            trade_intelligence, "DB_PATH", Path(self.temp.name) / "intelligence.db"
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def test_lifecycle_events_are_idempotent(self):
        row = {"trade_id": "TEST-1", "ticker": "F", "outcome": "OPEN", "thesis": "Recorded"}
        self.assertTrue(trade_intelligence.record_event(row, "entry", "entry"))
        self.assertFalse(trade_intelligence.record_event(row, "entry", "entry"))
        self.assertEqual(trade_intelligence.health()["lifecycle_events"], 1)

    def test_identical_snapshots_are_suppressed(self):
        row = {"trade_id": "TEST-2"}
        first = Path(self.temp.name) / "first.png"
        second = Path(self.temp.name) / "second.png"
        first.write_bytes(b"same-image")
        second.write_bytes(b"same-image")
        self.assertTrue(trade_intelligence.register_snapshot(row, "entry", first, source_timestamp="t1"))
        self.assertFalse(trade_intelligence.register_snapshot(row, "hold-1", second, source_timestamp="t2"))
        trade_intelligence.forget_snapshot("TEST-2", "entry")
        self.assertTrue(trade_intelligence.register_snapshot(row, "hold-1", second, source_timestamp="t2"))

    def test_failed_consumer_can_recover_to_same_canonical_version(self):
        trade_intelligence.acknowledge("TEST-3", "ticker-results", "v1", "RETRY", "network")
        self.assertEqual(trade_intelligence.health()["failed_syncs"], 1)
        trade_intelligence.acknowledge("TEST-3", "ticker-results", "v1")
        self.assertEqual(trade_intelligence.health()["failed_syncs"], 0)

    def test_complete_lifecycle_timeline_is_unique_and_replay_safe(self):
        row = {
            "trade_id": "SIM-20260801-001", "ticker": "SIM", "play_type": "REGULAR",
            "call_or_put": "call", "outcome": "OPEN", "thesis": "simulated evidence",
            "entry_confirmation": "confirmed", "invalidation": "defined", "risk_plan": "one contract",
        }
        entry = Path(self.temp.name) / "entry.png"
        hold = Path(self.temp.name) / "hold.png"
        exit_image = Path(self.temp.name) / "exit.png"
        entry.write_bytes(b"entry-chart")
        hold.write_bytes(b"changed-hold-chart")
        exit_image.write_bytes(b"changed-exit-chart")
        self.assertTrue(trade_intelligence.record_event(row, "entry", "entry"))
        self.assertTrue(trade_intelligence.register_snapshot(row, "entry", entry, source_timestamp="t1"))
        row.update({"last_signal": "HOLD", "current_pl_dollars": "5"})
        self.assertTrue(trade_intelligence.record_event(row, "hold-evaluation", "hold-1"))
        self.assertTrue(trade_intelligence.register_snapshot(row, "hold-1", hold, source_timestamp="t2"))
        row.update({"last_signal": "TAKE PROFIT", "outcome": "WIN", "realized_pl_dollars": "12"})
        self.assertTrue(trade_intelligence.record_event(row, "exit-decision", "exit"))
        self.assertTrue(trade_intelligence.register_snapshot(row, "exit", exit_image, source_timestamp="t3"))
        self.assertFalse(trade_intelligence.record_event(row, "exit-decision", "exit"))
        health = trade_intelligence.health()
        self.assertEqual(health["lifecycle_events"], 3)
        self.assertEqual(health["snapshots"], 3)

    def test_research_sources_are_deduplicated_and_queued(self):
        item = {"source_url": "https://example.test/source", "ticker": "F", "claim": "test"}
        first = trade_intelligence.store_research_source(item)
        second = trade_intelligence.store_research_source(item)
        self.assertEqual(first, second)
        health = trade_intelligence.health()
        self.assertEqual(health["research_sources"], 1)
        self.assertEqual(health["pending_research"], 1)

    def test_play_style_learning_includes_profitability_and_guardrail(self):
        rows = [
            {"ticker": "F", "play_type": "REGULAR", "call_or_put": "call", "outcome": "WIN", "realized_pl_dollars": "20", "max_favorable_pct": "30", "max_adverse_pct": "-5"},
            {"ticker": "F", "play_type": "REGULAR", "call_or_put": "call", "outcome": "LOSS", "realized_pl_dollars": "-10", "max_favorable_pct": "5", "max_adverse_pct": "-20"},
        ]
        summary = outcome_learning.summarize(rows)
        style = next(item for item in summary["groups"] if item["feature"] == "play_style")
        self.assertEqual(style["profit_factor"], 2.0)
        self.assertEqual(style["expectancy_dollars"], 5.0)
        self.assertFalse(summary["play_style_suggestions"][0]["automatic_change"])

    def test_high_risk_upgrade_requires_tests(self):
        self.assertEqual(upgrade_impact.report(["ford_scan.py"])["status"], "BLOCK")
        self.assertEqual(
            upgrade_impact.report(["ford_scan.py", "test_trade_intelligence.py"])["status"],
            "PASS",
        )


if __name__ == "__main__":
    unittest.main()
