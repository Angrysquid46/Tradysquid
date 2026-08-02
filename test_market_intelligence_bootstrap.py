from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import local_information_engine_bootstrap as bootstrap


class MarketIntelligenceBootstrapTests(unittest.TestCase):
    def temporary_paths(self):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        return directory, root / "engine.db", root / "acceptance.json"

    def test_required_cards_and_performance_sync_must_succeed_before_readiness(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        jobs = [
            engine.Job(
                "provider-event-queue",
                timedelta(seconds=15),
                lambda connection: "breaking-alerts heartbeat acknowledged",
            ),
            engine.Job(
                "premarket-visibility",
                timedelta(minutes=15),
                lambda connection: "premarket session card acknowledged",
            ),
            engine.Job(
                "discord-reporting",
                timedelta(minutes=5),
                lambda connection: "performance ledger reconciled",
            ),
        ]
        report_state = {
            "performance_reconciliation_version": bootstrap.performance_reconciliation.REPORT_VERSION,
            "performance_reconciliation_closed_trades": 123,
            "performance_reconciliation_week_trades": 18,
            "performance_reconciliation_daily_reports": 16,
            "performance_reconciliation_weekly_reports": 12,
        }
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", jobs),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(
                bootstrap.public.ford_scan,
                "read_report_state",
                return_value=report_state,
            ),
        ):
            payload = bootstrap.run_required_startup_jobs()

        self.assertEqual(payload["status"], "PASSED")
        self.assertEqual(
            set(payload["required_jobs"]),
            {"provider-event-queue", "premarket-visibility", "discord-reporting"},
        )
        self.assertEqual(
            payload["performance_reconciliation"]["canonical_closed_trades"],
            123,
        )
        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "PASSED")
        self.assertIn("performance reconciliation", stored["contract"])
        self.assertIn("before the engine health port opened", stored["contract"])

    def test_failed_discord_publication_blocks_startup(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine

        def fail(connection):
            raise RuntimeError("Discord did not acknowledge the card")

        jobs = [
            engine.Job(
                "provider-event-queue",
                timedelta(seconds=15),
                fail,
            ),
            engine.Job(
                "premarket-visibility",
                timedelta(minutes=15),
                lambda connection: "should not run",
            ),
            engine.Job(
                "discord-reporting",
                timedelta(minutes=5),
                lambda connection: "should not run",
            ),
        ]
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", jobs),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
        ):
            with self.assertRaisesRegex(RuntimeError, "startup publication failed"):
                bootstrap.run_required_startup_jobs()

        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "FAILED")
        self.assertIn("Discord did not acknowledge", stored["error"])

    def test_missing_performance_receipt_blocks_startup(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        jobs = [
            engine.Job(
                "provider-event-queue",
                timedelta(seconds=15),
                lambda connection: "ok",
            ),
            engine.Job(
                "premarket-visibility",
                timedelta(minutes=15),
                lambda connection: "ok",
            ),
            engine.Job(
                "discord-reporting",
                timedelta(minutes=5),
                lambda connection: "ran without durable receipt",
            ),
        ]
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", jobs),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(bootstrap.public.ford_scan, "read_report_state", return_value={}),
        ):
            with self.assertRaisesRegex(RuntimeError, "performance reconciliation version"):
                bootstrap.run_required_startup_jobs()

        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "FAILED")

    def test_engine_main_is_not_called_when_startup_acceptance_fails(self) -> None:
        engine_main = Mock(return_value=0)
        with (
            patch.object(
                bootstrap,
                "run_required_startup_jobs",
                side_effect=RuntimeError("required card missing"),
            ),
            patch.object(bootstrap.public.engine, "main", engine_main),
        ):
            with self.assertRaisesRegex(RuntimeError, "required card missing"):
                bootstrap.main()
        engine_main.assert_not_called()


if __name__ == "__main__":
    unittest.main()
