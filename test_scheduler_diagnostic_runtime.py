from __future__ import annotations

import sqlite3
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    def test_required_jobs_match_the_current_live_scheduler_contract(self) -> None:
        self.assertEqual(
            scheduler_runtime.REQUIRED_JOBS,
            (
                "self-diagnostics",
                "provider-event-queue",
                "spy-market-data-capture",
                "active-premarket",
                "active-market-regime",
                "intraday-chart-refresh",
                "competition-surfaces",
            ),
        )

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
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ("self-diagnostics",)),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(True, "open")),
            patch.object(scheduler_runtime, "_within_startup_grace", return_value=False),
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
        self.assertTrue(all("not registered" in check.detail for check in checks))

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
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ("market-hours-upgrade-review",)),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(False, "closed")),
            patch.object(scheduler_runtime, "_within_startup_grace", return_value=False),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertIn("next expected=2026-08-02T07:00:00-05:00", check.detail)
        self.assertIn("retry interval=900s", check.detail)

    def test_market_hours_only_job_is_not_overdue_while_market_closed(self) -> None:
        connection = self.connection()
        job = FakeJob(
            "position-tracker",
            timedelta(minutes=5),
            market_hours_only=True,
        )
        base = diagnostics.HealthCheck(
            "job-position-tracker",
            False,
            "scheduler",
            "job position-tracker",
            "status=OK; overdue=True; preserved Friday receipt",
            severity="WARNING",
        )
        engine = SimpleNamespace(JOBS=[job])
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ()),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(False, "weekend")),
            patch.object(scheduler_runtime, "_within_startup_grace", return_value=False),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertTrue(check.passed)
        self.assertEqual(check.severity, "INFO")
        self.assertIn("outside market session", check.detail)

    def test_preserved_receipt_predating_new_engine_uses_startup_grace(self) -> None:
        connection = self.connection()
        connection.execute(
            """
            INSERT INTO job_runs(job_name,status,started_at,finished_at,detail)
            VALUES ('position-tracker','OK','2026-07-31T14:58:07-05:00','2026-07-31T14:58:07-05:00','24 refreshed')
            """
        )
        connection.commit()
        job = FakeJob("position-tracker", timedelta(minutes=5))
        base = diagnostics.HealthCheck(
            "job-position-tracker",
            False,
            "scheduler",
            "job position-tracker",
            "status=OK; overdue=True",
            severity="WARNING",
        )
        engine = SimpleNamespace(JOBS=[job])
        engine_started = datetime(2026, 8, 2, 4, 0, tzinfo=timezone(timedelta(hours=-5)))
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ()),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(True, "open")),
            patch.object(scheduler_runtime, "_engine_started_at", return_value=engine_started),
            patch.object(
                diagnostics,
                "now",
                return_value=engine_started + timedelta(minutes=5),
            ),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertTrue(check.passed)
        self.assertEqual(check.severity, "INFO")
        self.assertIn("startup grace", check.detail)
        self.assertIn("predates", check.detail)

    def test_current_running_job_is_healthy_until_stuck_limit(self) -> None:
        connection = self.connection()
        connection.execute(
            """
            INSERT INTO job_runs(job_name,status,started_at,finished_at,detail)
            VALUES ('premarket-visibility','RUNNING','2026-08-02T15:03:25-05:00','','')
            """
        )
        connection.commit()
        job = FakeJob(
            "premarket-visibility",
            timedelta(minutes=45),
            retry_interval=timedelta(minutes=2),
        )
        base = diagnostics.HealthCheck(
            "job-premarket-visibility",
            False,
            "scheduler",
            "job premarket-visibility",
            "status=RUNNING; finished=pending; overdue=False; stuck=False",
            severity="WARNING",
        )
        engine = SimpleNamespace(JOBS=[job])
        current = datetime(2026, 8, 2, 15, 4, 39, tzinfo=timezone(timedelta(hours=-5)))
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ()),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(True, "open")),
            patch.object(diagnostics, "now", return_value=current),
            patch.object(scheduler_runtime, "_within_startup_grace", return_value=False),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertTrue(check.passed)
        self.assertEqual(check.severity, "INFO")
        self.assertIn("actively running", check.detail)
        self.assertIn("neither overdue nor stuck", check.detail)

    def test_running_job_still_fails_after_stuck_limit(self) -> None:
        connection = self.connection()
        connection.execute(
            """
            INSERT INTO job_runs(job_name,status,started_at,finished_at,detail)
            VALUES ('self-diagnostics','RUNNING','2026-08-02T14:30:00-05:00','','')
            """
        )
        connection.commit()
        job = FakeJob("self-diagnostics", timedelta(minutes=5))
        base = diagnostics.HealthCheck(
            "job-self-diagnostics",
            False,
            "scheduler",
            "job self-diagnostics",
            "status=RUNNING; finished=pending; overdue=False; stuck=True",
            severity="ERROR",
        )
        engine = SimpleNamespace(JOBS=[job])
        current = datetime(2026, 8, 2, 15, 4, 43, tzinfo=timezone(timedelta(hours=-5)))
        with (
            patch.object(scheduler_runtime, "_BASE_JOB_CHECKS", return_value=[base]),
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(scheduler_runtime, "REQUIRED_JOBS", ()),
            patch.object(diagnostics.market_data, "market_is_open_now", return_value=(True, "open")),
            patch.object(diagnostics, "now", return_value=current),
            patch.object(scheduler_runtime, "_within_startup_grace", return_value=False),
        ):
            check = scheduler_runtime.job_checks(connection)[0]
        self.assertFalse(check.passed)
        self.assertEqual(check.severity, "ERROR")
        self.assertNotIn("actively running", check.detail)

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
