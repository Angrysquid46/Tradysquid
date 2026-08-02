from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import diagnostic_review_runtime as review
import diagnostic_upgrade_system as diagnostics
import github_upgrade_bridge as bridge


class DiagnosticReviewRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(diagnostics, "DB_PATH", self.root / "diagnostics.db")
        self.state_patch = patch.object(
            diagnostics, "SUPERVISOR_STATE_PATH", self.root / "supervisor-state.json"
        )
        self.db_patch.start()
        self.state_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.state_patch.stop)
        diagnostics.SUPERVISOR_STATE_PATH.write_text(
            json.dumps(
                {
                    "local_sha": "abc123def456",
                    "deployed_sha": "abc123def456",
                    "last_known_working_sha": "abc123def456",
                }
            ),
            encoding="utf-8",
        )
        self.original_base_failure = review._BASE_RECORD_FAILURE
        self.original_base_recovery = review._BASE_RECORD_RECOVERY
        review._BASE_RECORD_FAILURE = diagnostics.record_failure
        review._BASE_RECORD_RECOVERY = diagnostics.record_recovery
        self.addCleanup(self._restore_bases)

    def _restore_bases(self) -> None:
        review._BASE_RECORD_FAILURE = self.original_base_failure
        review._BASE_RECORD_RECOVERY = self.original_base_recovery

    def check(self, key: str = "transient-one", detail: str = "temporary"):
        return diagnostics.HealthCheck(
            key,
            False,
            "test",
            "test operation",
            detail,
            severity="WARNING",
            runtime_target="test-runtime",
        )

    def test_first_and_second_failure_do_not_publish_individual_card(self) -> None:
        with (
            patch.object(diagnostics, "_sync_discord") as sync,
            patch.object(bridge, "add_or_update_diagnostic") as github,
        ):
            first = review.record_failure(self.check(), sync=True)
            second = review.record_failure(self.check(), sync=True)
        self.assertEqual(first["consecutive_failures"], 1)
        self.assertEqual(second["consecutive_failures"], 2)
        sync.assert_not_called()
        github.assert_not_called()

    def test_third_failure_escalates_and_publishes_one_card(self) -> None:
        github_result = {
            "issue_number": 77,
            "request_number": 4,
            "comment_id": 900,
        }
        with (
            patch.object(
                bridge,
                "add_or_update_diagnostic",
                return_value=github_result,
            ) as github,
            patch.object(diagnostics, "_sync_discord", return_value=True) as sync,
        ):
            review.record_failure(self.check(), sync=True)
            review.record_failure(self.check(), sync=True)
            third = review.record_failure(self.check(), sync=True)
        github.assert_called_once()
        sync.assert_called_once()
        self.assertEqual(third["github_issue_number"], 77)
        self.assertEqual(third["github_request_number"], 4)

    def test_discord_timeout_surfaces_share_one_incident(self) -> None:
        channel_timeout = diagnostics.HealthCheck(
            "discord-connectivity",
            False,
            "Discord",
            "guild channel API",
            "ConnectTimeout: HTTPSConnectionPool(host='discord.com', port=443)",
            severity="WARNING",
        )
        command_timeout = diagnostics.HealthCheck(
            "discord-command-registry-connectivity",
            False,
            "Discord commands",
            "read-only guild command verification",
            "Connection to discord.com timed out",
            severity="WARNING",
        )
        with patch.object(bridge, "add_or_update_diagnostic"):
            first = review.record_failure(channel_timeout, sync=False)
            second = review.record_failure(command_timeout, sync=False)
        self.assertEqual(first["signature"], second["signature"])
        connection = diagnostics.connect_store()
        try:
            count = connection.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
            row = connection.execute("SELECT * FROM diagnostics").fetchone()
        finally:
            connection.close()
        self.assertEqual(count, 1)
        self.assertEqual(row["signature_key"], "incident-discord-connectivity")
        self.assertEqual(row["consecutive_failures"], 2)

    def test_first_log_scan_seeds_cursor_without_replaying_history(self) -> None:
        log_dir = self.root / "logs"
        log_dir.mkdir()
        startup = self.root / "supervisor-startup.log"
        watchdog = self.root / "supervisor-watchdog.log"
        (log_dir / "supervisor.log").write_text(
            "old error: Discord request failed\n", encoding="utf-8"
        )
        with (
            patch.object(diagnostics, "ROOT", self.root),
            patch.object(diagnostics, "LOG_DIR", log_dir),
            patch.object(diagnostics, "STARTUP_LOG", startup),
            patch.object(diagnostics, "WATCHDOG_LOG", watchdog),
        ):
            store = diagnostics.connect_store()
            try:
                first = review.log_checks(store)
                with (log_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
                    handle.write(
                        "new error: ConnectTimeoutError: Connection to discord.com timed out\n"
                    )
                second = review.log_checks(store)
            finally:
                store.close()
        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].key, "log-supervisor.log-discord-connectivity")

    def test_summary_exposes_only_actionable_records_as_open(self) -> None:
        with patch.object(
            bridge,
            "add_or_update_diagnostic",
            return_value={"issue_number": 1, "request_number": 1, "comment_id": 1},
        ):
            review.record_failure(self.check("temporary"), sync=False)
            for _ in range(3):
                review.record_failure(self.check("persistent"), sync=False)
        summary = review.diagnostics_summary()
        self.assertEqual(len(summary["transient"]), 1)
        self.assertEqual(len(summary["actionable"]), 1)
        self.assertEqual(summary["open"], summary["actionable"])

    def test_dashboard_publisher_does_not_fail_because_feature_proof_failed(self) -> None:
        original = review._BASE_DASHBOARD_JOB
        review._BASE_DASHBOARD_JOB = Mock(
            side_effect=RuntimeError(
                "applied-upgrades verification found 2 failed item(s)"
            )
        )
        try:
            detail = review.dashboard_job(sqlite3.connect(":memory:"))
        finally:
            review._BASE_DASHBOARD_JOB = original
        self.assertIn("Dashboard published successfully", detail)
        self.assertIn("2 failed item", detail)

    def test_runtime_contract_contains_only_current_layers_in_order(self) -> None:
        root = Path(__file__).resolve().parent
        loader = (root / "run_with_env.py").read_text(encoding="utf-8")
        contract = (root / "runtime_contract.py").read_text(encoding="utf-8")
        self.assertIn("runtime_contract.install_information_engine()", loader)

        policy = contract.index("install_diagnostic_policy(diagnostics, review)")
        feature_jobs = contract.index("upgrade_batch_44.install_engine()")
        diagnostics_layer = contract.index("diagnostics.install()")
        calendar = contract.index("market_calendar_runtime.install()")
        supervisor = contract.index("supervisor_diagnostic_runtime.install()")
        scheduler = contract.index("scheduler_diagnostic_runtime.install()")
        review_layer = contract.index("review.install()")
        outbound = contract.index("outbound_connectivity_runtime.install()")
        retirement = contract.index("dedupe_and_retire_jobs(upgrade_batch_44._engine())")
        live_checks = contract.index("install_live_checks(diagnostics)")

        self.assertLess(policy, feature_jobs)
        self.assertLess(feature_jobs, diagnostics_layer)
        self.assertLess(diagnostics_layer, calendar)
        self.assertLess(calendar, supervisor)
        self.assertLess(supervisor, scheduler)
        self.assertLess(scheduler, review_layer)
        self.assertLess(review_layer, outbound)
        self.assertLess(outbound, retirement)
        self.assertLess(retirement, live_checks)

        for retired_install in (
            "upgrade_batch_44_live_acceptance.install()",
            "diagnostic_startup_runtime.install()",
            "diagnostic_nonblocking_runtime.install()",
            "diagnostic_state_migration.install()",
            "upgrade_lifecycle_dashboard.install()",
            "applied_upgrades.install_engine()",
        ):
            self.assertNotIn(retired_install, loader + contract)


if __name__ == "__main__":
    unittest.main()
