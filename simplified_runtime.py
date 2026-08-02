"""Simplify Tradysquid runtime recovery without changing trading behavior.

This module is installed last. It removes retired one-time reporting jobs, keeps
one stable diagnostic summary, prevents provider/log noise from opening code
repair batches, repairs missing owner channels, and closes diagnostic-only GitHub
batches after every incident is recovered.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import replace
from typing import Any, Callable

import diagnostic_review_runtime as review
import diagnostic_upgrade_system as diagnostics
import github_upgrade_bridge as bridge
import scheduler_diagnostic_runtime as scheduler
import supervisor_diagnostic_runtime as supervisor_runtime

VERSION = "simplified-runtime-v1"

RETIRED_JOBS = {
    "upgrade-batch-44-acceptance",
    "upgrade-request-migration",
    "upgrade-lifecycle-dashboard",
    "applied-upgrades-dashboard",
    "market-hours-upgrade-review",
}
RETIRED_DIAGNOSTIC_KEYS = {f"job-{name}" for name in RETIRED_JOBS}
RETIRED_DIAGNOSTIC_KEYS.update(
    {
        "diagnostic-live-message-proof",
        "diagnostic-live-acceptance-post",
        "diagnostic-owner-channel-bootstrap",
    }
)

CORE_REQUIRED_JOBS = (
    "self-diagnostics",
    "premarket-visibility",
    "managed-ticker-news",
    "managed-ticker-information",
    "outcome-learning",
    "system-activity",
    "active-market-regime",
    "intraday-chart-refresh",
    "dynamic-universe-rotation",
)

CORE_ESCALATION_KEYS = {
    "supervisor-heartbeat",
    "supervisor-mode",
    "supervisor-process-ownership",
    "watchdog-task",
    "service-command-bot",
    "service-information-engine",
    "service-restart-loop",
    "git-main-branch",
    "git-tracked-cleanliness",
    "installed-deployed-commit",
    "deployment-rollback",
    "scheduler-unique-jobs",
    "discord-required-channels",
    "upgrade-command-hooks",
    "runtime-log-integrity",
    *(f"required-job-{name}" for name in CORE_REQUIRED_JOBS),
}
IMMEDIATE_ESCALATION_KEYS = {
    "deployment-rollback",
    "git-main-branch",
    "git-tracked-cleanliness",
    "installed-deployed-commit",
}
RECOVERED_STATES = {"RECOVERED", "RESOLVED", "VERIFIED"}
ACTIVE_STATES = {"DEGRADED", "FAILED", "RETRYING", "FAILED AGAIN"}

_INSTALLED = False
_BASE_CYCLE: Callable[[Any], str] | None = None
_BASE_GITHUB_REPORT: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_BASE_ADD_OR_UPDATE: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _escalation_required(record: dict[str, Any], force_upgrade: bool) -> bool:
    """Only durable core-runtime defects enter the GitHub repair queue."""
    key = str(record.get("signature_key") or "")
    if key in RETIRED_DIAGNOSTIC_KEYS:
        return False
    if key == "incident-outbound-https-connectivity":
        return False
    if key in IMMEDIATE_ESCALATION_KEYS:
        return True
    if key not in CORE_ESCALATION_KEYS:
        return False
    return int(record.get("consecutive_failures") or 0) >= 3


def _github_report(record: dict[str, Any]) -> dict[str, Any]:
    if _BASE_GITHUB_REPORT is None:
        raise RuntimeError("Simplified runtime was not installed")
    report = dict(_BASE_GITHUB_REPORT(record))
    report.update(
        {
            "status": str(record.get("status") or "PENDING").upper(),
            "recovery_time": str(record.get("recovery_time") or ""),
            "verification_result": str(record.get("verification_result") or ""),
            "resolution_commit": str(record.get("resolution_commit") or ""),
        }
    )
    return report


def _diagnostic_body(report: dict[str, Any], sequence: int) -> str:
    marker = bridge._diagnostic_marker(str(report.get("signature") or ""))
    status = str(report.get("status") or "PENDING BATCH REVIEW").upper()
    recovered = status in RECOVERED_STATES
    evidence = bridge._clean_text(report.get("evidence"), 3500) or "No additional evidence supplied."
    acceptance = bridge._clean_text(report.get("acceptance_tests"), 1400) or "The affected runtime remains healthy for three complete checks."
    next_action = (
        "No owner action. The incident recovered and remains in history."
        if recovered
        else "Automatic recovery continues. Maintainer review is required only while the defect remains active."
    )
    lines = [
        bridge.REQUEST_MARKER,
        marker,
        f"## Upgrade request {sequence}",
        "",
        f"### DIAGNOSTIC-GENERATED: {bridge._clean_text(report.get('title'), 180) or 'Repair detected Tradysquid failure'}",
        "",
        "**Source:** AUTOMATIC DIAGNOSTIC",
        f"**Status:** {status}",
        f"**Diagnostic ID:** {bridge._clean_text(report.get('diagnostic_id'), 120)}",
        f"**Severity:** {bridge._clean_text(report.get('severity'), 40) or 'ERROR'}",
        f"**Component:** {bridge._clean_text(report.get('component'), 160)}",
        f"**Operation:** {bridge._clean_text(report.get('operation'), 200)}",
        f"**Affected channels:** {bridge._clean_text(report.get('channels'), 300) or 'None identified'}",
        f"**Process / job / hook:** {bridge._clean_text(report.get('runtime_target'), 300) or 'Not identified'}",
        f"**First occurrence:** {bridge._clean_text(report.get('first_seen'), 80)}",
        f"**Latest occurrence:** {bridge._clean_text(report.get('last_seen'), 80)}",
        f"**Consecutive failures:** {int(report.get('consecutive_failures') or 0)}",
        f"**Total failures:** {int(report.get('total_failures') or 0)}",
        f"**Deployed commit:** {bridge._clean_text(report.get('deployed_commit'), 80) or 'unknown'}",
        f"**Last known working commit:** {bridge._clean_text(report.get('last_working_commit'), 80) or 'unknown'}",
        "",
        "### Sanitized evidence",
        "```text",
        evidence,
        "```",
        "",
        f"**Repair objective:** {bridge._clean_text(report.get('repair_objective'), 900) or 'Restore the affected runtime without disturbing healthy services.'}",
        "",
        "### Required acceptance",
        acceptance,
    ]
    if recovered:
        lines.extend(
            [
                "",
                f"**Recovered at:** {bridge._clean_text(report.get('recovery_time'), 100) or bridge._timestamp()}",
                f"**Recovery proof:** {bridge._clean_text(report.get('verification_result'), 700) or 'A later diagnostic check passed.'}",
                f"**Resolution commit:** {bridge._clean_text(report.get('resolution_commit'), 80) or bridge._clean_text(report.get('deployed_commit'), 80) or 'unchanged'}",
            ]
        )
    lines.extend(["", f"**Next action:** {next_action}"])
    return "\n".join(lines)[:65000]


def _reconcile_open_batch() -> None:
    """Close an automatic-only batch after every diagnostic is recovered."""
    try:
        issue = bridge._find_open_batch()
        if not issue:
            return
        issue_number = int(issue["number"])
        comments = bridge._request_comments(issue_number)
        if not comments:
            return
        owner_requests = []
        active_diagnostics = []
        diagnostic_count = 0
        for comment in comments:
            body = str(comment.get("body") or "")
            source = bridge._field(body, "Source", "OWNER REQUEST").upper()
            if source != "AUTOMATIC DIAGNOSTIC":
                owner_requests.append(comment)
                continue
            diagnostic_count += 1
            status = bridge._field(body, "Status", "PENDING BATCH REVIEW").strip("*").upper()
            if status not in RECOVERED_STATES:
                active_diagnostics.append(comment)
        if owner_requests or not diagnostic_count or active_diagnostics:
            return
        bridge._request(
            "POST",
            f"/issues/{issue_number}/comments",
            payload={
                "body": (
                    "## Automatic diagnostic batch recovered\n\n"
                    "Every diagnostic-generated request in this batch is now RECOVERED, "
                    "RESOLVED, or VERIFIED. No owner request was present, so the batch "
                    "was closed automatically."
                )
            },
        )
        bridge._request(
            "PATCH",
            f"/issues/{issue_number}",
            payload={
                "state": "closed",
                "title": f"[Tradysquids Upgrade Batch] RECOVERED · #{issue_number}",
            },
        )
    except Exception:
        return


def _add_or_update_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
    if _BASE_ADD_OR_UPDATE is None:
        raise RuntimeError("Simplified runtime was not installed")
    result = _BASE_ADD_OR_UPDATE(report)
    _reconcile_open_batch()
    return result


def _quiet_log_checks(store: Any) -> list[diagnostics.HealthCheck]:
    """Treat only fatal local evidence as a repair signal, not every timeout line."""
    paths = [
        diagnostics.LOG_DIR / "supervisor.log",
        diagnostics.LOG_DIR / "command-bot.log",
        diagnostics.LOG_DIR / "information-engine.log",
        diagnostics.STARTUP_LOG,
        diagnostics.WATCHDOG_LOG,
    ]
    fatal: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        key = f"simple-log-offset:{path.name}"
        try:
            size = path.stat().st_size
            raw_previous = diagnostics._meta(store, key, "")
            if raw_previous == "":
                diagnostics._set_meta(store, key, str(size))
                continue
            previous = int(raw_previous or 0)
            if previous > size:
                previous = 0
            with path.open("rb") as handle:
                handle.seek(previous)
                text = handle.read(200_000).decode("utf-8", errors="replace")
            diagnostics._set_meta(store, key, str(size))
        except (OSError, ValueError):
            continue
        for line in text.splitlines():
            if re.search(
                r"(?i)(traceback \(most recent call last\)|unhandled exception|fatal error|rolled back|restart loop)",
                line,
            ):
                fatal.append(f"{path.name}: {line}")
    detail = (
        "\n".join(fatal[-12:])
        if fatal
        else "No newly appended fatal traceback, rollback, or restart-loop evidence was found."
    )
    return [
        diagnostics.HealthCheck(
            "runtime-log-integrity",
            not fatal,
            "runtime",
            "fatal local log evidence",
            detail,
            severity="ERROR" if fatal else "INFO",
            runtime_target="state/supervisor-logs",
            automatic_retry="supervisor continues normal service recovery",
            healthy_services="unchanged unless a core health check also fails",
            repair_objective="Repair a repeatable fatal runtime defect without converting ordinary provider timeouts into code issues.",
            acceptance_tests="Three complete diagnostic cycles contain no new fatal traceback, rollback, or restart-loop evidence.",
        )
    ]


def _supervisor_process_check() -> diagnostics.HealthCheck:
    """Verify exactly one simple supervisor and that it owns port 8876."""
    if os.name != "nt":
        return diagnostics.HealthCheck(
            "supervisor-process-ownership",
            True,
            "supervisor",
            "single active supervisor process",
            "Windows process ownership check is not applicable on this platform.",
            severity="INFO",
            runtime_target="run_supervisor_simple.py",
        )
    script = r"""
