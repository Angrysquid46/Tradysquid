from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import diagnostic_upgrade_system as diagnostics
import supervisor_diagnostic_runtime as supervisor_runtime


class SupervisorDiagnosticRuntimeTests(unittest.TestCase):
    def process_check(self, payload):
        result = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            return supervisor_runtime.supervisor_process_check()

    def watchdog(self, payload):
        result = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        with (
            patch.object(supervisor_runtime.os, "name", "nt"),
            patch.object(supervisor_runtime.subprocess, "run", return_value=result),
        ):
            return supervisor_runtime.watchdog_check()

    def test_single_interpreter_owning_health_port_passes(self) -> None:
        check = self.process_check(
            {
                "Processes": {
                    "ProcessId": 123,
                    "ParentProcessId": 10,
                    "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                },
                "PortOwner": 123,
                "OwnerTreeIds": [123, 10],
            }
        )
        self.assertTrue(check.passed)
        self.assertIn("matched supervisor processes=1", check.detail)
        self.assertIn("foreign supervisor PIDs=[]", check.detail)

    def test_python_wrapper_and_interpreter_in_same_owner_tree_pass(self) -> None:
        check = self.process_check(
            {
                "Processes": [
                    {
                        "ProcessId": 100,
                        "ParentProcessId": 50,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                    {
                        "ProcessId": 123,
                        "ParentProcessId": 100,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                ],
                "PortOwner": 123,
                "OwnerTreeIds": [123, 100, 50],
            }
        )
        self.assertTrue(check.passed)
        self.assertIn("matched supervisor processes=2", check.detail)
        self.assertIn("owner tree PIDs=[50, 100, 123]", check.detail)
        self.assertIn("foreign supervisor PIDs=[]", check.detail)

    def test_second_independent_supervisor_tree_fails(self) -> None:
        check = self.process_check(
            {
                "Processes": [
                    {
                        "ProcessId": 100,
                        "ParentProcessId": 50,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                    {
                        "ProcessId": 123,
                        "ParentProcessId": 100,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                    {
                        "ProcessId": 999,
                        "ParentProcessId": 888,
                        "CommandLine": "python run_with_env.py run_supervisor_simple.py",
                    },
                ],
                "PortOwner": 123,
                "OwnerTreeIds": [123, 100, 50],
            }
        )
        self.assertFalse(check.passed)
        self.assertFalse(check.force_upgrade)
        self.assertIn("foreign supervisor PIDs=[999]", check.detail)

    def test_wrong_port_owner_fails(self) -> None:
        check = self.process_check(
            {
                "Processes": {
                    "ProcessId": 123,
                    "ParentProcessId": 10,
                    "CommandLine": "python run_supervisor_simple.py",
                },
                "PortOwner": 999,
                "OwnerTreeIds": [999],
            }
        )
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

    def test_completed_watchdog_is_healthy(self) -> None:
        check = self.watchdog(
            {
                "TaskName": "Tradysquids Supervisor Watchdog",
                "State": "Ready",
                "LastTaskResult": 0,
                "LastRunTime": "today",
                "NextRunTime": "later",
            }
        )
        self.assertTrue(check.passed)
        self.assertIn("last_result=0", check.detail)

    def test_currently_running_watchdog_is_healthy(self) -> None:
        check = self.watchdog(
            {
                "TaskName": "Tradysquids Supervisor Watchdog",
                "State": "Running",
                "LastTaskResult": supervisor_runtime.TASK_RESULT_RUNNING,
                "LastRunTime": "today",
                "NextRunTime": "later",
            }
        )
        self.assertTrue(check.passed)
        self.assertIn("last_result=267009", check.detail)

    def test_running_result_without_running_state_is_not_healthy(self) -> None:
        check = self.watchdog(
            {
                "TaskName": "Tradysquids Supervisor Watchdog",
                "State": "Ready",
                "LastTaskResult": supervisor_runtime.TASK_RESULT_RUNNING,
                "LastRunTime": "today",
                "NextRunTime": "later",
            }
        )
        self.assertFalse(check.passed)

    def test_real_nonzero_watchdog_result_is_not_healthy(self) -> None:
        check = self.watchdog(
            {
                "TaskName": "Tradysquids Supervisor Watchdog",
                "State": "Ready",
                "LastTaskResult": 3,
                "LastRunTime": "today",
                "NextRunTime": "later",
            }
        )
        self.assertFalse(check.passed)
        self.assertIn("last_result=3", check.detail)

    def test_collect_appends_process_and_stop_flag_checks(self) -> None:
        base = diagnostics.HealthCheck("base", True, "base", "base", "ok")
        process = diagnostics.HealthCheck("process", True, "supervisor", "process", "ok")
        flag = diagnostics.HealthCheck("flag", True, "supervisor", "flag", "ok")
        with (
            patch.object(
                supervisor_runtime,
                "_BASE_COLLECT",
                return_value=([base], {"upgrade-review": {"id": "1"}}),
            ),
            patch.object(supervisor_runtime, "supervisor_process_check", return_value=process),
            patch.object(supervisor_runtime, "stop_flag_check", return_value=flag),
        ):
            checks, channels = supervisor_runtime.collect_health_checks(object())
        self.assertEqual(checks, [base, process, flag])
        self.assertIn("upgrade-review", channels)

    def test_install_wraps_current_diagnostic_collect_chain(self) -> None:
        active = lambda connection: ([], {})
        original_diagnostics = diagnostics.collect_health_checks
        original_watchdog = diagnostics._watchdog_check
        try:
            diagnostics.collect_health_checks = active
            supervisor_runtime._INSTALLED = False
            supervisor_runtime._BASE_COLLECT = None
            supervisor_runtime.install()
            self.assertIs(supervisor_runtime._BASE_COLLECT, active)
            self.assertIs(diagnostics.collect_health_checks, supervisor_runtime.collect_health_checks)
            self.assertIs(diagnostics._watchdog_check, supervisor_runtime.watchdog_check)
        finally:
            diagnostics.collect_health_checks = original_diagnostics
            diagnostics._watchdog_check = original_watchdog
            supervisor_runtime._INSTALLED = False
            supervisor_runtime._BASE_COLLECT = None


if __name__ == "__main__":
    unittest.main()
