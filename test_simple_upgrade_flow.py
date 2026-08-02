from __future__ import annotations

import unittest
from pathlib import Path

import github_upgrade_bridge
import run_supervisor_simple as simple
import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent


class SimpleUpgradeFlowTests(unittest.TestCase):
    def test_discord_bridge_logs_requests_without_editing_code(self) -> None:
        text = (ROOT / "github_upgrade_bridge.py").read_text(encoding="utf-8")
        self.assertIn("never edits repository contents", text)
        self.assertIn("PENDING BATCH REVIEW", text)
        self.assertTrue(callable(github_upgrade_bridge.add_request))
        self.assertTrue(callable(github_upgrade_bridge.ready_batch))

    def test_default_update_interval_is_two_minutes(self) -> None:
        self.assertEqual(supervisor.UPDATE_SECONDS, 120)

    def test_deployment_does_not_run_discord_maintenance(self) -> None:
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

    def test_simple_supervisor_has_safe_update_contract(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        for marker in (
            '"fetch", "--quiet", "origin", "main"',
            '"fetch", "--ipv4", "--quiet", "origin", "main"',
            "validate_checkout",
            "Compilation and focused deployment tests passed",
            "SIMPLE_TWO_MINUTE_UPDATER",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("sync_discord_structure", text)
        self.assertNotIn("register_discord_commands", text)
        self.assertNotIn("engine_acceptance", text)

    def test_watchdog_and_stop_script_recognize_simple_entrypoint(self) -> None:
        watchdog = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        stopper = (ROOT / "stop_tradysquid_processes.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_supervisor_simple.py", watchdog)
        self.assertIn("run_supervisor_simple", stopper)


if __name__ == "__main__":
    unittest.main()
