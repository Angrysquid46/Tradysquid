from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class SupervisorEntrypointDiagnosticsTests(unittest.TestCase):
    def test_watchdog_detects_simple_and_legacy_entrypoints(self) -> None:
        text = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_simple.py", text)
        self.assertIn("run_supervisor_resilient.py", text)
        self.assertIn("run_supervisor.py", text)
        self.assertIn("$SupervisorScripts", text)

    def test_stop_script_cleans_all_managed_entrypoints(self) -> None:
        text = (ROOT / "stop_tradysquid_processes.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_simple", text)
        self.assertIn("run_supervisor_resilient", text)
        self.assertIn("run_supervisor", text)
        self.assertIn("local_information_engine(_public|_bootstrap)?", text)

    def test_read_only_diagnostics_cover_updater_watchdog_services_and_failures(self) -> None:
        text = (ROOT / "SUPERVISOR-DIAGNOSTICS.ps1").read_text(encoding="utf-8")
        for marker in (
            "run_supervisor_simple.py",
            "update interval expected: 120 seconds",
            "last_fetch_status",
            "last_fetch_mode",
            "last_update_status",
            "last_known_working_sha",
            "rollback_result",
            "service_process_ids",
            "service_restart_counts",
            "diagnostics.db",
            "diagnostics_summary",
            "Get-ScheduledTask",
            "Get-NetTCPConnection",
            "supervisor.log",
            "command-bot.log",
            "information-engine.log",
            "supervisor-startup.log",
            "supervisor-watchdog.log",
            "No fetch, merge, reset, restart, repair, or Discord write was performed",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("git -C $Root fetch", text)
        self.assertNotIn("Start-Process", text)
        self.assertNotIn("Stop-Process", text)


if __name__ == "__main__":
    unittest.main()
