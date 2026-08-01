"""Launch the supervisor with resilient update and public-service overrides."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import always_on_operations
import ford_scan
import strict_learning_order
import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent
ORIGINAL_DEPLOY_IF_NEEDED = supervisor.deploy_if_needed
ORIGINAL_ENSURE_SERVICES = supervisor.ensure_services
ORIGINAL_FETCH_REMOTE_SHA = supervisor.fetch_remote_sha
_LAST_READY_SIGNATURE: tuple[tuple[str, bool], ...] | None = None
_ENGINE_START_GRACE_UNTIL = 0.0


def safe_take_process_ownership() -> None:
    if os.name != "nt":
        return
    helper = ROOT / "stop_tradysquid_processes.ps1"
    if not helper.exists():
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-KeepProcessId",
            str(os.getpid()),
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    time.sleep(2)


def public_command_bot_command() -> list[str]:
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "discord_command_bot_public.py"),
    ]


def public_information_engine_command() -> list[str]:
    """Return the always-on engine command and start its heartbeat grace window."""
    global _ENGINE_START_GRACE_UNTIL
    _ENGINE_START_GRACE_UNTIL = time.monotonic() + 120.0
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "local_information_engine_public.py"),
    ]


def information_engine_health() -> bool:
    """Require both a live service and scheduled work after startup grace."""
    if not supervisor.port_healthy("127.0.0.1", 8765):
        return False
    if always_on_operations.heartbeat_healthy(12):
        return True
    return time.monotonic() < _ENGINE_START_GRACE_UNTIL


def comprehensive_validate_checkout() -> tuple[bool, str]:
    compile_files = [
        "ford_scan.py",
        "local_information_engine.py",
        "local_information_engine_public.py",
        "always_on_operations.py",
        "operations_acceptance.py",
        "discord_command_bot.py",
        "discord_command_bot_public.py",
        "discord_cards.py",
        "learning_center_catalog.py",
        "learning_center_content.py",
        "learning_search_router.py",
        "learning_application.py",
        "learning_application_public.py",
        "learning_question_gaps.py",
        "strict_learning_order.py",
        "sync_learning_center.py",
        "sync_discord_cards.py",
        "sync_discord_structure.py",
        "sync_discord_structure_public.py",
        "register_discord_commands.py",
        "tradysquid_supervisor.py",
        "run_supervisor.py",
        "automation_acceptance.py",
    ]
    compile_result = supervisor.run(
        [sys.executable, "-m", "py_compile", *compile_files], timeout=180
    )
    if compile_result.returncode:
        return False, (compile_result.stderr or compile_result.stdout)[-2000:]

    validations = [
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "test_learning_center.py",
            "test_strict_learning_order.py",
            "test_supervisor_availability.py",
            "test_local_information_engine.py",
            "test_always_on_operations.py",
        ],
        [sys.executable, "sync_learning_center.py"],
        [sys.executable, "learning_search_router.py"],
        [sys.executable, "learning_application_public.py"],
        [sys.executable, "always_on_operations.py"],
    ]
    for command in validations:
        result = supervisor.run(command, timeout=300)
        if result.returncode:
            detail = (result.stderr or result.stdout or "validation failed")[-2000:]
            return False, f"{' '.join(command)}: {detail}"
    return True, (
        "Compilation, focused tests, curriculum, routed search, live application, "
        "question-gap queue, strict Learning Center order, full scheduler heartbeat, "
        "off-hours research, interval diagnostics, self-repair, service availability, "
        "and automatic update recovery validation passed"
    )


def public_run_discord_configuration() -> list[str]:
    results: list[str] = []
    if supervisor.AUTO_REGISTER_COMMANDS:
        command_result = supervisor.run(
            [
                sys.executable,
                str(ROOT / "run_with_env.py"),
                str(ROOT / "register_discord_commands.py"),
            ],
            timeout=120,
        )
        if command_result.returncode:
            results.append(
                "command registration failed: "
                + (command_result.stderr or command_result.stdout)[-700:]
            )
        else:
            results.append("Discord slash commands synchronized")

    if supervisor.AUTO_DISCORD_SYNC:
        structure_result = supervisor.run(
            [
                sys.executable,
                str(ROOT / "run_with_env.py"),
                str(ROOT / "sync_discord_structure_public.py"),
                "--apply",
            ],
            timeout=900,
        )
        if structure_result.returncode:
            results.append(
                "comprehensive Discord structure sync failed: "
                + (structure_result.stderr or structure_result.stdout)[-1200:]
            )
        else:
            results.append(
                "Strictly ordered Learning Center, always-on activity ledger, "
                "automation diagnostics, question-gap review queue, lesson cards, "
                "references, guides, and permissions synchronized"
            )
    return results


def discord_results_failed(results: Iterable[object] | None) -> bool:
    failure_words = (" failed", "error", "blocked", "timed out", "timeout")
    for result in results or []:
        lowered = f" {str(result).casefold()}"
        if any(word in lowered for word in failure_words):
            return True
    return False


def record_discord_sync_results(results: list[str], *, source: str) -> bool:
    payload = supervisor.state_payload()
    previous_status = str(payload.get("last_discord_sync_status") or "UNKNOWN")
    previous_signature = str(payload.get("last_discord_sync_signature") or "")
    failed = discord_results_failed(results)
    status = "FAILED" if failed else "OK"
    signature = " | ".join(results)[-3500:]
    update_status = str(payload.get("last_update_status") or "")
    if failed and update_status == "DEPLOYED":
        update_status = "DEPLOYED_WITH_DISCORD_ERRORS"

    supervisor.write_state(
        last_discord_sync_status=status,
        last_discord_sync_signature=signature,
        last_discord_sync_source=source,
        last_discord_sync_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        last_update_status=update_status,
        discord_results=results,
    )

    if failed and signature != previous_signature:
        supervisor.discord_post(
            "\n".join(
                [
                    "⚠️ **Tradysquids Discord synchronization failed**",
                    "The supervisor will retry automatically every update cycle.",
                    *[f"• {item}" for item in results],
                ]
            )[:1900],
            "workflow-log",
        )
    elif not failed and previous_status == "FAILED":
        supervisor.discord_post(
            "\n".join(
                [
                    "✅ **Tradysquids Discord synchronization recovered**",
                    *[f"• {item}" for item in results],
                ]
            )[:1900],
            "workflow-log",
        )
    return not failed


def retry_pending_discord_configuration() -> bool:
    payload = supervisor.state_payload()
    pending = (
        str(payload.get("last_discord_sync_status") or "") == "FAILED"
        or discord_results_failed(payload.get("discord_results") or [])
    )
    if not pending:
        return False
    supervisor.supervisor_log(
        "Retrying previously failed Discord configuration without waiting for another commit"
    )
    results = public_run_discord_configuration()
    record_discord_sync_results(results, source="automatic-retry")
    return True


def verify_and_repair_discord_integrity() -> bool:
    if not supervisor.AUTO_DISCORD_SYNC:
        return False
    payload = supervisor.state_payload()
    previous_status = str(payload.get("discord_integrity_status") or "UNKNOWN")
    previous_detail = str(payload.get("discord_integrity_detail") or "")
    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN,
        ford_scan.DISCORD_GUILD_ID,
    )
    if not tracker.enabled:
        return False
    try:
        result = strict_learning_order.enforce_learning_channel_order(
            tracker,
            attempts=3,
            retry_delay_seconds=1.0,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[-1800:]
        supervisor.write_state(
            discord_integrity_status="FAILED",
            discord_integrity_detail=detail,
            discord_integrity_checked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        if detail != previous_detail:
            supervisor.discord_post(
                "⚠️ **Tradysquids Discord integrity repair failed**\n"
                f"```{detail[:1400]}```\n"
                "The supervisor will retry automatically.",
                "workflow-log",
            )
        return False

    changed = bool(result.get("changed"))
    detail = (
        f"Verified {result['canonical']} official channels in ascending order; "
        f"extras={result['extras']}; changed={changed}; attempts={result['attempts']}"
    )
    supervisor.write_state(
        discord_integrity_status="OK",
        discord_integrity_detail=detail,
        discord_integrity_checked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    if changed or previous_status == "FAILED":
        supervisor.discord_post(
            "✅ **Tradysquids Discord integrity recovered**\n"
            "Learning Center verified in ascending `01 → 27` order.",
            "workflow-log",
        )
    return True


def monitored_fetch_remote_sha() -> str:
    payload = supervisor.state_payload()
    previous_status = str(payload.get("last_fetch_status") or "UNKNOWN")
    previous_signature = str(payload.get("last_fetch_error_signature") or "")
    try:
        remote = ORIGINAL_FETCH_REMOTE_SHA()
    except RuntimeError as exc:
        detail = str(exc)[-1500:]
        signature = detail.casefold()
        supervisor.write_state(
            last_fetch_status="FAILED",
            last_fetch_error_signature=signature,
            last_fetch_detail=detail,
            last_fetch_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        if signature != previous_signature:
            supervisor.discord_post(
                "\n".join(
                    [
                        "⚠️ **Tradysquids automatic update check failed**",
                        "The laptop could not fetch `origin/main`.",
                        f"```{detail[:1200]}```",
                        "The supervisor will keep retrying automatically.",
                    ]
                ),
                "workflow-log",
            )
        raise

    supervisor.write_state(
        last_fetch_status="OK",
        last_fetch_error_signature="",
        last_fetch_detail="origin/main fetched successfully",
        last_fetch_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        last_remote_sha=remote,
        local_sha=supervisor.current_sha(),
    )
    if previous_status == "FAILED":
        supervisor.discord_post(
            "✅ **Tradysquids automatic update checks recovered**\n"
            f"Remote version `{remote[:12]}` is reachable again.",
            "workflow-log",
        )
    return remote


def low_downtime_deploy_if_needed(*, force: bool = False) -> bool:
    original_stop_all = supervisor.stop_all_services
    staged_stop_used = False

    def pause_scheduled_writer() -> None:
        nonlocal staged_stop_used
        if staged_stop_used:
            original_stop_all()
            return
        staged_stop_used = True
        supervisor.stop_process("information-engine")
        supervisor.supervisor_log(
            "Information engine paused for deployment; command-bot and ngrok remain online"
        )
        time.sleep(1)

    supervisor.stop_all_services = pause_scheduled_writer
    try:
        deployed = ORIGINAL_DEPLOY_IF_NEEDED(force=force)
    finally:
        supervisor.stop_all_services = original_stop_all

    payload = supervisor.state_payload()
    if deployed and str(payload.get("last_update_status") or "") == "DEPLOYED":
        results = [str(item) for item in payload.get("discord_results") or []]
        record_discord_sync_results(results, source="deployment")
        return True

    if not deployed:
        retried = retry_pending_discord_configuration()
        if not retried:
            verify_and_repair_discord_integrity()
    return deployed


def service_health_snapshot() -> dict[str, bool]:
    return {
        service.name: bool(supervisor.LAST_HEALTH.get(service.name, False))
        for service in supervisor.SERVICES
    }


def ensure_services_with_readiness() -> None:
    global _LAST_READY_SIGNATURE

    ORIGINAL_ENSURE_SERVICES()
    statuses = service_health_snapshot()
    signature = tuple((name, statuses[name]) for name in sorted(statuses))
    supervisor.write_state(
        service_health=statuses,
        supervisor_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        scheduler_heartbeat_healthy=always_on_operations.heartbeat_healthy(12),
        local_sha=supervisor.current_sha(),
        auto_update_enabled=supervisor.AUTO_UPDATE,
    )

    all_ready = bool(statuses) and all(statuses.values())
    previously_all_ready = bool(_LAST_READY_SIGNATURE) and all(
        value for _, value in _LAST_READY_SIGNATURE
    )
    if all_ready and (signature != _LAST_READY_SIGNATURE or not previously_all_ready):
        version = supervisor.current_sha()
        supervisor.discord_post(
            "\n".join(
                [
                    "✅ **Tradysquids services ready**",
                    f"Version `{version}`",
                    "• command-bot: **ONLINE**",
                    "• information-engine: **ONLINE**",
                    "• scheduler heartbeat: **FIRING INTERVALS**",
                    "• ngrok: **ONLINE**",
                    "• automatic updater: **ONLINE**",
                    "Live activity receipts and automatic diagnostics are ready.",
                ]
            ),
            "system-health",
        )
    _LAST_READY_SIGNATURE = signature


supervisor.take_process_ownership = safe_take_process_ownership
supervisor.command_bot_command = public_command_bot_command
supervisor.information_engine_command = public_information_engine_command
supervisor.validate_checkout = comprehensive_validate_checkout
supervisor.run_discord_configuration = public_run_discord_configuration
supervisor.fetch_remote_sha = monitored_fetch_remote_sha
supervisor.deploy_if_needed = low_downtime_deploy_if_needed
supervisor.ensure_services = ensure_services_with_readiness

supervisor.SERVICES = [
    supervisor.Service(
        service.name,
        (
            public_command_bot_command
            if service.name == "command-bot"
            else public_information_engine_command
            if service.name == "information-engine"
            else service.command
        ),
        information_engine_health if service.name == "information-engine" else service.healthy,
    )
    for service in supervisor.SERVICES
]


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
