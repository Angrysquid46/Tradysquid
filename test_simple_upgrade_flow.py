from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_upgrade_bridge

# The laptop updater already runs this module. Importing these TestCase classes
# makes the same one-supervisor/runtime-contract checks part of local deployment
# validation, not CI-only decoration.
from test_discord_reconciliation_safety import DiscordReconciliationSafetyTests  # noqa: F401
from test_ngrok_process_runtime import NgrokProcessRuntimeTests  # noqa: F401
from test_runtime_contract import RuntimeContractTests  # noqa: F401
from test_scheduler_diagnostic_runtime import SchedulerDiagnosticRuntimeTests  # noqa: F401
from test_single_owner_runtime import SingleOwnerRuntimeTests  # noqa: F401
from test_supervisor_diagnostic_runtime import SupervisorDiagnosticRuntimeTests  # noqa: F401
from test_supervisor_entrypoint_diagnostics import SupervisorEntrypointDiagnosticsTests  # noqa: F401


ROOT = Path(__file__).resolve().parent
NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def load_simple():
    return importlib.import_module("run_supervisor_simple")


def load_supervisor():
    return importlib.import_module("tradysquid_supervisor")


def load_simple_runtime():
    return importlib.import_module("simple_upgrade_runtime")


def load_clean_handoff():
    return importlib.import_module("clean_rebuild_auto_handoff")


def handoff_receipt(
    status: str,
    *,
    minutes_ago: int = 0,
    attempts: int = 1,
    expected_commit: str | None = None,
) -> dict[str, object]:
    handoff = load_clean_handoff()
    return {
        "status": status,
        "expected_clean_commit": expected_commit or handoff.EXPECTED_CLEAN_COMMIT,
        "observed_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "attempt_count": attempts,
    }


