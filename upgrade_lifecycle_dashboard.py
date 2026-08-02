"""Factual owner-facing lifecycle for the shared Tradysquid upgrade batch.

The dashboard updates one stable #upgrade-requests message. It derives state from
GitHub batch data, pull-request CI, supervisor commits, deployment timestamps,
and post-deployment diagnostic receipts. It never changes GitHub approval state
or treats a generated Discord card as verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import diagnostic_upgrade_system as diagnostics
import github_upgrade_bridge as bridge
import upgrade_batch_44

JOB_NAME = "upgrade-lifecycle-dashboard"
MESSAGE_KEY = "shared-upgrade-lifecycle-v1:message-id"
HASH_KEY = "shared-upgrade-lifecycle-v1:content-hash"
_INSTALLED = False


@dataclass(frozen=True)
class Lifecycle:
    state: str
    next_action: str
    reason: str


def _engine() -> Any:
    return upgrade_batch_44._engine()


def _latest_job(connection: Any, name: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT status, started_at, COALESCE(finished_at, '') AS finished_at, detail
        FROM job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _time(value: Any) -> datetime | None:
    return diagnostics._parse_time(value)


def _post_deployment_verified(
    connection: Any,
    supervisor_state: dict[str, Any],
    diagnostic_summary: dict[str, Any],
) -> tuple[bool, str]:
    deployed_at = _time(supervisor_state.get("last_deployment_finished_at"))
    if not deployed_at:
        return False, "no completed deployment timestamp"
    required = (diagnostics.DIAGNOSTIC_JOB, "applied-upgrades-dashboard")
    details: list[str] = []
    for name in required:
        receipt = _latest_job(connection, name)
        finished = _time((receipt or {}).get("finished_at"))
        status = str((receipt or {}).get("status") or "MISSING").upper()
        if status != "OK" or not finished or finished < deployed_at:
            return False, f"{name} has no post-deployment OK receipt"
        details.append(f"{name}=OK@{finished.isoformat(timespec='minutes')}")
    open_diagnostics = diagnostic_summary.get("open") or []
    if open_diagnostics:
        return False, f"{len(open_diagnostics)} diagnostic failure(s) remain open"
    return True, "; ".join(details)


def derive_lifecycle(
    batch: dict[str, Any],
    pulls: list[dict[str, Any]],
    supervisor_state: dict[str, Any],
    *,
    verified: bool,
    verification_reason: str,
) -> Lifecycle:
    batch_state = str(batch.get("state") or "NONE").upper()
    update_status = str(supervisor_state.get("last_update_status") or "").upper()
    local = str(supervisor_state.get("local_sha") or "")[:12]
    deployed = str(supervisor_state.get("deployed_sha") or "")[:12]
    remote = str(supervisor_state.get("last_remote_sha") or "")[:12]

    if update_status == "ROLLED_BACK":
        return Lifecycle(
            "ROLLED BACK",
            "Use the diagnostic-generated request in the shared batch to repair validation before another merge.",
            str(supervisor_state.get("last_update_detail") or "deployment validation failed"),
        )
    if update_status in {"MERGE_FAILED", "VALIDATION_FAILED"}:
        return Lifecycle(
            "FAILED VALIDATION",
            "Repair the failing validation evidence and rerun CI before deployment.",
            str(supervisor_state.get("last_update_detail") or update_status),
        )
    if batch_state == "NONE":
        return Lifecycle(
            "NO OPEN BATCH",
            "Use /upgrade-add or wait for a persistent automatic diagnostic.",
            "No shared GitHub upgrade batch is currently open or ready.",
        )
    if batch_state == "OPEN":
        return Lifecycle(
            "PENDING",
            "Add remaining requests or use /upgrade-ready when the batch is complete.",
            f"Batch #{batch.get('issue_number')} remains open for intake.",
        )

    ci_states = {str(item.get("ci_state") or "UNKNOWN").upper() for item in pulls}
    if ci_states & {"FAILURE", "ERROR"}:
        return Lifecycle(
            "FAILED VALIDATION",
            "Repair the failing pull-request checks before merge.",
            "At least one open pull request has failing CI.",
        )
    if ci_states & {"PENDING", "EXPECTED"}:
        return Lifecycle(
            "UNDER REVIEW",
            "Wait for CI, then complete maintainer review.",
            "An implementation pull request exists and its checks are still running.",
        )
    if pulls and ci_states == {"SUCCESS"}:
        return Lifecycle(
            "CI PASSED",
            "Maintainer reviews and merges the approved implementation into main.",
            "All visible implementation pull requests report successful CI.",
        )
    if update_status == "DEPLOYING" or (remote and deployed and remote != deployed):
        return Lifecycle(
            "DEPLOYMENT PENDING",
            "Leave the simple two-minute updater running until the approved fast-forward commit installs.",
            f"remote={remote or 'unknown'}; deployed={deployed or 'unknown'}",
        )
    if verified and local and deployed and local == deployed:
        return Lifecycle(
            "VERIFIED",
            "No action is required unless a diagnostic returns as FAILED AGAIN.",
            verification_reason,
        )
    if update_status == "DEPLOYED" and local and deployed and local == deployed:
        return Lifecycle(
            "DEPLOYED",
            "Wait for post-deployment diagnostics and applied-upgrade receipts to pass.",
            verification_reason,
        )
    return Lifecycle(
        "UPGRADE READY",
        "Maintainer reviews, implements, tests, and merges the shared batch.",
        "The owner marked the batch ready, but no conclusive implementation or deployment evidence exists yet.",
    )


def render(
    batch: dict[str, Any],
    pulls: list[dict[str, Any]],
    supervisor_state: dict[str, Any],
    lifecycle: Lifecycle,
) -> str:
    lines = [
        "# Shared Upgrade Lifecycle",
        f"**State:** {lifecycle.state}",
        f"**GitHub batch:** #{batch.get('issue_number') or 'none'} · {batch.get('state', 'NONE')} · {batch.get('request_count', 0)} request(s)",
        f"**Commits:** local `{str(supervisor_state.get('local_sha') or 'unknown')[:12]}` · deployed `{str(supervisor_state.get('deployed_sha') or 'unknown')[:12]}` · remote `{str(supervisor_state.get('last_remote_sha') or 'unknown')[:12]}`",
        f"**Evidence:** {lifecycle.reason}",
        f"**Exact next action:** {lifecycle.next_action}",
        "",
        "## Requests",
    ]
    requests = batch.get("requests") or []
    if requests:
        for item in requests[:12]:
            lines.append(
                f"• **{item.get('request_number')} · {item.get('source')}** · {item.get('summary')} · lifecycle **{lifecycle.state}**"
            )
    else:
        lines.append("No requests are currently recorded.")
    if pulls:
        lines.append("## Open implementation pull requests")
        for pull in pulls[:6]:
            lines.append(
                f"• **PR #{pull.get('number')} · CI {pull.get('ci_state')}** · {pull.get('title')} · **Next:** {pull.get('next_action')}"
            )
    lines.extend(
        [
            "",
            "A GitHub issue proves intake only. A merge proves code availability only. VERIFIED requires post-deployment diagnostics and applied-upgrade receipts.",
            f"Updated **{diagnostics.iso_now()}**.",
        ]
    )
    return "\n".join(lines)[:1900]


def lifecycle_job(connection: Any) -> str:
    batch = bridge.batch_status()
    pulls = bridge.pull_request_queue()
    supervisor_state = diagnostics._read_json(diagnostics.SUPERVISOR_STATE_PATH)
    summary = diagnostics.diagnostics_summary()
    verified, reason = _post_deployment_verified(connection, supervisor_state, summary)
    lifecycle = derive_lifecycle(
        batch,
        pulls,
        supervisor_state,
        verified=verified,
        verification_reason=reason,
    )
    tracker, channel_id = diagnostics.ensure_owner_channel(
        diagnostics.REQUEST_CHANNEL,
        "Owner and automatic diagnostic upgrade requests using the shared GitHub batch.",
    )
    if not tracker or not channel_id:
        raise RuntimeError("#upgrade-requests is unavailable")
    diagnostics._upsert_message(
        connection,
        tracker,
        channel_id,
        MESSAGE_KEY,
        HASH_KEY,
        render(batch, pulls, supervisor_state, lifecycle),
    )
    _engine().store_observation(
        connection,
        JOB_NAME,
        {
            "state": lifecycle.state,
            "next_action": lifecycle.next_action,
            "batch": batch,
            "pulls": pulls,
            "verified": verified,
            "verification_reason": reason,
            "at": diagnostics.iso_now(),
        },
    )
    return f"{lifecycle.state}; {batch.get('request_count', 0)} request(s); {len(pulls)} open PR(s)"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    engine = _engine()
    replacement = engine.Job(
        JOB_NAME,
        timedelta(minutes=5),
        lifecycle_job,
        background=True,
        retry_interval=timedelta(minutes=2),
    )
    rebuilt = []
    found = False
    for job in engine.JOBS:
        if job.name == JOB_NAME:
            if not found:
                rebuilt.append(replacement)
                found = True
        else:
            rebuilt.append(job)
    if not found:
        rebuilt.append(replacement)
    engine.JOBS = rebuilt
    connection = engine.connect_db()
    try:
        connection.execute(
            "DELETE FROM engine_state WHERE key IN (?, ?)",
            (f"job:{JOB_NAME}", f"job-error:{JOB_NAME}"),
        )
        connection.commit()
    finally:
        connection.close()
    _INSTALLED = True
