from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics
import supervisor_diagnostic_runtime as supervisor_runtime


class SupervisorDiagnosticRuntimeTests(unittest.TestCase):
    def test_one_simple_supervisor_owning_health_port_passes(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "Processes": {
                        "ProcessId": 123,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                    "PortOwner": 123,
                }
            ),
            stderr="",
        )
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            check = supervisor_runtime.supervisor_process_check()
        self.assertTrue(check.passed)
        self.assertIn("simple supervisor processes=1", check.detail)
        self.assertIn("port 8876 owner=123", check.detail)

    def test_duplicate_supervisors_fail_without_immediate_github_escalation(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "Processes": [
                        {
                            "ProcessId": 1,
                            "CommandLine": "python run_supervisor_simple.py",
                        },
                        {
                            "ProcessId": 2,
                            "CommandLine": "python run_supervisor_simple.py",
                        },
                    ],
                    "PortOwner": 1,
                }
            ),
            stderr="",
        )
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            check = supervisor_runtime.supervisor_process_check()
        self.assertFalse(check.passed)
        self.assertFalse(check.force_upgrade)
        self.assertIn("simple supervisor processes=2", check.detail)
        self.assertIn("port 8876 owner=1", check.detail)

    def test_wrong_port_owner_fails(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "Processes": {
                        "ProcessId": 123,
                        "CommandLine": "python run_supervisor_simple.py",
                    },
                    "PortOwner": 999,
                }
            ),
            stderr="",
        )
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            check = supervisor_runtime.supervisor_process_check()
        self.assertFalse(check.passed)
        self.assertIn("port 8876 owner=999", check.detail)

    def test_stale_stop_flag_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            state.mkdir()
            (state / "supervisor-stop.flag").write_text("stop", encoding="utf-8")
            with patch.object(diagnostics, "ROOT", root):
                check = supervisor_runtime.stop_flag_check()
        self.assertFalse(check.passed)
        self.assertIn("Unexpected stop flag", check.detail)

    def test_healthy_watchdog_requires_zero_last_result(self) -> None:
        payload = {
            "TaskName": "Tradysquids Supervisor Watchdog",
            "State": "Ready",
            "LastTaskResult": 0,
            "LastRunTime": "today",
            "NextRunTime": "later",
        }
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            check = supervisor_runtime.watchdog_check()
        self.assertTrue(check.passed)
        self.assertIn("last_result=0", check.detail)

    def test_nonzero_watchdog_result_is_not_healthy(self) -> None:
        payload = {
            "TaskName": "Tradysquids Supervisor Watchdog",
            "State": "Ready",
            "LastTaskResult": 1,
            "LastRunTime": "today",
            "NextRunTime": "later",
        }
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            check = supervisor_runtime.watchdog_check()
        self.assertFalse(check.passed)
        self.assertIn("last_result=1", check.detail)

    def test_collect_appends_process_and_stop_flag_checks(self) -> None:
        base = diagnostics.HealthCheck("base", True, "base", "base", "ok")
        process = diagnostics.HealthCheck(
            "process", True, "supervisor", "process", "ok"
        )
        flag = diagnostics.HealthCheck(
            "flag", True, "supervisor", "flag", "ok"
        )
        with (
            patch.object(
                supervisor_runtime,
                "_BASE_COLLECT",
                return_value=([base], {"upgrade-review": {"id": "1"}}),
            ),
            patch.object(
                supervisor_runtime,
                "supervisor_process_check",
                return_value=process,
            ),
            patch.object(supervisor_runtime, "stop_flag_check", return_value=flag),
        ):
            checks, channels = supervisor_runtime.collect_health_checks(object())
        self.assertEqual(checks, [base, process, flag])
        self.assertIn("upgrade-review", channels)

    def test_install_captures_current_collect_chain(self) -> None:
        active = lambda connection: ([], {})
        original_startup = startup.collect_health_checks
        original_diagnostics = diagnostics.collect_health_checks
        original_watchdog = diagnostics._watchdog_check
        try:
            startup.collect_health_checks = active
            supervisor_runtime._INSTALLED = False
            supervisor_runtime._BASE_COLLECT = None
            supervisor_runtime.install()
            self.assertIs(supervisor_runtime._BASE_COLLECT, active)
            self.assertIs(startup.collect_health_checks, supervisor_runtime.collect_health_checks)
            self.assertIs(diagnostics._watchdog_check, supervisor_runtime.watchdog_check)
        finally:
            startup.collect_health_checks = original_startup
            diagnostics.collect_health_checks = original_diagnostics
            diagnostics._watchdog_check = original_watchdog
            supervisor_runtime._INSTALLED = False
            supervisor_runtime._BASE_COLLECT = None


if __name__ == "__main__":
    unittest.main()