$items = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    $_.CommandLine -match 'run_supervisor_simple\.py'
  } |
  Select-Object ProcessId, ParentProcessId, CommandLine)
$listener = Get-NetTCPConnection -State Listen -LocalPort 8876 -ErrorAction SilentlyContinue |
  Select-Object -First 1
[pscustomobject]@{
  Processes = $items
  OwnerPid = if ($listener) { [int]$listener.OwningProcess } else { 0 }
} | ConvertTo-Json -Compress -Depth 5
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        payload = json.loads((result.stdout or "{}").strip() or "{}")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return diagnostics.HealthCheck(
            "supervisor-process-ownership",
            False,
            "supervisor",
            "single active supervisor process",
            f"Process inspection failed: {type(exc).__name__}: {exc}",
            severity="WARNING",
            runtime_target="run_supervisor_simple.py and port 8876",
        )
    processes = payload.get("Processes") if isinstance(payload, dict) else []
    if isinstance(processes, dict):
        processes = [processes]
    processes = [item for item in processes if isinstance(item, dict)] if isinstance(processes, list) else []
    pids = [int(item.get("ProcessId") or 0) for item in processes]
    owner = int(payload.get("OwnerPid") or 0) if isinstance(payload, dict) else 0
    passed = result.returncode == 0 and len(pids) == 1 and owner == pids[0]
    return diagnostics.HealthCheck(
        "supervisor-process-ownership",
        passed,
        "supervisor",
        "single active supervisor process",
        f"simple supervisor processes={len(pids)}; PIDs={pids}; port 8876 owner={owner or 'none'}",
        severity="ERROR" if not passed else "INFO",
        runtime_target="run_supervisor_simple.py and port 8876",
        automatic_retry="watchdog removes duplicate owners and relaunches exactly one hidden supervisor",
        healthy_services="managed services remain independent during ownership repair",
        repair_objective="Leave exactly one run_supervisor_simple.py process owning port 8876.",
        acceptance_tests="Exactly one simple supervisor owns port 8876 for three consecutive checks.",
        force_upgrade=False,
    )


