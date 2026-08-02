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

    def scorecard_state(self) -> dict:
        return {
            "performance_reconciliation_version": bootstrap.performance_scorecards.REPORT_VERSION,
            "performance_reconciliation_closed_trades": 123,
            "performance_reconciliation_daily_reports": 16,
            "performance_reconciliation_weekly_reports": 4,
            "performance_reconciliation_monthly_reports": 2,
            "performance_reconciliation_strategy_groups": 6,
            "performance_reconciliation_history_pages": 0,
            "performance_reconciliation_scorecard_only": True,
        }

    def required_jobs(self):
        engine = bootstrap.public.engine
        return [
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
                lambda connection: "performance scorecards reconciled",
            ),
        ]

    def open_trade(self) -> dict[str, str]:
        row = bootstrap.public.ford_scan.blank_row()
        row.update(
            {
                "trade_id": "TEST-OPEN-001",
                "outcome": "OPEN",
                "discord_thread_id": "thread-1",
                "discord_format_version": bootstrap.journal_contract.JOURNAL_FORMAT_VERSION,
            }
        )
        return row

    def test_required_cards_and_scorecards_must_succeed_before_readiness(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", self.required_jobs()),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(
                bootstrap.public.ford_scan,
                "read_report_state",
                return_value=self.scorecard_state(),
            ),
            patch.object(bootstrap.public.ford_scan, "read_log", return_value=[]),
        ):
            payload = bootstrap.run_required_startup_jobs()

        self.assertEqual(payload["status"], "PASSED")
        self.assertEqual(
            set(payload["required_jobs"]),
            {"provider-event-queue", "premarket-visibility", "discord-reporting"},
        )
        performance = payload["performance_reconciliation"]
        self.assertEqual(performance["canonical_closed_trades"], 123)
        self.assertEqual(performance["strategy_scorecards"], 6)
        self.assertEqual(performance["history_pages"], 0)
        self.assertEqual(payload["journal_contract"]["canonical_trades"], 0)
        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "PASSED")
        self.assertIn("one scorecard per play type", stored["contract"])
        self.assertIn("complete entry checklist", stored["contract"])
        self.assertIn("before the engine health port opened", stored["contract"])

    def test_complete_open_journal_is_required_when_trades_exist(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        trade = self.open_trade()
        tracker = Mock()
        tracker.ready = True
        journal_result = {
            "created": 0,
            "refreshed": 1,
            "closed_reviews": 0,
            "verified": 1,
            "entry_snapshots": 1,
            "pending": 0,
        }
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", self.required_jobs()),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(
                bootstrap.public.ford_scan,
                "read_report_state",
                return_value=self.scorecard_state(),
            ),
            patch.object(bootstrap.public.ford_scan, "read_log", return_value=[trade]),
            patch.object(bootstrap.public.ford_scan, "DiscordTracker", return_value=tracker),
            patch.object(
                bootstrap.public.ford_scan,
                "sync_all_trade_journals",
                return_value=journal_result,
            ) as sync_journals,
            patch.object(bootstrap.public.ford_scan, "write_log") as write_log,
            patch.object(bootstrap.trade_intelligence, "needs_sync", return_value=False),
        ):
            payload = bootstrap.run_required_startup_jobs()

        sync_journals.assert_called_once_with([trade], tracker)
        write_log.assert_called_once_with([trade])
        self.assertEqual(payload["journal_contract"]["verified_this_startup"], 1)
        self.assertEqual(payload["journal_contract"]["entry_snapshots_found"], 1)
        self.assertTrue(payload["journal_contract"]["all_open_journals_verified"])

    def test_incomplete_open_journal_blocks_readiness(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        trade = self.open_trade()
        trade["discord_format_version"] = "13"
        tracker = Mock()
        tracker.ready = True
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", self.required_jobs()),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(
                bootstrap.public.ford_scan,
                "read_report_state",
                return_value=self.scorecard_state(),
            ),
            patch.object(bootstrap.public.ford_scan, "read_log", return_value=[trade]),
            patch.object(bootstrap.public.ford_scan, "DiscordTracker", return_value=tracker),
            patch.object(
                bootstrap.public.ford_scan,
                "sync_all_trade_journals",
                return_value={
                    "created": 0,
                    "refreshed": 0,
                    "closed_reviews": 0,
                    "verified": 0,
                    "entry_snapshots": 0,
                    "pending": 1,
                },
            ),
            patch.object(bootstrap.public.ford_scan, "write_log"),
            patch.object(bootstrap.trade_intelligence, "needs_sync", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "complete entry contract"):
                bootstrap.run_required_startup_jobs()

        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "FAILED")
        self.assertIn("TEST-OPEN-001", stored["error"])

    def test_failed_discord_publication_blocks_startup(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine

        def fail(connection):
            raise RuntimeError("Discord did not acknowledge the card")

        jobs = [
            engine.Job("provider-event-queue", timedelta(seconds=15), fail),
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
            engine.Job("provider-event-queue", timedelta(seconds=15), lambda connection: "ok"),
            engine.Job("premarket-visibility", timedelta(minutes=15), lambda connection: "ok"),
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
            with self.assertRaisesRegex(RuntimeError, "scorecard version"):
                bootstrap.run_required_startup_jobs()

        stored = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "FAILED")

    def test_history_pages_block_startup(self) -> None:
        directory, db_path, acceptance_path = self.temporary_paths()
        self.addCleanup(directory.cleanup)
        engine = bootstrap.public.engine
        state = self.scorecard_state()
        state["performance_reconciliation_history_pages"] = 12
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(engine, "JOBS", self.required_jobs()),
            patch.object(bootstrap, "ACCEPTANCE_PATH", acceptance_path),
            patch.object(
                bootstrap.public.ford_scan,
                "read_report_state",
                return_value=state,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "history-page output"):
                bootstrap.run_required_startup_jobs()

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