class SimpleUpgradeFlowTests(unittest.TestCase):
    def test_discord_bridge_logs_requests_without_editing_code(self) -> None:
        text = (ROOT / "github_upgrade_bridge.py").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertIn("It never calls OpenAI", normalized)
        self.assertNotIn('"/contents/', text)
        self.assertNotIn('"POST", "/pulls"', text)
        self.assertNotIn('"PUT", "/merges"', text)
        self.assertIn("PENDING BATCH REVIEW", text)
        self.assertTrue(callable(github_upgrade_bridge.add_request))
        self.assertTrue(callable(github_upgrade_bridge.add_or_update_diagnostic))
        self.assertTrue(callable(github_upgrade_bridge.ready_batch))

    def test_default_update_interval_is_two_minutes(self) -> None:
        self.assertEqual(load_supervisor().UPDATE_SECONDS, 120)

    def test_deployment_does_not_run_discord_maintenance(self) -> None:
        simple = load_simple()
        supervisor = load_supervisor()
        self.assertFalse(supervisor.AUTO_DISCORD_SYNC)
        self.assertFalse(supervisor.AUTO_REGISTER_COMMANDS)
        self.assertEqual(simple.no_deployment_discord_configuration(), [])

    def test_launcher_uses_simple_entrypoint_only(self) -> None:
        text = (ROOT / "START-SUPERVISOR.cmd").read_text(encoding="utf-8")
        launch_line = next(
            line for line in text.splitlines() if "python -u" in line.casefold()
        )
        self.assertIn("run_supervisor_simple.py", launch_line)
        self.assertNotIn("run_supervisor_resilient.py", launch_line)

    def test_handoff_runs_before_env_or_runtime_dependency_imports(self) -> None:
        source = (ROOT / "run_with_env.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main() -> None:") :]
        handoff_index = main_source.index("if launch_clean_handoff_before_runtime(target):")
        env_index = main_source.index("load_env()")
        runtime_index = main_source.index("install_runtime_overrides(")
        self.assertLess(handoff_index, env_index)
        self.assertLess(handoff_index, runtime_index)
        self.assertIn("import clean_rebuild_auto_handoff", source)
        self.assertIn("raise SystemExit(76)", main_source)

    def test_simple_supervisor_has_safe_update_contract(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        for marker in (
            '"fetch", "--quiet", "origin", "main"',
            '"fetch", "--ipv4", "--quiet", "origin", "main"',
            "validate_checkout",
            "Compilation and focused deployment tests passed",
            "SIMPLE_TWO_MINUTE_UPDATER",
            '"merge-base", "--is-ancestor"',
            '"merge", "--ff-only", "origin/main"',
            "_prepare_runtime_backup",
            "last_known_working_sha",
            "rollback_ref",
            "ROLLED_BACK",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("sync_discord_structure", text)
        self.assertNotIn("register_discord_commands", text)
        self.assertNotIn("engine_acceptance", text)

    def test_preflight_happens_before_service_stop(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        backup_index = text.index("saved_runtime = _prepare_runtime_backup")
        rollback_ref_index = text.index('backup_result = supervisor.git("update-ref"')
        stop_index = text.index("supervisor.stop_all_services()")
        self.assertLess(backup_index, stop_index)
        self.assertLess(rollback_ref_index, stop_index)

    def test_fetch_failure_path_never_stops_services(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        fetch_failure = text.index('last_update_status="FETCH_FAILED"')
        stop_index = text.index("supervisor.stop_all_services()")
        self.assertLess(fetch_failure, stop_index)
        segment = text[fetch_failure:stop_index]
        self.assertNotIn("stop_all_services", segment)
        self.assertNotIn('merge", "--ff-only', segment)

    def test_watchdog_and_stop_script_recognize_simple_entrypoint(self) -> None:
        watchdog = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        stopper = (ROOT / "stop_tradysquid_processes.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_supervisor_simple.py", watchdog)
        self.assertIn("run_supervisor_simple", stopper)

    def test_applied_upgrade_catalog_reports_the_running_simple_path(self) -> None:
        simple_upgrade_runtime = load_simple_runtime()
        simple_upgrade_runtime.install()
        keys = [item.key for item in simple_upgrade_runtime.SIMPLE_INFRA_SPECS]
        self.assertIn("discord-review-bridge", keys)
        self.assertIn("simple-two-minute-updater", keys)
        self.assertIn("safe-fast-forward-deployment", keys)
        self.assertIn("runtime-state-preservation", keys)
        self.assertIn("independent-feature-startup", keys)
        self.assertIn("applied-upgrades-dashboard", keys)
        self.assertNotIn("command-retry-separation", keys)

    def test_applied_upgrades_channel_is_owned_by_its_feature(self) -> None:
        text = (ROOT / "simple_upgrade_runtime.py").read_text(encoding="utf-8")
        self.assertIn("ensure_dashboard_channel", text)
        self.assertIn('/guilds/{tracker.guild_id}/channels', text)
        self.assertIn("permission_overwrites", text)

    def test_clean_rebuild_handoff_targets_exact_audited_commit(self) -> None:
        handoff = load_clean_handoff()
        text = (ROOT / "clean_rebuild_auto_handoff.py").read_text(encoding="utf-8")
        self.assertEqual(
            handoff.EXPECTED_CLEAN_COMMIT,
            "254d67d0cf2a796fd9689693c7b061ce98ae2c63",
        )
        self.assertEqual(handoff.MAX_ATTEMPTS, 3)
        self.assertEqual(handoff.LAUNCH_GRACE_SECONDS, 45 * 60)
        self.assertEqual(handoff.RETRY_BACKOFF_SECONDS, 15 * 60)
        self.assertIn("refs/remotes/origin", text)
        self.assertIn("worktree", text)
        self.assertIn("supervisor-stop.flag", text)
        self.assertIn("clean-rebuild-auto-handoff.json", text)
        self.assertIn("secret_values_written", text)
        self.assertNotIn("TERMINAL_STATUSES", text)
        self.assertNotIn("DISCORD_BOT_TOKEN=", text)
        self.assertNotIn("TRADIER_ACCESS_TOKEN=", text)
        self.assertTrue(callable(handoff.launch_if_needed))
        self.assertTrue(callable(handoff.evaluate_handoff))

    def test_fresh_launched_receipt_waits_without_duplicate_process(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=5),
            {},
            now=NOW,
        )
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["attempt_count"], 1)

    def test_stale_launched_receipt_retries_instead_of_blocking_forever(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=46),
            {},
            now=NOW,
        )
        self.assertEqual(decision["action"], "launch")
        self.assertEqual(decision["attempt_count"], 2)

    def test_newer_final_pass_completes_handoff(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=20),
            handoff_receipt("PASS", minutes_ago=1),
            now=NOW,
        )
        self.assertEqual(decision["action"], "complete")
        self.assertEqual(decision["final_status"], "PASS")

    def test_fresh_rolled_back_receipt_observes_backoff(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=20),
            handoff_receipt("ROLLED BACK", minutes_ago=1),
            now=NOW,
        )
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["final_status"], "ROLLED_BACK")

    def test_old_rolled_back_receipt_retries(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=30),
            handoff_receipt("ROLLED BACK", minutes_ago=16),
            now=NOW,
        )
        self.assertEqual(decision["action"], "launch")
        self.assertEqual(decision["attempt_count"], 2)

    def test_third_failed_attempt_blocks_automatic_loop(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=30, attempts=3),
            handoff_receipt("FAILED", minutes_ago=1, attempts=3),
            now=NOW,
        )
        self.assertEqual(decision["action"], "blocked")
        self.assertEqual(decision["attempt_count"], 3)

    def test_old_final_failure_does_not_override_newer_active_launch(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt("LAUNCHED", minutes_ago=1, attempts=2),
            handoff_receipt("ROLLED BACK", minutes_ago=20, attempts=1),
            now=NOW,
        )
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["attempt_count"], 2)

    def test_receipt_for_old_target_does_not_block_new_target(self) -> None:
        handoff = load_clean_handoff()
        decision = handoff.evaluate_handoff(
            handoff_receipt(
                "PASS",
                minutes_ago=1,
                attempts=3,
                expected_commit="0" * 40,
            ),
            {},
            now=NOW,
        )
        self.assertEqual(decision["action"], "launch")
        self.assertEqual(decision["attempt_count"], 1)

    def test_deployment_manifest_compiles_and_tests_handoff(self) -> None:
        manifest = importlib.import_module("deployment_validation_manifest")
        result = manifest.validate_manifest()
        self.assertIn("clean_rebuild_auto_handoff.py", manifest.COMPILE_MODULES)
        self.assertTrue(result["automatic_handoff_tested"])


if __name__ == "__main__":
    unittest.main()
