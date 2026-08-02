"""Discord-visible proof of which Tradysquid upgrades are actually attached.

The dedicated #applied-upgrades channel is intentionally not a release-notes
wall. Every card distinguishes code attachment, channel presence, and live
runtime proof. A generated card alone can never produce ACTIVE status.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import learning_center_catalog
import network_compat
import upgrade_batch_44
import upgrade_batch_44_live_acceptance as live


ROOT = Path(__file__).resolve().parent
SUPERVISOR_STATE_PATH = ROOT / "state" / "supervisor-state.json"
ENGINE_ACCEPTANCE_PATH = ROOT / "state" / "market-intelligence-startup.json"
CHANNEL_NAME = "applied-upgrades"
JOB_NAME = "applied-upgrades-dashboard"
VERSION = "applied-upgrades-v1"
OVERVIEW_STATE = f"{VERSION}:overview-message-id"
MESSAGE_STATE_PREFIX = f"{VERSION}:card-message-id:"
HASH_STATE_PREFIX = f"{VERSION}:card-content-hash:"

_INSTALLED = False
_STRUCTURE_INSTALLED = False


@dataclass(frozen=True)
class UpgradeSpec:
    key: str
    title: str
    description: str
    implementation: str
    channels: tuple[str, ...]
    acceptance_number: int | None = None
    display_channels: str = ""
    group: str = "Discord feature upgrades"


BATCH_SPECS = (
    UpgradeSpec(
        "active-universe-news",
        "Active-universe news",
        "Replaces single-ticker news with timestamped news for the active scanner universe.",
        "managed-ticker-news → upgrade_batch_44.active_news_job",
        ("news-and-events", "breaking-alerts"),
        1,
    ),
    UpgradeSpec(
        "dynamic-premarket",
        "Dynamic premarket cards",
        "Publishes useful session cards for each active ticker instead of one fixed-symbol card.",
        "premarket-visibility → upgrade_batch_44.active_premarket_job",
        ("premarket",),
        2,
    ),
    UpgradeSpec(
        "future-upgrade-relocation",
        "Future upgrade-request relocation",
        "Mirrors upgrade confirmations into the owner channel and removes the source confirmation.",
        "github_upgrade_patch mirror + source cleanup hooks",
        ("upgrade-requests",),
        3,
    ),
    UpgradeSpec(
        "deduplicated-alerts",
        "Deduplicated breaking alerts",
        "Uses stable headline hashes so the same event is updated instead of repeatedly reposted.",
        "managed-ticker-news + stable headline digest",
        ("breaking-alerts", "news-and-events"),
        4,
    ),
    UpgradeSpec(
        "intraday-charts",
        "Intraday charts and levels",
        "Builds smaller-timeframe charts, support, resistance, and timestamped active-ticker context.",
        "intraday-chart-refresh → upgrade_batch_44.intraday_chart_job",
        ("charts-and-levels",),
        5,
    ),
    UpgradeSpec(
        "market-regime",
        "Active-universe market regime",
        "Maintains one market-regime summary covering active symbols plus SPY and QQQ context.",
        "active-market-regime → upgrade_batch_44.market_regime_summary_job",
        ("market-regime",),
        6,
    ),
    UpgradeSpec(
        "universe-rotation",
        "Dynamic universe rotation",
        "Scores liquid optionable candidates while protecting member additions and open positions.",
        "dynamic-universe-rotation → upgrade_batch_44.universe_rotation_job",
        ("universe-watch",),
        7,
    ),
    UpgradeSpec(
        "system-activity-receipts",
        "System Activity from real receipts",
        "Builds activity status from scheduler receipts and visible-work freshness rather than promises.",
        "system-activity → enhanced always_on_operations activity card",
        ("system-activity",),
        8,
    ),
    UpgradeSpec(
        "learning-results-dashboard",
        "Learning Results evidence dashboard",
        "Shows reviewed samples, evidence limits, and suggested reviews without changing filters automatically.",
        "outcome-learning → enhanced learning results renderer",
        ("learning-results",),
        9,
    ),
    UpgradeSpec(
        "aggregate-play-channels",
        "Aggregate-only play-type channels",
        "Keeps individual completed trades in Trade Journal while play channels remain clean summaries.",
        "play-style evidence renderer + Trade Journal contract",
        (
            "regular-calls",
            "regular-puts",
            "swing-calls",
            "swing-puts",
            "bull-put-spreads",
            "bear-call-spreads",
            "trade-journal",
        ),
        10,
        "six play-type channels + #trade-journal",
    ),
    UpgradeSpec(
        "play-evidence-improvements",
        "Play-type evidence and improvements",
        "Adds expectancy, MFE, MAE, sample limits, and improvement tradeoffs to play dashboards.",
        "enhanced play-style evidence renderer",
        (
            "regular-calls",
            "regular-puts",
            "swing-calls",
            "swing-puts",
            "bull-put-spreads",
            "bear-call-spreads",
            "learning-results",
        ),
        11,
        "six play-type channels + #learning-results",
    ),
    UpgradeSpec(
        "expanded-learning-center",
        "Expanded Learning Center and journals",
        "Adds applied frameworks, evidence checklists, failure modes, drills, and journal-linked decision fields.",
        "27 lesson supplements + journal contract v16",
        tuple(learning_center_catalog.ORDERED_CHANNELS) + ("trade-journal",),
        12,
        "Learning Center 01–27 + #trade-journal",
    ),
    UpgradeSpec(
        "historical-upgrade-migration",
        "Historical upgrade-request migration",
        "Scans complete accessible channel history, copies confirmations, verifies the copy, then deletes the source.",
        "upgrade-request-migration → reliable paginated copy-then-delete job",
        ("upgrade-requests",),
        13,
    ),
)


INFRA_SPECS = (
    UpgradeSpec(
        "live-batch-acceptance",
        "Live batch acceptance",
        "Checks the original 13 changes against runtime receipts and visible Discord state instead of source files alone.",
        "upgrade-batch-44-acceptance + reliable migration jobs",
        ("upgrade-requests",),
        group="Reliability and deployment upgrades",
    ),
    UpgradeSpec(
        "command-retry-separation",
        "Nonblocking slash-command retries",
        "Keeps services running when command registration times out and retries only the failed command step.",
        "run_supervisor_resilient command/structure failure separation",
        ("workflow-log", "system-health"),
        group="Reliability and deployment upgrades",
    ),
    UpgradeSpec(
        "supervisor-hardening",
        "Supervisor, updater, and diagnostics hardening",
        "Verifies process ownership, watchdog recovery, updater state, expected ports, and diagnostic log tails.",
        "resilient supervisor + watchdog + SUPERVISOR-DIAGNOSTICS.ps1",
        ("workflow-log", "system-health", "automation-diagnostics"),
        group="Reliability and deployment upgrades",
    ),
    UpgradeSpec(
        "engine-startup-retry",
        "Information-engine startup retry",
        "Keeps the engine health port online while required Discord receipts retry in the background.",
        "local_information_engine_bootstrap background acceptance worker",
        ("system-health", "system-activity"),
        group="Reliability and deployment upgrades",
    ),
    UpgradeSpec(
        "ipv4-network-compat",
        "IPv4 GitHub and Discord compatibility",
        "Forces Tradysquid Git and Python requests onto IPv4 and retries failed fetches without restarting healthy services.",
        "network_compat + git fetch --ipv4",
        ("workflow-log", "system-health"),
        group="Reliability and deployment upgrades",
    ),
    UpgradeSpec(
        "applied-upgrades-dashboard",
        "Applied Upgrades verification dashboard",
        "Shows what each upgrade does, affected channels, attached implementation, deployed version, and live proof.",
        "applied-upgrades-dashboard → applied_upgrades.dashboard_job",
        ("applied-upgrades",),
        group="Reliability and deployment upgrades",
    ),
)

ALL_SPECS = (*BATCH_SPECS, *INFRA_SPECS)


def _engine() -> Any:
    return upgrade_batch_44._engine()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def _current_sha() -> str:
    state = _read_json(SUPERVISOR_STATE_PATH)
    deployed = str(state.get("deployed_sha") or state.get("local_sha") or "").strip()
    if deployed:
        return deployed[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _guild_channels(tracker: Any) -> list[dict[str, Any]]:
    payload = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    return [item for item in payload if isinstance(payload, list) and isinstance(item, dict)]


def _channel_map(channels: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name") or "").casefold(): item
        for item in channels
        if item.get("name") and item.get("id")
    }


def _channel_proof(
    spec: UpgradeSpec,
    channels: dict[str, dict[str, Any]],
) -> tuple[bool, str, str]:
    missing = [name for name in spec.channels if name.casefold() not in channels]
    present = len(spec.channels) - len(missing)
    if spec.display_channels:
        affected = spec.display_channels
    else:
        references = []
        for name in spec.channels:
            item = channels.get(name.casefold())
            references.append(f"<#{item['id']}>" if item else f"`#{name} missing`")
        affected = " · ".join(references)
    detail = f"{present}/{len(spec.channels)} required channels present"
    if missing:
        detail += "; missing " + ", ".join(f"#{name}" for name in missing[:8])
    return not missing, affected, detail


def _source_has(path: str, *markers: str) -> bool:
    try:
        text = (ROOT / path).read_text(encoding="utf-8")
    except OSError:
        return False
    return all(marker in text for marker in markers)


def _job_status(connection: Any, name: str) -> tuple[str, str]:
    row = live._latest_job(connection, name)
    if not row:
        return "PENDING", "no scheduler receipt yet"
    status = str(row.get("status") or "").upper()
    detail = " ".join(str(row.get("detail") or "").split())[:220]
    if status == "OK":
        return "PASS", detail or "scheduler job completed"
    if status == "RUNNING":
        return "PENDING", "scheduler job is currently running"
    if status in {"ERROR", "INTERRUPTED"}:
        return "FAIL", detail or status.lower()
    return "PENDING", detail or status.lower() or "unknown receipt state"


def _combine_runtime(*values: tuple[str, str]) -> tuple[str, str]:
    statuses = [status for status, _ in values]
    detail = " | ".join(text for _, text in values if text)[:500]
    if "FAIL" in statuses:
        return "FAIL", detail
    if statuses and all(status == "PASS" for status in statuses):
        return "PASS", detail
    return "PENDING", detail or "runtime verification is pending"


def _overall_status(
    implementation_attached: bool,
    channels_present: bool,
    runtime_status: str,
) -> str:
    if not implementation_attached or not channels_present or runtime_status == "FAIL":
        return "FAILED"
    if runtime_status == "PASS":
        return "ACTIVE"
    return "PENDING"


def _record(
    spec: UpgradeSpec,
    *,
    implementation_attached: bool,
    channels_present: bool,
    affected: str,
    channel_detail: str,
    runtime_status: str,
    runtime_detail: str,
) -> dict[str, Any]:
    return {
        "key": spec.key,
        "group": spec.group,
        "title": spec.title,
        "description": spec.description,
        "implementation": spec.implementation,
        "implementation_attached": implementation_attached,
        "channels_present": channels_present,
        "affected": affected,
        "channel_detail": channel_detail,
        "runtime_status": runtime_status,
        "runtime_detail": runtime_detail,
        "status": _overall_status(
            implementation_attached,
            channels_present,
            runtime_status,
        ),
    }


def _batch_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    static = {int(item["number"]): item for item in live.static_audit()}
    records = []
    for spec in BATCH_SPECS:
        item = static.get(int(spec.acceptance_number or 0), {})
        attached = item.get("status") == "PASS"
        runtime_status, runtime_detail = live._live_check(
            connection,
            int(spec.acceptance_number or 0),
            item,
        )
        channels_present, affected, channel_detail = _channel_proof(spec, channels)
        records.append(
            _record(
                spec,
                implementation_attached=attached,
                channels_present=channels_present,
                affected=affected,
                channel_detail=channel_detail,
                runtime_status=runtime_status,
                runtime_detail=runtime_detail,
            )
        )
    return records


def _infra_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    jobs = {job.name: job for job in _engine().JOBS}
    supervisor_state = _read_json(SUPERVISOR_STATE_PATH)
    acceptance = _read_json(ENGINE_ACCEPTANCE_PATH)
    now = datetime.now().astimezone()
    results: list[dict[str, Any]] = []

    for spec in INFRA_SPECS:
        channels_present, affected, channel_detail = _channel_proof(spec, channels)
        attached = False
        runtime_status = "PENDING"
        runtime_detail = "runtime verification is pending"

        if spec.key == "live-batch-acceptance":
            attached = (
                jobs.get("upgrade-batch-44-acceptance") is not None
                and jobs["upgrade-batch-44-acceptance"].callback is live.live_acceptance_job
                and jobs.get("upgrade-request-migration") is not None
                and jobs["upgrade-request-migration"].callback
                is live.reliable_upgrade_migration_job
            )
            runtime_status, runtime_detail = _combine_runtime(
                _job_status(connection, "upgrade-batch-44-acceptance"),
                _job_status(connection, "upgrade-request-migration"),
            )
        elif spec.key == "command-retry-separation":
            attached = _source_has(
                "run_supervisor_resilient.py",
                "RETRY_PENDING",
                "run_command_registration_only",
                "blocking_discord_results_failed",
            )
            command_status = str(
                supervisor_state.get("last_command_registration_status") or "UNKNOWN"
            ).upper()
            if command_status == "OK":
                runtime_status = "PASS"
            elif command_status == "RETRY_PENDING":
                runtime_status = "PENDING"
            else:
                runtime_status = "PENDING"
            runtime_detail = f"supervisor command-registration state: {command_status}"
        elif spec.key == "supervisor-hardening":
            attached = (
                _source_has("SUPERVISOR-DIAGNOSTICS.ps1", "last_fetch_status", "Get-NetTCPConnection")
                and _source_has("ENSURE-SUPERVISOR.ps1", "run_supervisor_resilient.py")
                and _source_has("stop_tradysquid_processes.ps1", "run_supervisor_resilient")
            )
            heartbeat = _parse_time(supervisor_state.get("supervisor_heartbeat_at"))
            heartbeat_fresh = bool(heartbeat and now - heartbeat <= timedelta(minutes=5))
            local_sha = str(supervisor_state.get("local_sha") or "")[:12]
            deployed_sha = str(supervisor_state.get("deployed_sha") or "")[:12]
            if heartbeat_fresh and local_sha and local_sha == deployed_sha:
                runtime_status = "PASS"
            elif str(supervisor_state.get("supervisor") or "").upper() == "ONLINE":
                runtime_status = "PENDING"
            else:
                runtime_status = "FAIL"
            runtime_detail = (
                f"supervisor={supervisor_state.get('supervisor', 'UNKNOWN')}; "
                f"heartbeat={'fresh' if heartbeat_fresh else 'stale/missing'}; "
                f"local={local_sha or 'unknown'}; deployed={deployed_sha or 'unknown'}; "
                f"fetch={supervisor_state.get('last_fetch_status', 'UNKNOWN')}"
            )
        elif spec.key == "engine-startup-retry":
            attached = (
                _source_has(
                    "local_information_engine_bootstrap.py",
                    "startup_acceptance_worker",
                    "start_acceptance_retry_worker",
                    "RETRYING",
                )
                and _source_has(
                    "run_supervisor_resilient.py",
                    "engine_acceptance",
                    "services running; startup verification retrying",
                )
            )
            state = str(acceptance.get("status") or "STARTING").upper()
            runtime_status = "PASS" if state == "PASSED" else "FAIL" if state == "FAILED" else "PENDING"
            runtime_detail = (
                f"startup acceptance={state}; "
                + " ".join(str(acceptance.get("error") or acceptance.get("contract") or "").split())[:360]
            )
        elif spec.key == "ipv4-network-compat":
            attached = bool(network_compat.status().get("installed")) and _source_has(
                "run_supervisor_resilient.py",
                "ipv4_fetch_remote_sha",
                '"--ipv4"',
            )
            fetch_status = str(supervisor_state.get("last_fetch_status") or "UNKNOWN").upper()
            runtime_status = "PASS" if fetch_status == "OK" else "PENDING"
            runtime_detail = (
                f"Python address family={network_compat.status().get('address_family')}; "
                f"latest supervisor Git fetch={fetch_status}"
            )
        elif spec.key == "applied-upgrades-dashboard":
            attached = (
                jobs.get(JOB_NAME) is not None
                and jobs[JOB_NAME].callback is dashboard_job
            )
            message_id = _engine().get_state(connection, OVERVIEW_STATE, "")
            runtime_status = "PASS" if message_id else "PENDING"
            runtime_detail = (
                f"overview message acknowledged as {message_id}"
                if message_id
                else "dashboard job is attached; first Discord acknowledgement is pending"
            )

        results.append(
            _record(
                spec,
                implementation_attached=attached,
                channels_present=channels_present,
                affected=affected,
                channel_detail=channel_detail,
                runtime_status=runtime_status,
                runtime_detail=runtime_detail,
            )
        )
    return results


def collect_records(
    connection: Any,
    channels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [*_batch_records(connection, channels), *_infra_records(connection, channels)]


def _render_card(record: dict[str, Any], version: str) -> str:
    icons = {"ACTIVE": "✅", "PENDING": "⏳", "FAILED": "❌"}
    runtime_icons = {"PASS": "✅", "PENDING": "⏳", "FAIL": "❌"}
    return "\n".join(
        [
            f"## {icons[record['status']]} {record['title']}",
            f"**Status:** {record['status']}",
            f"**What it does:** {record['description']}",
            f"**Affected channels:** {record['affected']}",
            f"**Implementation:** `{record['implementation']}`",
            (
                "**Attachment proof:** "
                f"{'✅ code hook attached' if record['implementation_attached'] else '❌ code hook missing'} · "
                f"{'✅' if record['channels_present'] else '❌'} {record['channel_detail']}"
            ),
            (
                "**Runtime proof:** "
                f"{runtime_icons[record['runtime_status']]} {record['runtime_detail']}"
            ),
            f"**Deployed version checked:** `{version}`",
        ]
    )[:1900]


def _upsert_if_changed(
    connection: Any,
    tracker: Any,
    channel_id: str,
    state_key: str,
    hash_key: str,
    content: str,
    *,
    always_update: bool = False,
) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    message_id = _engine().get_state(connection, state_key, "")
    previous = _engine().get_state(connection, hash_key, "")
    if message_id and previous == digest and not always_update:
        return message_id
    message_id = live._upsert_plain_receipt(
        connection,
        tracker,
        channel_id,
        state_key,
        content,
    )
    _engine().set_state(connection, hash_key, digest)
    return message_id


def dashboard_job(connection: Any) -> str:
    tracker = _engine().discord_tracker()
    if not tracker:
        raise RuntimeError("Discord is unavailable, so applied-upgrade proof cannot be posted")
    channels_list = _guild_channels(tracker)
    channels = _channel_map(channels_list)
    destination = channels.get(CHANNEL_NAME)
    if not destination:
        raise RuntimeError("#applied-upgrades is missing; Discord structure sync has not applied it")

    version = _current_sha()
    records = collect_records(connection, channels)
    counts = {
        status: sum(1 for item in records if item["status"] == status)
        for status in ("ACTIVE", "PENDING", "FAILED")
    }
    groups = []
    for group in ("Discord feature upgrades", "Reliability and deployment upgrades"):
        group_records = [item for item in records if item["group"] == group]
        groups.append(
            f"**{group}:** "
            f"{sum(item['status'] == 'ACTIVE' for item in group_records)} active · "
            f"{sum(item['status'] == 'PENDING' for item in group_records)} pending · "
            f"{sum(item['status'] == 'FAILED' for item in group_records)} failed"
        )
    overview = "\n".join(
        [
            "# Applied Upgrades",
            f"**Deployed version:** `{version}`",
            (
                f"**ACTIVE {counts['ACTIVE']} · PENDING {counts['PENDING']} · "
                f"FAILED {counts['FAILED']}**"
            ),
            *groups,
            "**Proof rule:** a generated card is not proof. ACTIVE requires an attached implementation, every required channel, and a passing runtime receipt or durable state.",
            "PENDING means the code and channels are attached but live verification has not completed. FAILED means code, channels, or runtime proof is missing or broken.",
            f"Last checked **{_engine().iso_now()}**.",
        ]
    )[:1900]
    channel_id = str(destination["id"])
    _upsert_if_changed(
        connection,
        tracker,
        channel_id,
        OVERVIEW_STATE,
        f"{HASH_STATE_PREFIX}overview",
        overview,
        always_update=True,
    )

    for index, record in enumerate(records, start=1):
        content = _render_card(record, version)
        _upsert_if_changed(
            connection,
            tracker,
            channel_id,
            f"{MESSAGE_STATE_PREFIX}{record['key']}",
            f"{HASH_STATE_PREFIX}{record['key']}",
            content,
        )

    _engine().store_observation(
        connection,
        JOB_NAME,
        {
            "version": version,
            "counts": counts,
            "records": records,
            "at": _engine().iso_now(),
        },
    )
    if counts["FAILED"]:
        raise RuntimeError(
            f"applied-upgrades verification found {counts['FAILED']} failed item(s)"
        )
    return (
        f"{len(records)} upgrades checked; {counts['ACTIVE']} active; "
        f"{counts['PENDING']} pending; 0 failed"
    )


def install_engine() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    engine = _engine()
    rebuilt = []
    found = False
    for job in engine.JOBS:
        if job.name == JOB_NAME:
            rebuilt.append(
                engine.Job(
                    JOB_NAME,
                    timedelta(minutes=5),
                    dashboard_job,
                    background=True,
                    retry_interval=timedelta(minutes=2),
                )
            )
            found = True
        else:
            rebuilt.append(job)
    if not found:
        rebuilt.append(
            engine.Job(
                JOB_NAME,
                timedelta(minutes=5),
                dashboard_job,
                background=True,
                retry_interval=timedelta(minutes=2),
            )
        )
    engine.JOBS = rebuilt
    _INSTALLED = True


def install_structure(sync: Any) -> None:
    global _STRUCTURE_INSTALLED
    if _STRUCTURE_INSTALLED:
        return
    if not any(item.name == CHANNEL_NAME for item in sync.CHANNELS):
        rebuilt = []
        inserted = False
        for item in sync.CHANNELS:
            if item.name in {"upgrade-requests", "upgrade-review"} and not inserted:
                rebuilt.append(
                    sync.ChannelSpec(
                        "OWNER CONTROL",
                        CHANNEL_NAME,
                        "Verified installed upgrades, affected channels, implementations, and live runtime proof.",
                    )
                )
                inserted = True
            rebuilt.append(item)
        if not inserted:
            rebuilt.append(
                sync.ChannelSpec(
                    "OWNER CONTROL",
                    CHANNEL_NAME,
                    "Verified installed upgrades, affected channels, implementations, and live runtime proof.",
                )
            )
        sync.CHANNELS = rebuilt
    sync.CHANNEL_STARTERS[CHANNEL_NAME] = (
        "Updated by live runtime checks. A generated card alone never counts as ACTIVE."
    )
    sync.GUIDES[CHANNEL_NAME] = """# Applied Upgrades