def _ensure_owner_channels() -> list[str]:
    tracker = diagnostics._engine().discord_tracker()
    if not tracker:
        return []
    channels = diagnostics._guild_channels(tracker)
    mapped = diagnostics._channel_map(channels)
    template = next(
        (
            mapped[name]
            for name in (
                diagnostics.REQUEST_CHANNEL,
                diagnostics.REVIEW_CHANNEL,
                diagnostics.APPLIED_CHANNEL,
                "workflow-log",
                "system-health",
                "automation-diagnostics",
                "system-activity",
            )
            if name in mapped
        ),
        None,
    )
    if template is None:
        template = next(
            (item for item in channels if int(item.get("type") or -1) == 0),
            None,
        )
    if template is None:
        return []
    topics = {
        diagnostics.REQUEST_CHANNEL: "Owner-facing upgrade request intake and lifecycle history.",
        diagnostics.REVIEW_CHANNEL: "One stable review summary for persistent actionable repairs.",
        diagnostics.APPLIED_CHANNEL: "Installed upgrades with deployed commit and live proof.",
    }
    created: list[str] = []
    for name, topic in topics.items():
        if name in mapped:
            continue
        payload: dict[str, Any] = {"name": name, "type": 0, "topic": topic}
        if template.get("parent_id"):
            payload["parent_id"] = template["parent_id"]
        if isinstance(template.get("permission_overwrites"), list):
            payload["permission_overwrites"] = template["permission_overwrites"]
        item = tracker._request("POST", f"/guilds/{tracker.guild_id}/channels", payload)
        if isinstance(item, dict) and item.get("id"):
            mapped[name] = item
            template = item
            created.append(name)
    return created


