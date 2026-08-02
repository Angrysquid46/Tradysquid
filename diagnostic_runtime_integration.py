"""Narrow runtime integration for diagnostics and applied-upgrade proof.

The active infrastructure renderer is captured at install time, after the simple
updater runtime has installed its cards. This prevents import order from silently
replacing the active updater proof with an obsolete renderer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

import applied_upgrades as dashboard
import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
_BASE_JOB_CHECKS: Callable[[Any], list[diagnostics.HealthCheck]] | None = None
_BASE_INFRA_RECORDS: Callable[[Any, dict[str, dict[str, Any]]], list[dict[str, Any]]] | None = None

DIAGNOSTIC_SPECS = (
    dashboard.UpgradeSpec(
        "shared-diagnostic-upgrade-path",
        "Shared diagnostic upgrade path",
        "Persistent failures become DIAGNOSTIC-GENERATED requests in the same GitHub batch as owner requests.",
        "diagnostic_upgrade_system.record_failure → github_upgrade_bridge.add_or_update_diagnostic",
        ("upgrade-review", "upgrade-requests"),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "five-minute-self-diagnostics",
        "Five-minute self diagnostics",
        "Checks supervisor, services, Git, Discord, scheduler receipts, logs, and applied-upgrade proof without restarting healthy services.",
        "self-diagnostics → diagnostic_upgrade_system.diagnostic_cycle_job",
        ("upgrade-review",),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "two-hour-market-review",
        "Two-hour market-hours upgrade review",
        "Reviews waiting batches, diagnostic requests, pull requests, CI, deployment, and verification during official sessions.",
        "market-hours-upgrade-review → diagnostic_upgrade_system.market_upgrade_review_job",
        ("upgrade-review",),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "diagnostic-live-acceptance",
        "Diagnostic live acceptance",
        "Lists each runtime acceptance item separately and updates one stable review card.",
        "diagnostic_upgrade_system._post_live_acceptance",
        ("upgrade-review", "applied-upgrades"),
        group="Upgrade delivery and verification",
    ),
)


def job_checks(connection: Any) -> list[diagnostics.HealthCheck]:
    if _BASE_JOB_CHECKS is None:
        raise RuntimeError("Diagnostic job integration was not installed")
    checks = _BASE_JOB_CHECKS(connection)
    refined: list[diagnostics.HealthCheck] = []
    for check in checks:
        detail = check.detail.casefold()
        if "no scheduler receipt exists yet" in detail:
            refined.append(
                replace(
                    check,
                    passed=True,
                    severity="INFO",
                    detail=(
                        check.detail
                        + " The registered job is awaiting its first scheduled run."
                    ),
                )
            )
            continue
        if "status=running" in detail and "stuck=false" in detail:
            refined.append(
                replace(
                    check,
                    passed=True,
                    severity="INFO",
                    detail=(
                        check.detail
                        + " The job is currently running within its allowed window."
                    ),
                )
            )
            continue
        refined.append(check)
    return refined


def diagnostic_infra_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if _BASE_INFRA_RECORDS is None:
        raise RuntimeError("Applied-upgrade diagnostic integration was not installed")
    records = list(_BASE_INFRA_RECORDS(connection, channels))
    jobs = {job.name: job for job in dashboard._engine().JOBS}
    summary = diagnostics.diagnostics_summary()
    open_count = len(summary.get("open") or [])

    for spec in DIAGNOSTIC_SPECS:
        channels_present, affected, channel_detail = dashboard._channel_proof(
            spec, channels
        )
        if spec.key == "shared-diagnostic-upgrade-path":
            attached = all(
                marker
                in (diagnostics.ROOT / "github_upgrade_bridge.py").read_text(
                    encoding="utf-8"
                )
                for marker in (
                    "add_or_update_diagnostic",
                    "AUTOMATIC DIAGNOSTIC",
                    "DIAGNOSTIC-GENERATED",
                )
            )
            status = "PASS" if attached else "FAIL"
            detail = f"shared batch bridge attached; {open_count} open diagnostic(s)"
        elif spec.key == "five-minute-self-diagnostics":
            job = jobs.get(diagnostics.DIAGNOSTIC_JOB)
            attached = bool(
                job and job.callback is diagnostics.diagnostic_cycle_job
            )
            status, detail = dashboard._job_status(
                connection, diagnostics.DIAGNOSTIC_JOB
            )
        elif spec.key == "two-hour-market-review":
            job = jobs.get(diagnostics.MARKET_REVIEW_JOB)
            attached = bool(
                job and job.callback is diagnostics.market_upgrade_review_job
            )
            status, detail = dashboard._job_status(
                connection, diagnostics.MARKET_REVIEW_JOB
            )
        else:
            attached = bool(
                jobs.get(diagnostics.DIAGNOSTIC_JOB)
                and diagnostics.ACCEPTANCE_MESSAGE_KEY
            )
            message_id = dashboard._engine().get_state(
                connection, diagnostics.ACCEPTANCE_MESSAGE_KEY, ""
            )
            status = "PASS" if message_id else "PENDING"
            detail = (
                f"live acceptance message acknowledged as {message_id}"
                if message_id
                else "live acceptance is attached; first Discord acknowledgement is pending"
            )
        records.append(
            dashboard._record(
                spec,
                implementation_attached=attached,
                channels_present=channels_present,
                affected=affected,
                channel_detail=channel_detail,
                runtime_status=status,
                runtime_detail=detail,
            )
        )
    return records


def install() -> None:
    global _INSTALLED, _BASE_JOB_CHECKS, _BASE_INFRA_RECORDS
    if _INSTALLED:
        return
    _BASE_JOB_CHECKS = diagnostics._job_checks
    _BASE_INFRA_RECORDS = dashboard._infra_records
    diagnostics._job_checks = job_checks
    existing = {spec.key for spec in dashboard.INFRA_SPECS}
    dashboard.INFRA_SPECS = (
        *dashboard.INFRA_SPECS,
        *(spec for spec in DIAGNOSTIC_SPECS if spec.key not in existing),
    )
    dashboard.ALL_SPECS = (*dashboard.BATCH_SPECS, *dashboard.INFRA_SPECS)
    dashboard._infra_records = diagnostic_infra_records
    _INSTALLED = True
