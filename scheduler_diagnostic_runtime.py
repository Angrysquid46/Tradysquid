"""Scheduler diagnostics for current information-engine work only.

Completed upgrade migrations and acceptance dashboards are not runtime services.
This module checks the current scanner, information, learning, chart, universe,
and self-diagnostic jobs against their actual active schedules.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable

import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
_BASE_JOB_CHECKS: Callable[[Any], list[diagnostics.HealthCheck]] | None = None
STARTUP_GRACE = timedelta(minutes=20)

REQUIRED_JOBS = (
    "self-diagnostics",
    "provider-event-queue",
    "spy-market-data-capture",
    "active-premarket",
    "active-market-regime",
    "intraday-chart-refresh",
    "competition-surfaces",
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


def _market_open() -> bool:
    try:
        return bool(diagnostics.market_data.market_is_open_now()[0])
    except Exception:
        return False


def _active_interval(job: Any) -> timedelta:
    if not _market_open() and job.after_hours_interval:
        return job.after_hours_interval
    return job.interval


def _expected_to_run_now(job: Any) -> bool:
    if getattr(job, "market_hours_only", False) and not _market_open():
        return bool(getattr(job, "after_hours_interval", None))
    return True


def _engine_started_at():
    state = diagnostics._read_json(diagnostics.SUPERVISOR_STATE_PATH)
    times = (
        state.get("service_last_started_at")
        if isinstance(state.get("service_last_started_at"), dict)
        else {}
    )
    return diagnostics._parse_time(
        times.get("information-engine")
        or state.get("information_engine_started_at")
        or state.get("supervisor_heartbeat_at")
    )


def _within_startup_grace() -> bool:
    started = _engine_started_at()
    return bool(started and diagnostics.now() - started <= STARTUP_GRACE)


def _receipt_predates_engine(receipt: dict[str, Any] | None) -> bool:
    if not receipt:
        return True
    started = _engine_started_at()
    finished = diagnostics._parse_time(receipt.get("finished_at"))
    return bool(started and (not finished or finished < started))


def _running_receipt_is_healthy(
    receipt: dict[str, Any] | None,
    interval: timedelta,
) -> bool:
    """A current RUNNING receipt is healthy until it exceeds the stuck limit."""
    if not receipt or str(receipt.get("status") or "").upper() != "RUNNING":
        return False
    started = diagnostics._parse_time(receipt.get("started_at"))
    if not started:
        return False
    elapsed = diagnostics.now() - started
    stuck_after = max(interval * 2, timedelta(minutes=20))
    return timedelta(0) <= elapsed <= stuck_after


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

        if _running_receipt_is_healthy(receipt, interval):
            check = replace(
                check,
                passed=True,
                severity="INFO",
                detail=(
                    f"{check.detail}; schedule state=actively running; "
                    "the current receipt is neither overdue nor stuck"
                ),
            )
        elif not _expected_to_run_now(job):
            check = replace(
                check,
                passed=True,
                severity="INFO",
                detail=(
                    f"{check.detail}; schedule state=outside market session; "
                    "the market-hours-only job is not expected to run now"
                ),
            )
        elif _within_startup_grace() and _receipt_predates_engine(receipt):
            check = replace(
                check,
                passed=True,
                severity="INFO",
                detail=(
                    f"{check.detail}; schedule state=startup grace; preserved receipt "
                    "predates the current information-engine process"
                ),
            )

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
                automatic_retry="none; missing registration requires a repair",
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