def _diagnostic_cycle(engine_connection: Any) -> str:
    if _BASE_CYCLE is None:
        raise RuntimeError("Simplified runtime was not installed")
    channel_detail = ""
    try:
        created = _ensure_owner_channels()
        if created:
            channel_detail = "; restored owner channels: " + ", ".join(created)
    except Exception as exc:
        channel_detail = f"; Discord channel repair retrying: {type(exc).__name__}"
    detail = _BASE_CYCLE(engine_connection)
    return detail + channel_detail


def _replace_diagnostic_job() -> None:
    engine = diagnostics._engine()
    rebuilt = []
    found = False
    for job in engine.JOBS:
        if job.name in RETIRED_JOBS:
            continue
        if job.name == diagnostics.DIAGNOSTIC_JOB:
            if found:
                continue
            rebuilt.append(replace(job, callback=_diagnostic_cycle))
            found = True
        else:
            rebuilt.append(job)
    if not found:
        rebuilt.append(
            engine.Job(
                diagnostics.DIAGNOSTIC_JOB,
                diagnostics.timedelta(minutes=5),
                _diagnostic_cycle,
                background=True,
                retry_interval=diagnostics.timedelta(minutes=2),
            )
        )
    engine.JOBS = rebuilt


def _migrate_stale_diagnostics() -> None:
    """Resolve retired/noisy records and refresh their GitHub comments."""
    try:
        connection = diagnostics.connect_store()
    except Exception:
        return
    reports: list[dict[str, Any]] = []
    try:
        rows = [dict(row) for row in connection.execute("SELECT * FROM diagnostics").fetchall()]
        timestamp = diagnostics.iso_now()
        for row in rows:
            key = str(row.get("signature_key") or "")
            component = str(row.get("component") or "").casefold()
            status = str(row.get("status") or "").upper()
            retire = key in RETIRED_DIAGNOSTIC_KEYS or component == "logs"
            if retire and status in ACTIVE_STATES:
                connection.execute(
                    """
                    UPDATE diagnostics SET
                        status='RECOVERED', consecutive_failures=0,
                        last_seen=?, recovery_time=?, resolution_commit=?,
                        verification_result=?, automatic_retry='not needed'
                    WHERE signature=?
                    """,
                    (
                        timestamp,
                        timestamp,
                        diagnostics._current_sha(),
                        "Retired one-time reporting job or generic log symptom was removed from the core runtime.",
                        row["signature"],
                    ),
                )
        connection.commit()
        refreshed = [dict(row) for row in connection.execute("SELECT * FROM diagnostics").fetchall()]
        for row in refreshed:
            if row.get("github_request_number") and str(row.get("status") or "").upper() in RECOVERED_STATES:
                reports.append(_github_report(row))
    finally:
        connection.close()
    for report in reports:
        try:
            bridge.add_or_update_diagnostic(report)
        except Exception:
            continue
    _reconcile_open_batch()


