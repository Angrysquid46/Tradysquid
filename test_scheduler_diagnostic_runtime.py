from __future__ import annotations

import sqlite3
import unittest
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import diagnostic_upgrade_system as diagnostics
import scheduler_diagnostic_runtime as scheduler_runtime


@dataclass(frozen=True)
class FakeJob:
    name: str
    interval: timedelta
    callback: object = lambda connection: None
    market_hours_only: bool = False
    after_hours_interval: timedelta | None = None
    background: bool = True
    provider_heavy: bool = False
    retry_interval: timedelta | None = None


class SchedulerDiagnosticRuntimeTests(unittest.TestCase):
    def connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                detail TEXT
            )
            """
        )
        return connection

    def test_registered_job_includes_next_expected_and_retry_interval(self) -> None:
        connection = self.connection()
        connection.execute(
            """
            INSERT INTO job_runs(job_name,status,started_at,finished_at,detail)
            VALUES ('self-diagnostics','OK','2026-08-02T01:00:00-05:00','2026-08-02T01:01:00-05:00','ok')
            """
        )
        connection.commit()
        job = FakeJob(
            "self-diagnostics",
            timedelta(minutes=5),
            retry_interval=timedelta(minutes=2),
        )
        base = diagnostics.HealthCheck(
            "job-self-diagnostics",
            True,
            "scheduler",
            "job self-diagnostics",
            "status=OK",
        )
        engine = SimpleNamespace(JOBS=[job])
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(
                scheduler_runtime,
                "REQUIRED_JOBS",
                ("self-diagnostics",),
            ),
            patch.object(
                diagnostics.ford_scan,
                "market_is_open_now",
                return_value=(True, "open"),
            ),
        ):
            checks = scheduler_runtime.job_checks(connection)
        self.assertEqual(len(checks), 1)
        self.assertIn("registered=True", checks[0].detail)
        self.assertIn("enabled=True", checks[0].detail)
        self.assertIn("next expected=2026-08-02T01:06:00-05:00", checks[0].detail)
        self.assertIn("retry interval=120s", checks[0].detail)

    def test_missing_required_job_names_exact_job_and_forces_upgrade(self) -> None:
        connection = self.connection()
        engine = SimpleNamespace(JOBS=[])
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(
                scheduler_runtime,
                "REQUIRED_JOBS",
                ("self-diagnostics", "applied-upgrades-dashboard"),
            ),
        ):
            checks = scheduler_runtime.job_checks(connection)
        self.assertEqual(
            {check.runtime_target for check in checks},
            {"self-diagnostics", "applied-upgrades-dashboard"},
        )
        self.assertTrue(all(not check.passed for check in checks))
        self.assertTrue(all(check.force_upgrade for check in checks))
        self.assertTrue(
            all("not registered" in check.detail for check in checks)
        )

    def test_after_hours_interval_controls_next_expected_run(self) -> None:
        connection = self.connection()
        connection.execute(
            """
            INSERT INTO job_runs(job_name,status,started_at,finished_at,detail)
            VALUES ('market-hours-upgrade-review','OK','2026-08-02T01:00:00-05:00','2026-08-02T01:00:00-05:00','outside session')
            """
        )
        connection.commit()
        job = FakeJob(
            "market-hours-upgrade-review",
            timedelta(hours=2),
            after_hours_interval=timedelta(hours=6),
            retry_interval=timedelta(minutes=15),
        )
        base = diagnostics.HealthCheck(
            "job-market-hours-upgrade-review",
            True,
            "scheduler",
            "job market-hours-upgrade-review",
            "status=OK",
        )
        engine = SimpleNamespace(JOBS=[job])
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(
                scheduler_runtime,
                "REQUIRED_JOBS",
                ("market-hours-upgrade-review",),
            ),
            patch.object(
                diagnostics.ford_scan,
                "market_is_open_now",
                return_value=(False, "closed"),
            ),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertIn("next expected=2026-08-02T07:00:00-05:00", check.detail)
        self.assertIn("retry interval=900s", check.detail)

    def test_install_wraps_current_job_check_chain(self) -> None:
        active = lambda connection: []
        original = diagnostics._job_checks
        try:
            diagnostics._job_checks = active
            scheduler_runtime._INSTALLED = False
            scheduler_runtime._BASE_JOB_CHECKS = None
            scheduler_runtime.install()
            self.assertIs(scheduler_runtime._BASE_JOB_CHECKS, active)
            self.assertIs(diagnostics._job_checks, scheduler_runtime.job_checks)
        finally:
            diagnostics._job_checks = original
            scheduler_runtime._INSTALLED = False
            scheduler_runtime._BASE_JOB_CHECKS = None


if __name__ == "__main__":
    unittest.main()
