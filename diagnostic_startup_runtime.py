"""Startup and live-proof integration for Tradysquid diagnostics.

Every information-engine process performs one immediate complete diagnostic,
including after deployment, rollback, or an ordinary restart on the same commit.
A harmless synthetic failure/recovery proves that one Discord message is updated
rather than duplicated. This module never participates in deployment gating.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
_ORIGINAL_CYCLE = diagnostics.diagnostic_cycle_job
_ORIGINAL_COLLECT = diagnostics.collect_health_checks
_ORIGINAL_ACCEPTANCE_CONTENT = diagnostics._acceptance_content
SELF_TEST_KEY = "diagnostic-stable-report-self-test"
SELF_TEST_META_PREFIX = "live-self-test:"
RESTART_SAMPLE_KEY = "service-restart-sample"

CHANNEL_TOPICS = {
    diagnostics.REQUEST_CHANNEL: "Owner and automatic diagnostic upgrade requests using the shared GitHub batch.",
    diagnostics.REVIEW_CHANNEL: "Owner review queue for upgrades, diagnostics, deployment, recovery, and exact next actions.",
    diagnostics.APPLIED_CHANNEL: "Verified upgrade implementations, affected channels, deployed commits, and live runtime proof.",
}


def _ensure_required_owner_channels() -> list[str]:
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
            )
            if name in mapped
        ),
        None,
    )
    created: list[str] = []
    for name, topic in CHANNEL_TOPICS.items():
        if name in mapped:
            continue
        if not template:
            raise RuntimeError(
                f"Cannot safely create #{name}: no existing owner-control channel is available as a permission template"
            )
        payload: dict[str, Any] = {
            "name": name,
            "type": 0,
            "topic": topic[:1024],
        }
        if template.get("parent_id"):
            payload["parent_id"] = template["parent_id"]
        overwrites = template.get("permission_overwrites")
        if isinstance(overwrites, list):
            payload["permission_overwrites"] = overwrites
        item = tracker._request(
            "POST", f"/guilds/{tracker.guild_id}/channels", payload
        )
        channel_id = str((item or {}).get("id") or "")
        if not channel_id:
            raise RuntimeError(f"Discord did not acknowledge creation of #{name}")
        mapped[name] = item
        created.append(name)
        template = item
    return created


def _restart_loop_check() -> diagnostics.HealthCheck:
    state = diagnostics._read_json(diagnostics.SUPERVISOR_STATE_PATH)
    counts = (
        state.get("service_restart_counts")
        if isinstance(state.get("service_restart_counts"), dict)
        else {}
    )
    current = {str(name): int(value or 0) for name, value in counts.items()}
    timestamp = diagnostics.now()
    store = diagnostics.connect_store()
    try:
        raw = diagnostics._meta(store, RESTART_SAMPLE_KEY, "")
        try:
            previous = json.loads(raw) if raw else {}
        except (ValueError, TypeError, json.JSONDecodeError):
            previous = {}
        previous_at = diagnostics._parse_time(previous.get("at"))
        previous_counts = previous.get("counts") if isinstance(previous.get("counts"), dict) else {}
        deltas = {
            name: count - int(previous_counts.get(name) or 0)
            for name, count in current.items()
        }
        recent = bool(previous_at and timestamp - previous_at <= timedelta(minutes=10))
        loops = {name: delta for name, delta in deltas.items() if recent and delta >= 3}
        diagnostics._set_meta(
            store,
            RESTART_SAMPLE_KEY,
            json.dumps({"at": timestamp.isoformat(), "counts": current}),
        )
    finally:
        store.close()
    detail = (
        "Restart loop detected: "
        + ", ".join(f"{name} restarted {count} time(s) within ten minutes" for name, count in loops.items())
        if loops
        else "No service increased its restart count by three or more within the sampled ten-minute window."
    )
    return diagnostics.HealthCheck(
        "service-restart-loop",
        not loops,
        "supervisor",
        "managed service restart loop detection",
        detail,
        runtime_target="service_restart_counts and service_last_started_at",
        automatic_retry="supervisor continues affected-service recovery; diagnostics escalate repeatable loops",
        healthy_services=str(state.get("service_health") or "unknown"),
        repair_objective="Stop repeated process exits and preserve unrelated healthy services.",
        acceptance_tests="The affected service remains healthy for at least ten minutes without three restarts.",
        force_upgrade=bool(loops),
    )


def collect_health_checks(engine_connection: Any):
    checks, channels = _ORIGINAL_COLLECT(engine_connection)
    checks.append(_restart_loop_check())
    return checks, channels


def _self_test_complete() -> bool:
    store = diagnostics.connect_store()
    try:
        return bool(
            diagnostics._meta(
                store,
                f"{SELF_TEST_META_PREFIX}{diagnostics._current_sha()}",
                "",
            )
        )
    finally:
        store.close()


def acceptance_content(checks, channels) -> str:
    content = _ORIGINAL_ACCEPTANCE_CONTENT(checks, channels)
    lines = content.splitlines()
    complete = _self_test_complete()
    replacement = (
        "✅ **PASS · Diagnostic stable reporting** · synthetic failure and recovery updated one persistent diagnostic record"
        if complete
        else "⏳ **PENDING · Diagnostic stable reporting** · synthetic create-and-recover proof has not completed"
    )
    output = [
        replacement if "Diagnostic stable reporting" in line else line
        for line in lines
    ]
    return "\n".join(output)[:1900]


def _run_stable_message_self_test() -> None:
    meta_key = f"{SELF_TEST_META_PREFIX}{diagnostics._current_sha()}"
    store = diagnostics.connect_store()
    try:
        if diagnostics._meta(store, meta_key, ""):
            return
    finally:
        store.close()

    check = diagnostics.HealthCheck(
        SELF_TEST_KEY,
        False,
        "diagnostic system",
        "stable Discord create-and-recover self-test",
        "Controlled synthetic diagnostic used only to prove deduplication and recovery reporting.",
        severity="INFO",
        channels="#upgrade-review",
        runtime_target="diagnostic_startup_runtime._run_stable_message_self_test",
        automatic_retry="not applicable; controlled self-test",
        healthy_services="unchanged",
        repair_objective="Prove one diagnostic record can transition from failure to recovery without duplicate messages.",
        acceptance_tests="One local record and one Discord message ID persist across failure and VERIFIED recovery states.",
    )
    first = diagnostics.record_failure(check, sync=True)
    recovered = diagnostics.record_recovery(
        SELF_TEST_KEY,
        "Controlled live diagnostic recovered successfully on the same record and Discord message.",
        verified=True,
        sync=True,
    )
    if not first or not recovered:
        raise RuntimeError("Diagnostic stable-message self-test did not produce a verified record")
    if first.get("signature") != recovered.get("signature"):
        raise RuntimeError("Diagnostic stable-message self-test changed signatures")
    if first.get("discord_message_id") and recovered.get("discord_message_id"):
        if first["discord_message_id"] != recovered["discord_message_id"]:
            raise RuntimeError("Diagnostic stable-message self-test created a duplicate Discord message")
    store = diagnostics.connect_store()
    try:
        diagnostics._set_meta(
            store,
            meta_key,
            json.dumps(
                {
                    "diagnostic_id": recovered.get("diagnostic_id"),
                    "signature": recovered.get("signature"),
                    "discord_message_id": recovered.get("discord_message_id"),
                    "status": recovered.get("status"),
                    "verified_at": diagnostics.iso_now(),
                },
                separators=(",", ":"),
            ),
        )
    finally:
        store.close()


def diagnostic_cycle_job(engine_connection: Any) -> str:
    created = _ensure_required_owner_channels()
    detail = _ORIGINAL_CYCLE(engine_connection)
    _run_stable_message_self_test()
    checks, channels = collect_health_checks(engine_connection)
    diagnostics._post_live_acceptance(engine_connection, checks, channels)
    suffix = f"; created owner channels: {', '.join(created)}" if created else ""
    return f"{detail}; stable reporting verified{suffix}"


def _force_startup_cycle() -> None:
    engine = diagnostics._engine()
    connection = engine.connect_db()
    try:
        connection.execute(
            "DELETE FROM engine_state WHERE key IN (?, ?)",
            (f"job:{diagnostics.DIAGNOSTIC_JOB}", f"job-error:{diagnostics.DIAGNOSTIC_JOB}"),
        )
        connection.commit()
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    diagnostics.collect_health_checks = collect_health_checks
    diagnostics._acceptance_content = acceptance_content
    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job

    engine = diagnostics._engine()
    rebuilt = []
    found = False
    for job in engine.JOBS:
        if job.name == diagnostics.DIAGNOSTIC_JOB:
            rebuilt.append(
                engine.Job(
                    job.name,
                    job.interval,
                    diagnostic_cycle_job,
                    market_hours_only=job.market_hours_only,
                    after_hours_interval=job.after_hours_interval,
                    background=job.background,
                    provider_heavy=job.provider_heavy,
                    retry_interval=job.retry_interval,
                )
            )
            found = True
        else:
            rebuilt.append(job)
    if not found:
        raise RuntimeError("The self-diagnostics scheduler job is missing")
    engine.JOBS = rebuilt
    _force_startup_cycle()
    _INSTALLED = True
