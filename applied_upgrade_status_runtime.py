"""Complete the factual status model for #applied-upgrades.

The dashboard distinguishes code attachment from live proof and explicitly shows
rolled-back deployment state and retired behavior. A generated card never proves
itself. FAILED remains the only status that causes the dashboard job to fail.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import applied_upgrades as dashboard
import simple_upgrade_runtime

_INSTALLED = False
_BASE_COLLECT = dashboard.collect_records

STATUS_ORDER = (
    "ACTIVE",
    "INSTALLED",
    "PENDING",
    "FAILED",
    "ROLLED BACK",
    "SUPERSEDED",
)
STATUS_ICONS = {
    "ACTIVE": "✅",
    "INSTALLED": "📦",
    "PENDING": "⏳",
    "FAILED": "❌",
    "ROLLED BACK": "↩️",
    "SUPERSEDED": "🗃️",
}
RUNTIME_ICONS = {
    "PASS": "✅",
    "INSTALLED": "📦",
    "PENDING": "⏳",
    "FAIL": "❌",
    "ROLLED_BACK": "↩️",
    "SUPERSEDED": "🗃️",
}

DEPLOYMENT_SPEC = dashboard.UpgradeSpec(
    "deployment-transaction-state",
    "Latest deployment transaction",
    "Shows whether the newest reviewed commit is installed, deploying, active, failed validation, or rolled back.",
    "run_supervisor_simple.deploy_if_needed + supervisor-state.json",
    ("workflow-log", "upgrade-review", "applied-upgrades"),
    group="Upgrade delivery and verification",
)
SUPERSEDED_SPECS = (
    dashboard.UpgradeSpec(
        "superseded-resilient-readiness-gate",
        "Legacy resilient readiness gate",
        "The former deployment-time Discord and engine readiness gate is retired and cannot block the active updater.",
        "run_supervisor_resilient.py retained as historical source; START-SUPERVISOR.cmd does not launch it",
        (),
        display_channels="No active channels; behavior retired",
        group="Superseded deployment behavior",
    ),
    dashboard.UpgradeSpec(
        "superseded-deployment-discord-sync",
        "Deployment-time Discord synchronization",
        "Full structure sync and slash-command registration no longer run inside the code deployment transaction.",
        "run_supervisor_simple.no_deployment_discord_configuration",
        (),
        display_channels="Runtime features own their channels after startup",
        group="Superseded deployment behavior",
    ),
)


def overall_status(
    implementation_attached: bool,
    channels_present: bool,
    runtime_status: str,
) -> str:
    status = str(runtime_status or "PENDING").upper()
    if not implementation_attached or not channels_present or status == "FAIL":
        return "FAILED"
    if status == "PASS":
        return "ACTIVE"
    if status == "INSTALLED":
        return "INSTALLED"
    if status == "ROLLED_BACK":
        return "ROLLED BACK"
    if status == "SUPERSEDED":
        return "SUPERSEDED"
    return "PENDING"


def _installed_without_attempt(record: dict[str, Any]) -> bool:
    detail = str(record.get("runtime_detail") or "").casefold()
    return any(
        marker in detail
        for marker in (
            "no scheduler receipt yet",
            "first discord acknowledgement is pending",
            "first scheduled run",
            "acceptance receipt has not been written",
            "first runtime receipt",
        )
    )


def _deployment_record(
    channels: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    state = dashboard._read_json(dashboard.SUPERVISOR_STATE_PATH)
    update = str(state.get("last_update_status") or "UNKNOWN").upper()
    local = str(state.get("local_sha") or "")[:12]
    deployed = str(state.get("deployed_sha") or "")[:12]
    attached = dashboard._source_has(
        "run_supervisor_simple.py",
        "def deploy_if_needed",
        "ROLLED_BACK",
        '"merge", "--ff-only", "origin/main"',
    )
    if update == "ROLLED_BACK":
        runtime = "ROLLED_BACK"
    elif update in {"MERGE_FAILED", "VALIDATION_FAILED", "DIRTY", "NON_FAST_FORWARD"}:
        runtime = "FAIL"
    elif update == "DEPLOYED" and local and local == deployed:
        runtime = "PASS"
    elif update in {"DEPLOYING", "DEPLOYMENT_PENDING"}:
        runtime = "PENDING"
    else:
        runtime = "INSTALLED" if attached else "FAIL"
    present, affected, channel_detail = dashboard._channel_proof(
        DEPLOYMENT_SPEC, channels
    )
    return dashboard._record(
        DEPLOYMENT_SPEC,
        implementation_attached=attached,
        channels_present=present,
        affected=affected,
        channel_detail=channel_detail,
        runtime_status=runtime,
        runtime_detail=(
            f"last update={update}; local={local or 'unknown'}; "
            f"deployed={deployed or 'unknown'}; rollback={state.get('rollback_result', 'unknown')}"
        ),
    )


def _superseded_records(
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in SUPERSEDED_SPECS:
        present, affected, channel_detail = dashboard._channel_proof(spec, channels)
        records.append(
            dashboard._record(
                spec,
                implementation_attached=True,
                channels_present=present,
                affected=affected,
                channel_detail=channel_detail,
                runtime_status="SUPERSEDED",
                runtime_detail="Retired from the launched runtime and replaced by run_supervisor_simple.py.",
            )
        )
    return records


def collect_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records = list(_BASE_COLLECT(connection, channels))
    for record in records:
        if record.get("status") == "PENDING" and _installed_without_attempt(record):
            record["status"] = "INSTALLED"
    records.append(_deployment_record(channels))
    records.extend(_superseded_records(channels))
    return records


def render_card(record: dict[str, Any], version: str) -> str:
    status = str(record.get("status") or "FAILED")
    runtime_status = str(record.get("runtime_status") or "PENDING")
    return "\n".join(
        [
            f"## {STATUS_ICONS.get(status, '❓')} {record['title']}",
            f"**Status:** {status}",
            f"**What it does:** {record['description']}",
            f"**Affected channels:** {record['affected'] or 'None'}",
            f"**Implementation:** `{record['implementation']}`",
            (
                "**Attachment proof:** "
                f"{'✅ code hook attached' if record['implementation_attached'] else '❌ code hook missing'} · "
                f"{'✅' if record['channels_present'] else '❌'} {record['channel_detail']}"
            ),
            (
                "**Runtime proof:** "
                f"{RUNTIME_ICONS.get(runtime_status, '❓')} {record['runtime_detail']}"
            ),
            f"**Deployed version checked:** `{version}`",
            (
                "**Proof meaning:** INSTALLED is code attachment without a completed live attempt; "
                "PENDING is live work or retry in progress; ACTIVE requires passing runtime evidence."
            ),
        ]
    )[:1900]


def dashboard_job(connection: Any) -> str:
    simple_upgrade_runtime.ensure_dashboard_channel()
    tracker = dashboard._engine().discord_tracker()
    if not tracker:
        raise RuntimeError(
            "Discord is unavailable, so applied-upgrade proof cannot be posted"
        )
    channels_list = dashboard._guild_channels(tracker)
    channels = dashboard._channel_map(channels_list)
    destination = channels.get(dashboard.CHANNEL_NAME)
    if not destination:
        raise RuntimeError(
            "#applied-upgrades is missing after feature-owned channel bootstrap"
        )

    version = dashboard._current_sha()
    records = collect_records(connection, channels)
    counts = {
        status: sum(1 for item in records if item["status"] == status)
        for status in STATUS_ORDER
    }
    groups: list[str] = []
    group_names = []
    for item in records:
        if item["group"] not in group_names:
            group_names.append(item["group"])
    for group in group_names:
        items = [item for item in records if item["group"] == group]
        summary = " · ".join(
            f"{sum(item['status'] == status for item in items)} {status.lower()}"
            for status in STATUS_ORDER
            if any(item["status"] == status for item in items)
        )
        groups.append(f"**{group}:** {summary or 'no records'}")

    overview = "\n".join(
        [
            "# Applied Upgrades",
            f"**Deployed version:** `{version}`",
            "**" + " · ".join(f"{status} {counts[status]}" for status in STATUS_ORDER) + "**",
            *groups,
            (
                "**Proof rule:** a generated card is not proof. ACTIVE requires an attached implementation, "
                "every required channel, and a passing runtime receipt or durable state."
            ),
            (
                "INSTALLED means code exists but no live attempt has completed. PENDING means live work or retry is in progress. "
                "ROLLED BACK and SUPERSEDED remain visible instead of being disguised as active."
            ),
            f"Last checked **{dashboard._engine().iso_now()}**.",
        ]
    )[:1900]
    channel_id = str(destination["id"])
    dashboard._upsert_if_changed(
        connection,
        tracker,
        channel_id,
        dashboard.OVERVIEW_STATE,
        f"{dashboard.HASH_STATE_PREFIX}overview",
        overview,
        always_update=True,
    )
    for record in records:
        dashboard._upsert_if_changed(
            connection,
            tracker,
            channel_id,
            f"{dashboard.MESSAGE_STATE_PREFIX}{record['key']}",
            f"{dashboard.HASH_STATE_PREFIX}{record['key']}",
            render_card(record, version),
        )

    dashboard._engine().store_observation(
        connection,
        dashboard.JOB_NAME,
        {
            "version": version,
            "counts": counts,
            "records": records,
            "at": dashboard._engine().iso_now(),
        },
    )
    if counts["FAILED"]:
        raise RuntimeError(
            f"applied-upgrades verification found {counts['FAILED']} failed item(s)"
        )
    return "; ".join(
        [
            f"{len(records)} upgrades checked",
            *(f"{counts[status]} {status.lower()}" for status in STATUS_ORDER if counts[status]),
        ]
    )


def install() -> None:
    global _INSTALLED, _BASE_COLLECT
    if _INSTALLED:
        return
    _BASE_COLLECT = dashboard.collect_records
    dashboard._overall_status = overall_status
    dashboard.collect_records = collect_records
    dashboard._render_card = render_card
    dashboard.dashboard_job = dashboard_job
    _INSTALLED = True
