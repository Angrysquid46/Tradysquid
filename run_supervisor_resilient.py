"""Run Tradysquids with non-blocking Discord command-registration retries.

Discord slash-command registration is independent from the information engine
and channel/card synchronization. A transient timeout while registering commands
must remain visible and retry automatically, but it must not mark an otherwise
healthy deployment unusable or suppress services-ready/system-health updates.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable

import run_supervisor as base


COMMAND_FAILURE_PREFIX = "command registration failed:"


def command_registration_failed(results: Iterable[object] | None) -> bool:
    return any(
        str(item).casefold().strip().startswith(COMMAND_FAILURE_PREFIX)
        for item in results or []
    )


def blocking_discord_results_failed(results: Iterable[object] | None) -> bool:
    """Return True only for failures that prevent Discord structure readiness."""
    failure_words = (" failed", "error", "blocked", "timed out", "timeout")
    for result in results or []:
        lowered = f" {str(result).casefold()}"
        if lowered.strip().startswith(COMMAND_FAILURE_PREFIX):
            continue
        if any(word in lowered for word in failure_words):
            return True
    return False


def run_command_registration_only() -> str:
    result = base.supervisor.run(
        [
            sys.executable,
            str(base.ROOT / "run_with_env.py"),
            str(base.ROOT / "register_discord_commands.py"),
        ],
        timeout=120,
    )
    if result.returncode:
        return (
            COMMAND_FAILURE_PREFIX
            + " "
            + (result.stderr or result.stdout or "command failed")[-700:]
        )
    return "Discord slash commands synchronized"


def structure_results(results: Iterable[object] | None) -> list[str]:
    """Preserve the latest structure result during a command-only retry."""
    values: list[str] = []
    for item in results or []:
        text = str(item)
        lowered = text.casefold().strip()
        if lowered.startswith(COMMAND_FAILURE_PREFIX):
            continue
        if lowered == "discord slash commands synchronized":
            continue
        values.append(text)
    return values


def record_discord_sync_results(results: list[str], *, source: str) -> bool:
    payload = base.supervisor.state_payload()
    previous_status = str(payload.get("last_discord_sync_status") or "UNKNOWN")
    previous_command_status = str(
        payload.get("last_command_registration_status") or "UNKNOWN"
    )
    previous_signature = str(payload.get("last_discord_sync_signature") or "")

    blocking_failed = blocking_discord_results_failed(results)
    command_failed = command_registration_failed(results)
    sync_status = "FAILED" if blocking_failed else "OK"
    command_status = "RETRY_PENDING" if command_failed else "OK"
    signature = " | ".join(results)[-3500:]
    update_status = str(payload.get("last_update_status") or "")

    if blocking_failed and update_status == "DEPLOYED":
        update_status = "DEPLOYED_WITH_DISCORD_ERRORS"
    elif not blocking_failed and update_status == "DEPLOYED_WITH_DISCORD_ERRORS":
        update_status = "DEPLOYED"

    version = base.supervisor.current_sha()
    base.supervisor.write_state(
        last_discord_sync_status=sync_status,
        last_command_registration_status=command_status,
        last_discord_sync_signature=signature,
        last_discord_sync_source=source,
        last_discord_sync_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        last_update_status=update_status,
        deployed_sha=version,
        discord_results=results,
    )

    if blocking_failed:
        message = "\n".join(
            [
                "❌ **Tradysquids deployment incomplete**",
                f"Version `{version}` is running, but Discord structure synchronization failed.",
                *[f"• {item}" for item in results],
                "The supervisor will retry automatically; services-ready remains blocked until the structure succeeds.",
            ]
        )[:1900]
        if signature != previous_signature:
            base.supervisor.discord_post(message, "workflow-log")
        base.supervisor.discord_post(message, "system-health")
        return False

    if command_failed:
        message = "\n".join(
            [
                "⚠️ **Tradysquids deployment active; command retry pending**",
                f"Version `{version}` is running.",
                *[f"• {item}" for item in results],
                "Discord structure is synchronized, so local services and System Health are not blocked.",
                "Slash-command registration will retry separately without rerunning the Learning Center sync.",
            ]
        )[:1900]
        if (
            source == "deployment"
            or previous_command_status != "RETRY_PENDING"
            or signature != previous_signature
        ):
            base.supervisor.discord_post(message, "workflow-log")
            base.supervisor.discord_post(message, "system-health")
        return True

    completion = "\n".join(
        [
            "✅ **Tradysquids deployment completed**",
            f"Version `{version}`",
            *[f"• {item}" for item in results],
            "Discord synchronization is verified and services-ready is allowed.",
        ]
    )[:1900]
    if (
        source == "deployment"
        or previous_status == "FAILED"
        or previous_command_status == "RETRY_PENDING"
    ):
        base.supervisor.discord_post(completion, "workflow-log")
        base.supervisor.discord_post(completion, "system-health")
    return True


def retry_pending_discord_configuration() -> bool:
    payload = base.supervisor.state_payload()
    previous_results = [str(item) for item in payload.get("discord_results") or []]
    blocking_pending = (
        str(payload.get("last_discord_sync_status") or "") == "FAILED"
        or blocking_discord_results_failed(previous_results)
    )
    command_pending = (
        str(payload.get("last_command_registration_status") or "")
        == "RETRY_PENDING"
        or command_registration_failed(previous_results)
    )
    if not blocking_pending and not command_pending:
        return False

    if blocking_pending:
        base.supervisor.supervisor_log(
            "Retrying failed Discord structure configuration"
        )
        results = base.public_run_discord_configuration()
    else:
        base.supervisor.supervisor_log(
            "Retrying Discord slash-command registration without rerunning structure sync"
        )
        results = [run_command_registration_only(), *structure_results(previous_results)]

    record_discord_sync_results(results, source="automatic-retry")
    return True


def deployment_sync_ready(version: str) -> bool:
    """Structure readiness is independent from slash-command registration."""
    payload = base.supervisor.state_payload()
    update_status = str(payload.get("last_update_status") or "")
    sync_status = str(payload.get("last_discord_sync_status") or "")
    deployed_sha = str(payload.get("deployed_sha") or "")
    if not update_status and not sync_status:
        return True
    return (
        update_status == "DEPLOYED"
        and sync_status == "OK"
        and deployed_sha[:12] == version[:12]
    )


def install() -> None:
    base.command_registration_failed = command_registration_failed
    base.discord_results_failed = blocking_discord_results_failed
    base.record_discord_sync_results = record_discord_sync_results
    base.retry_pending_discord_configuration = retry_pending_discord_configuration
    base.deployment_sync_ready = deployment_sync_ready


install()


if __name__ == "__main__":
    raise SystemExit(base.supervisor.main())
