from __future__ import annotations

import unittest
from pathlib import Path

import simplified_runtime


ROOT = Path(__file__).resolve().parent


class SupervisorEntrypointDiagnosticsTests(unittest.TestCase):
    def test_watchdog_requires_exactly_one_simple_owner(self) -> None:
        text = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_simple.py", text)
        self.assertIn("SingleOwner", text)
        self.assertIn("Get-HealthPortOwner", text)
        self.assertIn("LocalPort $HealthPort", text)
        self.assertIn("wscript.exe", text)
        self.assertNotIn("run_supervisor_resilient.py", text)
        self.assertNotIn("run_supervisor.py'", text)

    def test_stop_script_cleans_simple_owner_and_managed_services(self) -> None:
        text = (ROOT / "stop_tradysquid_processes.ps1").read_text(encoding="utf-8")
        self.assertIn("run_supervisor_simple", text)
        self.assertIn("LocalPort 8876", text)
        self.assertIn("local_information_engine(_public|_bootstrap)?", text)
        self.assertNotIn("run_supervisor_resilient", text)

    def test_read_only_diagnostics_cover_updater_watchdog_services_and_failures(self) -> None:
        text = (ROOT / "SUPERVISOR-DIAGNOSTICS.ps1").read_text(encoding="utf-8")
        for marker in (
            "run_supervisor_simple.py",
            "update interval expected: 120 seconds",
            "simple supervisor count",
            "port 8876 owner",
            "last_fetch_status",
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

    def test_simplified_runtime_retires_only_reporting_jobs(self) -> None:
        validation = simplified_runtime.validate()
        self.assertEqual(validation["single_supervisor_target"], "run_supervisor_simple.py:8876")
        self.assertFalse(validation["provider_timeouts_create_code_issue"])
        self.assertTrue(validation["diagnostic_only_batch_autoclose"])
        self.assertIn("upgrade-batch-44-acceptance", validation["retired_jobs"])
        self.assertIn("upgrade-request-migration", validation["retired_jobs"])
        self.assertNotIn("intraday-chart-refresh", validation["retired_jobs"])

    def test_runtime_repair_is_installed_last(self) -> None:
        text = (ROOT / "run_with_env.py").read_text(encoding="utf-8")
        self.assertIn("simplified_runtime.install()", text)
        self.assertGreater(
            text.index("simplified_runtime.install()"),
            text.index("applied_upgrades.install_engine()"),
        )


if __name__ == "__main__":
    unittest.main()
