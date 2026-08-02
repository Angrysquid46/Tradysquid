"""Complete scheduler diagnostics with required-job and next-run evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable

import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
_BASE_JOB_CHECKS: Callable[[Any], list[diagnostics.HealthCheck]] | None = None

REQUIRED_JOBS = (
    "self-diagnostics",
    "market-hours-upgrade-review",
    "upgrade-lifecycle-dashboard",
    "applied-upgrades-dashboard",
    "upgrade-batch-44-acceptance",
    "upgrade-request-migration",
    "premarket-visibility",
    "managed-ticker-news",
    "managed-ticker-information",
    "outcome-learning",
    "system-activity",
    "active-market-regime",
    "intraday-chart-refresh",
    "dynamic-universe-rotation",
)


def _job_map() -> dict[str, Any]:
    return {job.name: job for job in diagnostics._engine().JOBS}


def _latest_receipt(connection: Any, name: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT status, started_at, COALESCE(finished_at, '') AS finished_at, detail
        FROM job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _active_interval(job: Any) -> timedelta:
    interval = job.interval
    if job.after_hours_interval and not diagnostics.ford_scan.market_is_open_now()[0]:
        interval = job.after_hours_interval
    return interval


def job_checks(connection: Any) -> list[diagnostics.HealthCheck]:
    if _BASE_JOB_CHECKS is None:
        raise RuntimeError("Scheduler diagnostic runtime was not installed")
    checks = list(_BASE_JOB_CHECKS(connection))
    jobs = _job_map()
    by_key = {check.key: index for index, check in enumerate(checks)}

    for name, job in jobs.items():
        key = f"job-{name}"
        index = by_key.get(key)
        if index is None:
            continue
        check = checks[index]
        receipt = _latest_receipt(connection, name)
        finished = diagnostics._parse_time((receipt or {}).get("finished_at"))
        interval = _active_interval(job)
        next_expected = finished + interval if finished else None
        retry = job.retry_interval or interval
        detail = (
            f"{check.detail}; registered=True; enabled=True; "
            f"next expected={next_expected.isoformat(timespec='seconds') if next_expected else 'after first successful receipt'}; "
            f"retry interval={int(retry.total_seconds())}s"
        )
        checks[index] = replace(check, detail=detail[:1900])

    for name in REQUIRED_JOBS:
        if name in jobs:
            continue
        checks.append(
            diagnostics.HealthCheck(
                f"required-job-{name}",
                False,
                "scheduler",
                f"required job {name}",
                f"Required scheduler job `{name}` is not registered.",
                severity="ERROR",
                runtime_target=name,
                automatic_retry="none; missing registration requires an upgrade repair",
                healthy_services="other registered jobs remain independent",
                repair_objective=f"Register exactly one enabled `{name}` job with a durable receipt and retry interval.",
                acceptance_tests=f"`{name}` is registered once, records an OK receipt, and reports a next expected run.",
                force_upgrade=True,
            )
        )
    return checks


def install() -> None:
    global _INSTALLED, _BASE_JOB_CHECKS
    if _INSTALLED:
        return
    _BASE_JOB_CHECKS = diagnostics._job_checks
    diagnostics._job_checks = job_checks
    _INSTALLED = True