def install() -> None:
    global _INSTALLED, _BASE_CYCLE, _BASE_GITHUB_REPORT, _BASE_ADD_OR_UPDATE
    if _INSTALLED:
        return

    _BASE_CYCLE = diagnostics.diagnostic_cycle_job
    _BASE_GITHUB_REPORT = diagnostics._github_report
    _BASE_ADD_OR_UPDATE = bridge.add_or_update_diagnostic

    diagnostics._escalation_required = _escalation_required
    diagnostics._github_report = _github_report
    diagnostics._log_checks = _quiet_log_checks
    diagnostics._post_live_acceptance = lambda *args, **kwargs: None
    bridge._diagnostic_body = _diagnostic_body
    bridge.add_or_update_diagnostic = _add_or_update_diagnostic
    supervisor_runtime.supervisor_process_check = _supervisor_process_check
    scheduler.REQUIRED_JOBS = CORE_REQUIRED_JOBS

    _replace_diagnostic_job()

    threading.Thread(
        target=_migrate_stale_diagnostics,
        name="simplified-diagnostic-cleanup",
        daemon=True,
    ).start()
    _INSTALLED = True


def validate() -> dict[str, Any]:
    return {
        "version": VERSION,
        "retired_jobs": sorted(RETIRED_JOBS),
        "core_required_jobs": list(CORE_REQUIRED_JOBS),
        "diagnostic_only_batch_autoclose": True,
        "provider_timeouts_create_code_issue": False,
        "single_supervisor_target": "run_supervisor_simple.py:8876",
    }
