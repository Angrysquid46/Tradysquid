from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_supervisor
import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent


class SupervisorAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        run_supervisor._LAST_READY_SIGNATURE = None

    def test_supervisor_log_is_safe_on_legacy_windows_console(self) -> None:
        class LegacyConsole:
            encoding = "cp1252"

            def __init__(self) -> None:
                self.output: list[str] = []

            def write(self, value: str) -> int:
                value.encode(self.encoding)
                self.output.append(value)
                return len(value)

            def flush(self) -> None:
                return None

        console = LegacyConsole()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(supervisor, "LOG_DIR", Path(directory)),
                patch.object(supervisor.sys, "stdout", console),
            ):
                supervisor.supervisor_log("Deploying old → new")

            self.assertIn("\\u2192", "".join(console.output))
            log_text = (Path(directory) / "supervisor.log").read_text(encoding="utf-8")
            self.assertIn("→", log_text)

    def test_deployment_pauses_only_information_engine_until_final_restart(self) -> None:
        full_stop = Mock()
        stopped: list[str] = []

        def fake_deploy(*, force: bool = False) -> bool:
            self.assertTrue(force)
            supervisor.stop_all_services()
            return True

        with (
            patch.object(run_supervisor, "ORIGINAL_DEPLOY_IF_NEEDED", fake_deploy),
            patch.object(supervisor, "stop_all_services", full_stop),
            patch.object(supervisor, "stop_process", side_effect=stopped.append),
            patch.object(supervisor, "supervisor_log"),
            patch.object(supervisor, "state_payload", return_value={}),
            patch.object(run_supervisor.time, "sleep"),
        ):
            result = run_supervisor.low_downtime_deploy_if_needed(force=True)
            self.assertIs(supervisor.stop_all_services, full_stop)

        self.assertTrue(result)
        self.assertEqual(stopped, ["information-engine"])
        full_stop.assert_not_called()

    def test_no_deployment_runs_automatic_discord_integrity_check(self) -> None:
        with (
            patch.object(run_supervisor, "ORIGINAL_DEPLOY_IF_NEEDED", return_value=False),
            patch.object(run_supervisor, "retry_pending_discord_configuration", return_value=False) as retry,
            patch.object(run_supervisor, "verify_and_repair_discord_integrity", return_value=True) as integrity,
        ):
            result = run_supervisor.low_downtime_deploy_if_needed()
        self.assertFalse(result)
        retry.assert_called_once_with()
        integrity.assert_called_once_with()

    def test_integrity_repair_records_and_reports_changed_order(self) -> None:
        tracker = Mock(enabled=True)
        write_state = Mock()
        post = Mock()
        with (
            patch.object(run_supervisor.ford_scan, "DiscordTracker", return_value=tracker),
            patch.object(
                run_supervisor.strict_learning_order,
                "enforce_learning_channel_order",
                return_value={
                    "canonical": 30,
                    "extras": 1,
                    "attempts": 1,
                    "changed": True,
                },
            ) as enforce,
            patch.object(supervisor, "state_payload", return_value={}),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "discord_post", post),
        ):
            result = run_supervisor.verify_and_repair_discord_integrity()

        self.assertTrue(result)
        enforce.assert_called_once()
        self.assertEqual(write_state.call_args.kwargs["discord_integrity_status"], "OK")
        post.assert_called_once()
        self.assertIn("01 → 27", post.call_args.args[0])

    def test_integrity_failure_is_saved_for_future_retry(self) -> None:
        tracker = Mock(enabled=True)
        write_state = Mock()
        post = Mock()
        with (
            patch.object(run_supervisor.ford_scan, "DiscordTracker", return_value=tracker),
            patch.object(
                run_supervisor.strict_learning_order,
                "enforce_learning_channel_order",
                side_effect=RuntimeError("Discord refused order"),
            ),
            patch.object(supervisor, "state_payload", return_value={}),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "discord_post", post),
        ):
            result = run_supervisor.verify_and_repair_discord_integrity()

        self.assertFalse(result)
        self.assertEqual(write_state.call_args.kwargs["discord_integrity_status"], "FAILED")
        post.assert_called_once()
        self.assertIn("will retry automatically", post.call_args.args[0])

    def test_readiness_posts_once_when_every_service_is_verified_online(self) -> None:
        ready = {service.name: True for service in supervisor.SERVICES}
        post = Mock()
        write_state = Mock()

        with (
            patch.object(run_supervisor, "ORIGINAL_ENSURE_SERVICES"),
            patch.object(supervisor, "LAST_HEALTH", ready.copy()),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
            patch.object(supervisor, "state_payload", return_value={}),
        ):
            run_supervisor.ensure_services_with_readiness()
            run_supervisor.ensure_services_with_readiness()

        post.assert_called_once()
        message, channel = post.call_args.args
        self.assertEqual(channel, "system-health")
        self.assertIn("services ready", message)
        self.assertIn("command-bot: **ONLINE**", message)
        self.assertIn("information-engine: **ONLINE**", message)
        self.assertIn("Discord synchronization: **VERIFIED**", message)
        self.assertIn("ngrok: **ONLINE**", message)
        self.assertIn("automatic updater: **ONLINE**", message)
        self.assertEqual(write_state.call_count, 4)
        heartbeat = write_state.call_args.kwargs
        self.assertIn("supervisor_heartbeat_at", heartbeat)
        self.assertTrue(heartbeat["auto_update_enabled"])

    def test_readiness_is_blocked_when_discord_sync_failed(self) -> None:
        ready = {service.name: True for service in supervisor.SERVICES}
        post = Mock()
        state = {
            "last_update_status": "DEPLOYED_WITH_DISCORD_ERRORS",
            "last_discord_sync_status": "FAILED",
            "deployed_sha": "abc123def456",
        }
        with (
            patch.object(run_supervisor, "ORIGINAL_ENSURE_SERVICES"),
            patch.object(supervisor, "LAST_HEALTH", ready.copy()),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "write_state"),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
            patch.object(supervisor, "state_payload", return_value=state),
        ):
            run_supervisor.ensure_services_with_readiness()
        post.assert_not_called()

    def test_readiness_posts_again_after_an_unhealthy_transition_recovers(self) -> None:
        ready = {service.name: True for service in supervisor.SERVICES}
        unhealthy = ready.copy()
        unhealthy["ngrok"] = False
        post = Mock()

        with (
            patch.object(run_supervisor, "ORIGINAL_ENSURE_SERVICES"),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "write_state"),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
            patch.object(supervisor, "state_payload", return_value={}),
        ):
            with patch.object(supervisor, "LAST_HEALTH", ready.copy()):
                run_supervisor.ensure_services_with_readiness()
            with patch.object(supervisor, "LAST_HEALTH", unhealthy):
                run_supervisor.ensure_services_with_readiness()
            with patch.object(supervisor, "LAST_HEALTH", ready.copy()):
                run_supervisor.ensure_services_with_readiness()

        self.assertEqual(post.call_count, 2)

    def test_failed_discord_sync_is_persisted_for_retry(self) -> None:
        write_state = Mock()
        post = Mock()
        results = [
            "Discord slash commands synchronized",
            "comprehensive Discord structure sync failed: HTTP 400",
        ]
        with (
            patch.object(supervisor, "state_payload", return_value={"last_update_status": "DEPLOYED"}),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
        ):
            succeeded = run_supervisor.record_discord_sync_results(results, source="deployment")

        self.assertFalse(succeeded)
        self.assertEqual(write_state.call_args.kwargs["last_discord_sync_status"], "FAILED")
        self.assertEqual(
            write_state.call_args.kwargs["last_update_status"],
            "DEPLOYED_WITH_DISCORD_ERRORS",
        )
        self.assertEqual(post.call_count, 2)
        channels = {call.args[1] for call in post.call_args_list}
        self.assertEqual(channels, {"workflow-log", "system-health"})
        for call in post.call_args_list:
            self.assertIn("deployment incomplete", call.args[0])

    def test_successful_retry_restores_deployed_status(self) -> None:
        write_state = Mock()
        post = Mock()
        results = [
            "Discord slash commands synchronized",
            "Strictly ordered Learning Center synchronized",
        ]
        with (
            patch.object(
                supervisor,
                "state_payload",
                return_value={
                    "last_update_status": "DEPLOYED_WITH_DISCORD_ERRORS",
                    "last_discord_sync_status": "FAILED",
                },
            ),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
        ):
            succeeded = run_supervisor.record_discord_sync_results(
                results, source="automatic-retry"
            )
        self.assertTrue(succeeded)
        self.assertEqual(write_state.call_args.kwargs["last_update_status"], "DEPLOYED")
        self.assertEqual(write_state.call_args.kwargs["last_discord_sync_status"], "OK")
        self.assertEqual(post.call_count, 2)

    def test_failed_discord_sync_retries_without_a_new_commit(self) -> None:
        results = [
            "Discord slash commands synchronized",
            "Strictly ordered Learning Center synchronized",
        ]
        record = Mock(return_value=True)
        with (
            patch.object(supervisor, "state_payload", return_value={"last_discord_sync_status": "FAILED"}),
            patch.object(supervisor, "supervisor_log"),
            patch.object(run_supervisor, "public_run_discord_configuration", return_value=results) as sync,
            patch.object(run_supervisor, "record_discord_sync_results", record),
        ):
            retried = run_supervisor.retry_pending_discord_configuration()

        self.assertTrue(retried)
        sync.assert_called_once_with()
        record.assert_called_once_with(results, source="automatic-retry")

    def test_fetch_failure_is_visible_and_retried(self) -> None:
        post = Mock()
        write_state = Mock()
        with (
            patch.object(
                run_supervisor,
                "ORIGINAL_FETCH_REMOTE_SHA",
                side_effect=RuntimeError("authentication failed"),
            ),
            patch.object(supervisor, "state_payload", return_value={}),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "discord_post", post),
        ):
            with self.assertRaisesRegex(RuntimeError, "authentication failed"):
                run_supervisor.monitored_fetch_remote_sha()

        self.assertEqual(write_state.call_args.kwargs["last_fetch_status"], "FAILED")
        post.assert_called_once()
        self.assertIn("automatic update check failed", post.call_args.args[0])

    def test_launcher_and_watchdog_prevent_a_single_process_failure(self) -> None:
        launcher = (ROOT / "START-SUPERVISOR.cmd").read_text(encoding="utf-8")
        watchdog = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "INSTALL-REMOTE-CONTROL.cmd").read_text(encoding="utf-8")
        task_installer = (ROOT / "INSTALL-SUPERVISOR-WATCHDOG.ps1").read_text(encoding="utf-8")

        self.assertIn("supervisor-stop.flag", launcher)
        self.assertIn("ENSURE-SUPERVISOR.ps1", launcher)
        self.assertIn("supervisor_heartbeat_at", watchdog)
        self.assertIn("Stop-StaleSupervisor", watchdog)
        self.assertIn("INSTALL-SUPERVISOR-WATCHDOG.ps1", installer)
        self.assertIn("automation_acceptance.py", installer)
        self.assertIn("/SC MINUTE", task_installer)
        self.assertIn("/MO 5", task_installer)


if __name__ == "__main__":
    unittest.main()
