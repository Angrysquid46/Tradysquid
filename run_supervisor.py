"""Launch the supervisor with safe ownership and public-service overrides."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent
ORIGINAL_DEPLOY_IF_NEEDED = supervisor.deploy_if_needed
ORIGINAL_ENSURE_SERVICES = supervisor.ensure_services
_LAST_READY_SIGNATURE: tuple[tuple[str, bool], ...] | None = None


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
    """Run the wrapper that contains public ticker and Learning Center features."""
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "discord_command_bot_public.py"),
    ]


def comprehensive_validate_checkout() -> tuple[bool, str]:
    """Validate every deployment-critical public and learning module."""
    compile_files = [
        "ford_scan.py",
        "local_information_engine.py",
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
        ],
        [sys.executable, "sync_learning_center.py"],
        [sys.executable, "learning_search_router.py"],
        [sys.executable, "learning_application_public.py"],
    ]
    for command in validations:
        result = supervisor.run(command, timeout=300)
        if result.returncode:
            detail = (result.stderr or result.stdout or "validation failed")[-2000:]
            return False, f"{' '.join(command)}: {detail}"
    return True, (
        "Compilation, focused tests, curriculum, routed search, live application, "
        "question-gap queue, strict Learning Center order, and service-availability "
        "validation passed"
    )


def public_run_discord_configuration() -> list[str]:
    """Register commands and apply the public 27-topic Discord release."""
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
                "Strictly ordered Learning Center, question-gap review queue, lesson cards, references, guides, and permissions synchronized"
            )
    return results


def low_downtime_deploy_if_needed(*, force: bool = False) -> bool:
    """Keep the command bot and tunnel online during validation and Discord sync.

    The base supervisor used to stop every service before pulling, validating, and
    synchronizing Discord. That made slash commands unavailable for the entire
    deployment. Only the scheduled information engine needs to pause while files
    are updated. The command bot and ngrok continue serving the currently loaded
    code until the normal final restart swaps all services to the new version.
    """
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
        return ORIGINAL_DEPLOY_IF_NEEDED(force=force)
    finally:
        supervisor.stop_all_services = original_stop_all


def service_health_snapshot() -> dict[str, bool]:
    """Return the latest verified health state for every managed service."""
    return {
        service.name: bool(supervisor.LAST_HEALTH.get(service.name, False))
        for service in supervisor.SERVICES
    }


def ensure_services_with_readiness() -> None:
    """Run health recovery and announce only verified readiness transitions."""
    global _LAST_READY_SIGNATURE

    ORIGINAL_ENSURE_SERVICES()
    statuses = service_health_snapshot()
    signature = tuple((name, statuses[name]) for name in sorted(statuses))
    supervisor.write_state(service_health=statuses)

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
                    "• ngrok: **ONLINE**",
                    "Slash commands are ready for use.",
                ]
            ),
            "system-health",
        )
    _LAST_READY_SIGNATURE = signature


supervisor.take_process_ownership = safe_take_process_ownership
supervisor.command_bot_command = public_command_bot_command
supervisor.validate_checkout = comprehensive_validate_checkout
supervisor.run_discord_configuration = public_run_discord_configuration
supervisor.deploy_if_needed = low_downtime_deploy_if_needed
supervisor.ensure_services = ensure_services_with_readiness

# Service.command stores the original function object at import time, so replace
# the immutable Service entry as well. Otherwise the override would sit nearby
# looking useful while the supervisor continued launching the legacy bot.
supervisor.SERVICES = [
    supervisor.Service(
        service.name,
        public_command_bot_command if service.name == "command-bot" else service.command,
        service.healthy,
    )
    for service in supervisor.SERVICES
]


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
