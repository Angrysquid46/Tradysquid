"""Runtime proof and channel bootstrap for the restored simple upgrade flow.

This module does not participate in deployment. It only keeps the owner-facing
#applied-upgrades dashboard truthful after the resilient deployment wrapper is
retired, and lets that feature create its own Discord channel when missing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import applied_upgrades as dashboard
import network_compat


ROOT = Path(__file__).resolve().parent
_INSTALLED = False
_ORIGINAL_DASHBOARD_JOB = dashboard.dashboard_job

SIMPLE_INFRA_SPECS = (
    dashboard.UpgradeSpec(
        "discord-review-bridge",
        "Discord request review bridge",
        "Stores owner upgrade requests in a GitHub issue batch for maintainer review and implementation.",
        "github_upgrade_bridge.add_request + ready_batch",
        ("upgrade-requests", "upgrade-review"),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "simple-two-minute-updater",
        "Simple two-minute updater",
        "Checks origin/main every two minutes and installs only reviewed commits merged to main.",
        "START-SUPERVISOR.cmd → run_supervisor_simple.py",
        ("workflow-log", "system-health"),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "safe-fast-forward-deployment",
        "Safe fast-forward deployment",
        "Requires main, a clean tracked tree, fast-forward ancestry, compilation, focused tests, and rollback on validation failure.",
        "tradysquid_supervisor.deploy_if_needed + run_supervisor_simple.validate_checkout",
        ("workflow-log", "system-health"),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "runtime-state-preservation",
        "Runtime-state preservation",
        "Keeps generated trade and Discord state outside Git so live data cannot block or be overwritten by upgrades.",
        ".gitignore + supervisor runtime backup/restore",
        ("automation-diagnostics",),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "independent-feature-startup",
        "Independent feature startup",
        "Starts feature jobs after deployment without making Discord synchronization or command registration part of the updater.",
        "run_with_env runtime hooks + information engine jobs",
        ("system-health", "system-activity"),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "network-fallback",
        "Git network fallback",
        "Attempts the normal Git route and then IPv4 while leaving healthy services running when both routes fail.",
        "run_supervisor_simple.fetch_remote_sha + network_compat",
        ("workflow-log",),
        group="Upgrade delivery and verification",
    ),
    dashboard.UpgradeSpec(
        "applied-upgrades-dashboard",
        "Applied Upgrades verification dashboard",
        "Shows each upgrade, affected channels, implementation attachment, deployed version, and live runtime proof.",
        "applied-upgrades-dashboard → applied_upgrades.dashboard_job",
        ("applied-upgrades",),
        group="Upgrade delivery and verification",
    ),
)


def _source_has(path: str, *markers: str) -> bool:
    try:
        text = (ROOT / path).read_text(encoding="utf-8")
    except OSError:
        return False
    return all(marker in text for marker in markers)


def _heartbeat_fresh(state: dict[str, Any]) -> bool:
    heartbeat = dashboard._parse_time(state.get("supervisor_heartbeat_at"))
    return bool(
        heartbeat
        and datetime.now().astimezone() - heartbeat <= timedelta(minutes=5)
    )


def _runtime_record(
    spec: dashboard.UpgradeSpec,
    *,
    attached: bool,
    channels: dict[str, dict[str, Any]],
    status: str,
    detail: str,
) -> dict[str, Any]:
    channels_present, affected, channel_detail = dashboard._channel_proof(
        spec, channels
    )
    return dashboard._record(
        spec,
        implementation_attached=attached,
        channels_present=channels_present,
        affected=affected,
        channel_detail=channel_detail,
        runtime_status=status,
        runtime_detail=detail,
    )


def simple_infra_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    state = dashboard._read_json(dashboard.SUPERVISOR_STATE_PATH)
    mode = str(state.get("supervisor_mode") or "UNKNOWN").upper()
    local_sha = str(state.get("local_sha") or "")[:12]
    deployed_sha = str(state.get("deployed_sha") or "")[:12]
    fetch_status = str(state.get("last_fetch_status") or "UNKNOWN").upper()
    services = state.get("service_health") if isinstance(state.get("service_health"), dict) else {}
    records: list[dict[str, Any]] = []

    for spec in SIMPLE_INFRA_SPECS:
        if spec.key == "discord-review-bridge":
            attached = _source_has(
                "github_upgrade_bridge.py",
                "def add_request",
                "def ready_batch",
                "PENDING BATCH REVIEW",
            ) and _source_has("github_upgrade_patch.py", "upgrade-add")
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if attached else "FAIL",
                    detail="request logging and batch-ready hooks are attached",
                )
            )
        elif spec.key == "simple-two-minute-updater":
            attached = _source_has(
                "run_supervisor_simple.py",
                "SIMPLE_TWO_MINUTE_UPDATER",
                "no_deployment_discord_configuration",
            ) and _source_has(
                "START-SUPERVISOR.cmd", "run_supervisor_simple.py"
            )
            active = mode == "SIMPLE_TWO_MINUTE_UPDATER" and _heartbeat_fresh(state)
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if active else "PENDING",
                    detail=(
                        f"mode={mode}; interval={state.get('update_interval_seconds', 'unknown')}s; "
                        f"heartbeat={'fresh' if _heartbeat_fresh(state) else 'pending/stale'}"
                    ),
                )
            )
        elif spec.key == "safe-fast-forward-deployment":
            attached = _source_has(
                "tradysquid_supervisor.py",
                "merge-base",
                "--ff-only",
                "Validation failed; rolled back",
            ) and _source_has(
                "run_supervisor_simple.py",
                "validate_checkout",
                "focused deployment tests passed",
            )
            proven = bool(
                mode == "SIMPLE_TWO_MINUTE_UPDATER"
                and local_sha
                and local_sha == deployed_sha
            )
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if proven else "PENDING",
                    detail=(
                        f"local={local_sha or 'unknown'}; deployed={deployed_sha or 'unknown'}; "
                        f"last update={state.get('last_update_status', 'UNKNOWN')}"
                    ),
                )
            )
        elif spec.key == "runtime-state-preservation":
            attached = _source_has(
                ".gitignore",
                "state/discord-report-state.json",
                "state/ford-plays-log.csv",
            ) and _source_has(
                "tradysquid_supervisor.py",
                "backup_runtime_changes",
                "restore_runtime_changes",
            )
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if attached else "FAIL",
                    detail="generated runtime files are ignored and deployment backup/restore is attached",
                )
            )
        elif spec.key == "independent-feature-startup":
            attached = _source_has(
                "run_supervisor_simple.py",
                "AUTO_DISCORD_SYNC = False",
                "AUTO_REGISTER_COMMANDS = False",
            ) and _source_has(
                "run_with_env.py",
                "upgrade_batch_44.install_engine",
                "applied_upgrades.install_engine",
            )
            healthy = bool(services.get("command-bot") and services.get("information-engine"))
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if healthy else "PENDING",
                    detail=(
                        f"command-bot={services.get('command-bot', 'unknown')}; "
                        f"information-engine={services.get('information-engine', 'unknown')}"
                    ),
                )
            )
        elif spec.key == "network-fallback":
            attached = _source_has(
                "run_supervisor_simple.py",
                '"normal", ("fetch", "--quiet", "origin", "main")',
                '"ipv4", ("fetch", "--ipv4", "--quiet", "origin", "main")',
            ) and bool(network_compat.status().get("installed"))
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if fetch_status == "OK" else "PENDING",
                    detail=(
                        f"latest fetch={fetch_status}; mode={state.get('last_fetch_mode', 'unknown')}; "
                        f"Python family={network_compat.status().get('address_family')}"
                    ),
                )
            )
        elif spec.key == "applied-upgrades-dashboard":
            jobs = {job.name: job for job in dashboard._engine().JOBS}
            attached = jobs.get(dashboard.JOB_NAME) is not None
            message_id = dashboard._engine().get_state(
                connection, dashboard.OVERVIEW_STATE, ""
            )
            records.append(
                _runtime_record(
                    spec,
                    attached=attached,
                    channels=channels,
                    status="PASS" if message_id else "PENDING",
                    detail=(
                        f"overview message acknowledged as {message_id}"
                        if message_id
                        else "dashboard job is attached; first Discord acknowledgement is pending"
                    ),
                )
            )
    return records


def ensure_dashboard_channel() -> None:
    tracker = dashboard._engine().discord_tracker()
    if not tracker:
        return
    channels = dashboard._guild_channels(tracker)
    mapped = dashboard._channel_map(channels)
    if dashboard.CHANNEL_NAME in mapped:
        return
    sibling = mapped.get("upgrade-requests") or mapped.get("upgrade-review")
    payload: dict[str, Any] = {
        "name": dashboard.CHANNEL_NAME,
        "type": 0,
        "topic": "Verified installed upgrades, affected channels, implementations, and live runtime proof.",
    }
    if sibling:
        if sibling.get("parent_id"):
            payload["parent_id"] = sibling["parent_id"]
        if isinstance(sibling.get("permission_overwrites"), list):
            payload["permission_overwrites"] = sibling["permission_overwrites"]
    tracker._request("POST", f"/guilds/{tracker.guild_id}/channels", payload)


def dashboard_job(connection: Any) -> str:
    ensure_dashboard_channel()
    return _ORIGINAL_DASHBOARD_JOB(connection)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    dashboard.INFRA_SPECS = SIMPLE_INFRA_SPECS
    dashboard.ALL_SPECS = (*dashboard.BATCH_SPECS, *SIMPLE_INFRA_SPECS)
    dashboard._infra_records = simple_infra_records
    dashboard.dashboard_job = dashboard_job
    _INSTALLED = True
