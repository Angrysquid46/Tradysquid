from __future__ import annotations

import unittest

import dynamic_universe
import journal_contract
import upgrade_batch_44 as batch


class UpgradeBatch44Tests(unittest.TestCase):
    def test_market_direction_prefers_recorded_regime(self) -> None:
        self.assertEqual(
            batch._snapshot_direction({"regime": "BULLISH / CONTROLLED"}, -2.0),
            "BULLISH",
        )
        self.assertEqual(
            batch._snapshot_direction({"regime": "BEARISH / CONTROLLED"}, 2.0),
            "BEARISH",
        )
        self.assertEqual(batch._snapshot_direction({}, 0.75), "UP")
        self.assertEqual(batch._snapshot_direction({}, -0.75), "DOWN")

    def test_learning_results_are_aggregate_only(self) -> None:
        summary = {
            "closed_trades": 25,
            "reviewed_trades": 20,
            "review_coverage_pct": 80.0,
            "minimum_sample": 20,
            "learning_version": "abc123",
            "evidence_ready_groups": [
                {
                    "feature": "play_style",
                    "value": "REGULAR-CALL",
                    "samples": 20,
                    "win_rate_pct": 55.0,
                    "average_pl_dollars": 4.5,
                    "total_pl_dollars": 90.0,
                    "average_mae_pct": -12.0,
                }
            ],
            "play_style_suggestions": [
                {
                    "play_style": "REGULAR-CALL",
                    "samples": 20,
                    "confidence": "EVIDENCE-READY",
                    "observation": "Preserve the confirmed entry filter.",
                    "expected_tradeoff": "Fewer entries.",
                }
            ],
        }
        rendered = batch.learning_results_text(summary)
        self.assertIn("Evidence Dashboard", rendered)
        self.assertIn("Suggested next reviews", rendered)
        self.assertNotIn("Trade History", rendered)
        self.assertNotIn("trade_id", rendered)

    def test_style_card_keeps_history_in_journal(self) -> None:
        group = {
            "samples": 12,
            "win_rate_pct": 50.0,
            "average_pl_dollars": 1.0,
            "total_pl_dollars": 12.0,
            "profit_factor": 1.1,
            "average_mfe_pct": 18.0,
            "average_mae_pct": -10.0,
            "evidence_ready": False,
        }
        suggestion = {
            "observation": "Review adverse excursion.",
            "expected_tradeoff": "Tighter entries reduce frequency.",
        }
        rendered = batch.style_evidence_text(
            "Regular Call", group, suggestion, 20
        )
        self.assertIn("8 more closed trade", rendered)
        self.assertIn("Individual completed trades remain only in Trade Journal", rendered)
        self.assertNotIn("trade_id", rendered)

    def test_universe_rotation_capability_was_removed_not_merely_disabled(self) -> None:
        # Owner directive: this system trades SPY exclusively. Ticker-
        # rotation/universe-expansion used to exist but stay off by default
        # (UNIVERSE_ROTATION_ENABLED=False) - a prior "erase this" request
        # was only ever half-honored that way. This time the capability
        # itself is gone: no job, no function, no candidate-pool constants.
        self.assertFalse(hasattr(batch, "universe_rotation_job"))
        self.assertFalse(hasattr(batch, "UNIVERSE_ROTATION_ENABLED"))
        self.assertFalse(hasattr(batch, "LIQUID_CANDIDATES"))
        self.assertFalse(hasattr(dynamic_universe, "upsert_candidates"))
        self.assertFalse(hasattr(dynamic_universe, "max_active_symbols"))

    def test_engine_install_registers_batch_jobs_once(self) -> None:
        batch.install_engine()
        names = [job.name for job in batch._engine().JOBS]
        for expected in (
            "active-market-regime",
            "intraday-chart-refresh",
            "upgrade-request-migration",
        ):
            self.assertLessEqual(names.count(expected), 1)
        self.assertNotIn("dynamic-universe-rotation", names)


if __name__ == "__main__":
    unittest.main()
