from __future__ import annotations

from datetime import datetime
from typing import Callable

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:  # pragma: no cover - installation verification handles this
    BackgroundScheduler = None


JOB_DEFINITIONS = (
    ("provider-budget-refresh", "interval", {"seconds": 30}),
    ("market-session-refresh", "interval", {"minutes": 1}),
    ("universe-evaluation", "interval", {"minutes": 15}),
    ("universe-rotation", "interval", {"minutes": 30}),
    ("active-universe-quotes", "interval", {"minutes": 1}),
    ("full-strategy-scan", "interval", {"minutes": 5}),
    ("open-position-monitoring", "interval", {"minutes": 1}),
    ("market-intelligence-refresh", "interval", {"minutes": 5}),
    ("daily-reporting", "cron", {"hour": 15, "minute": 20}),
    ("weekly-reporting", "cron", {"day_of_week": "fri", "hour": 15, "minute": 30}),
    ("monthly-reporting", "cron", {"day": "last", "hour": 15, "minute": 40}),
    ("learning-results", "cron", {"hour": 16, "minute": 0}),
    ("learning-center-reconciliation", "interval", {"hours": 6}),
    ("strategy-control-reconciliation", "interval", {"minutes": 5}),
    ("diagnostics", "interval", {"minutes": 5}),
    ("database-backup", "cron", {"hour": 2, "minute": 0}),
    ("retention-cleanup", "cron", {"hour": 2, "minute": 30}),
)

LIVE_STARTUP_JOBS = (
    "active-universe-quotes",
    "full-strategy-scan",
    "open-position-monitoring",
    "market-intelligence-refresh",
)


class SchedulerService:
    def __init__(self, timezone: str = "America/Chicago") -> None:
        if BackgroundScheduler is None:
            raise RuntimeError("APScheduler is not installed")
        self.scheduler = BackgroundScheduler(
            timezone=timezone,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 120,
            },
        )
        self.startup_jobs_triggered: list[str] = []

    @property
    def running(self) -> bool:
        return bool(self.scheduler.running)

    def register(self, jobs: dict[str, Callable[[], object]]) -> None:
        for job_id, kind, parameters in JOB_DEFINITIONS:
            function = jobs.get(job_id, lambda: None)
            self.scheduler.add_job(
                function,
                kind,
                id=job_id,
                replace_existing=True,
                **parameters,
            )

    def start(self) -> None:
        self.scheduler.start()
        self.startup_jobs_triggered = self.trigger_now()

    def trigger_now(self, job_ids: tuple[str, ...] = LIVE_STARTUP_JOBS) -> list[str]:
        """Queue selected registered jobs for immediate scheduler execution.

        APScheduler executes the normal wrapped jobs in its background worker,
        preserving max-instances, receipts, diagnostics, and future cadence.
        The Discord event loop therefore remains free while market data and
        paper positions begin updating immediately after application startup.
        """

        now = datetime.now(self.scheduler.timezone)
        triggered: list[str] = []
        missing: list[str] = []
        for job_id in job_ids:
            job = self.scheduler.get_job(job_id)
            if job is None:
                missing.append(job_id)
                continue
            self.scheduler.modify_job(job_id, next_run_time=now)
            triggered.append(job_id)
        if missing:
            raise KeyError(f"Registered scheduler jobs are missing: {', '.join(missing)}")
        return triggered

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)
