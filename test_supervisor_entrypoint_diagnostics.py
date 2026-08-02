from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class SupervisorEntrypointDiagnosticsTests(unittest.TestCase):
    def test_watchdog_detects_resilient_and_legacy_entrypoints(self) -> None:
        text = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_resilient.py", text)
        self.assertIn("run_supervisor.py", text)
        self.assertIn("$SupervisorScripts", text)

    def test_stop_script_cleans_all_managed_entrypoints(self) -> None:
        text = (ROOT / "stop_tradysquid_processes.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_resilient", text)
        self.assertIn("run_supervisor", text)
        self.assertIn("local_information_engine(_public|_bootstrap)?", text)

    def test_read_only_diagnostics_cover_updater_watchdog_and_engine_acceptance(self) -> None:
        text = (ROOT / "SUPERVISOR-DIAGNOSTICS.ps1").read_text(encoding="utf-8")
        for marker in (
            "last_fetch_status",
            "last_update_status",
            "last_discord_sync_status",
            "last_command_registration_status",
            "information_engine_acceptance_status",
            "market-intelligence-startup.json",
            "Get-ScheduledTask",
            "Get-NetTCPConnection",
            "supervisor.log",
            "supervisor-startup.log",
            "supervisor-watchdog.log",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
