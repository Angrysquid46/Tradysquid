"""Launch the supervisor with safe ownership and public-service overrides."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent


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
        "learning_question_gaps.py",
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
            "test_local_information_engine.py",
        ],
        [sys.executable, "sync_learning_center.py"],
        [sys.executable, "learning_search_router.py"],
        [sys.executable, "learning_application.py"],
    ]
    for command in validations:
        result = supervisor.run(command, timeout=300)
        if result.returncode:
            detail = (result.stderr or result.stdout or "validation failed")[-2000:]
            return False, f"{' '.join(command)}: {detail}"
    return True, (
        "Compilation, focused tests, curriculum, routed search, live application, "
        "and unanswered-question queue validation passed"
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
                "Ordered Learning Center, question-gap review queue, lesson cards, references, guides, and permissions synchronized"
            )
    return results


supervisor.take_process_ownership = safe_take_process_ownership
supervisor.command_bot_command = public_command_bot_command
supervisor.validate_checkout = comprehensive_validate_checkout
supervisor.run_discord_configuration = public_run_discord_configuration

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