This owner-only channel answers five questions for every deployed upgrade:

1. What does the upgrade do?
2. Which Discord channels are affected?
3. Which concrete job, hook, or runtime module implements it?
4. Is that implementation attached to the running process?
5. Is there a passing live receipt, or is verification still pending/failed?

**ACTIVE** requires code attachment, all required channels, and live proof.
**PENDING** means the implementation and channels exist but runtime proof has not
completed. **FAILED** means something required is missing or a live check failed.
A card existing in this channel is never treated as proof by itself."""
    _STRUCTURE_INSTALLED = True


def validate() -> dict[str, Any]:
    keys = [item.key for item in ALL_SPECS]
    if len(keys) != len(set(keys)):
        raise RuntimeError("Applied-upgrade catalog contains duplicate keys")
    original_numbers = [item.acceptance_number for item in BATCH_SPECS]
    if original_numbers != list(range(1, 14)):
        raise RuntimeError("Original batch catalog must preserve requests 1 through 13")
    if CHANNEL_NAME not in INFRA_SPECS[-1].channels:
        raise RuntimeError("Applied-upgrades dashboard does not verify its own channel")
    return {
        "version": VERSION,
        "original_batch_upgrades": len(BATCH_SPECS),
        "reliability_upgrades": len(INFRA_SPECS),
        "total_cards": len(ALL_SPECS),
        "generated_card_is_not_proof": True,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
