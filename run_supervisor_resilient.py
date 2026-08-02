"""Run Tradysquids with resilient Discord and engine-readiness handling.

Discord slash-command registration is independent from channel/card readiness.
The information engine must remain alive during transient Discord failures, while
services-ready remains blocked until its durable startup acceptance passes.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Iterable

import run_supervisor as base


COMMAND_FAILURE_PREFIX = "command registration failed:"
ENGINE_ACCEPTANCE_PATH = base.ROOT / "state" / "market-intelligence-startup.json"
_LAST_ENGINE_ACCEPTANCE_STATUS = ""


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
            "Discord synchronization is verified; engine acceptance determines final services-ready status.",
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

    base.record_discord_sync_results(results, source="automatic-retry")
    return True


def engine_acceptance() -> tuple[str, str]:
    if not ENGINE_ACCEPTANCE_PATH.exists():
        return "STARTING", "acceptance receipt has not been written yet"
    try:
        payload = json.loads(ENGINE_ACCEPTANCE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return "RETRYING", f"acceptance receipt unreadable: {type(exc).__name__}"
    if not isinstance(payload, dict):
        return "RETRYING", "acceptance receipt is not an object"
    status = str(payload.get("status") or "STARTING").upper()
    detail = str(payload.get("error") or payload.get("contract") or "")
    return status, " ".join(detail.split())[:700]


def deployment_sync_ready(version: str) -> bool:
    """Require structure readiness and durable engine startup acceptance."""
    payload = base.supervisor.state_payload()
    update_status = str(payload.get("last_update_status") or "")
    sync_status = str(payload.get("last_discord_sync_status") or "")
    deployed_sha = str(payload.get("deployed_sha") or "")
    discord_ready = (
        (not update_status and not sync_status)
        or (
            update_status == "DEPLOYED"
            and sync_status == "OK"
            and deployed_sha[:12] == version[:12]
        )
    )
    acceptance_status, acceptance_detail = engine_acceptance()
    base.supervisor.write_state(
        information_engine_acceptance_status=acceptance_status,
        information_engine_acceptance_detail=acceptance_detail,
        information_engine_acceptance_checked_at=time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        ),
    )
    return discord_ready and acceptance_status == "PASSED"


def ensure_services_with_acceptance() -> None:
    """Keep services alive while applying acceptance only to this health cycle."""
    global _LAST_ENGINE_ACCEPTANCE_STATUS
    original_readiness = base.deployment_sync_ready
    base.deployment_sync_ready = deployment_sync_ready
    try:
        base.ensure_services_with_readiness()
    finally:
        base.deployment_sync_ready = original_readiness

    status, detail = engine_acceptance()
    base.supervisor.write_state(
        information_engine_acceptance_status=status,
        information_engine_acceptance_detail=detail,
    )
    engine_online = bool(base.supervisor.LAST_HEALTH.get("information-engine", False))
    if (
        engine_online
        and status != "PASSED"
        and status != _LAST_ENGINE_ACCEPTANCE_STATUS
    ):
        base.supervisor.discord_post(
            "\n".join(
                [
                    "⚠️ **Tradysquids services running; startup verification retrying**",
                    "• information-engine process: **ONLINE**",
                    f"• startup acceptance: **{status}**",
                    f"• detail: {detail or 'required Discord receipts are still pending'}",
                    "The engine remains online and retries automatically; final services-ready waits for PASS.",
                ]
            )[:1900],
            "system-health",
        )
    _LAST_ENGINE_ACCEPTANCE_STATUS = status


def install() -> None:
    base.command_registration_failed = command_registration_failed
    base.discord_results_failed = blocking_discord_results_failed
    base.record_discord_sync_results = record_discord_sync_results
    base.retry_pending_discord_configuration = retry_pending_discord_configuration
    base.supervisor.ensure_services = ensure_services_with_acceptance


install()


if __name__ == "__main__":
    raise SystemExit(base.supervisor.main())
