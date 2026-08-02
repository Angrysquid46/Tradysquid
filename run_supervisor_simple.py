"""Run Tradysquid with a deliberately small automatic deployment path.

Upgrade flow:
1. Owner submits requests through Discord.
2. Requests are reviewed and implemented in GitHub.
3. The laptop checks origin/main every two minutes.
4. A new fast-forward commit is validated, installed, and restarted once.

Deployment does not own Discord structure synchronization, slash-command
registration, Learning Center repair, or engine acceptance. Those remain normal
runtime responsibilities of the features that need them. A transient Discord
failure therefore cannot block or roll back an otherwise valid code update.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import network_compat

network_compat.install()

import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent

# Deployment itself never performs Discord maintenance. Feature startup jobs own
# their channels and cards after the new code starts.
supervisor.AUTO_DISCORD_SYNC = False
supervisor.AUTO_REGISTER_COMMANDS = False


def take_process_ownership() -> None:
    """Stop older managed copies before this supervisor owns the services."""
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


def command_bot_command() -> list[str]:
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "discord_command_bot_public.py"),
    ]


def information_engine_command() -> list[str]:
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "local_information_engine_public.py"),
    ]


def fetch_remote_sha() -> str:
    """Fetch main without disturbing services; try normal routing then IPv4."""
    failures: list[str] = []
    attempts = (
        ("normal", ("fetch", "--quiet", "origin", "main")),
        ("ipv4", ("fetch", "--ipv4", "--quiet", "origin", "main")),
    )
    for label, arguments in attempts:
        result = supervisor.git(*arguments, timeout=60)
        if result.returncode == 0:
            remote = supervisor.git("rev-parse", "origin/main", check=True)
            supervisor.write_state(
                last_fetch_status="OK",
                last_fetch_mode=label,
                last_fetch_detail="origin/main fetched successfully",
                last_fetch_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                last_remote_sha=remote.stdout.strip(),
                local_sha=supervisor.current_sha(),
            )
            return remote.stdout.strip()
        detail = (result.stderr or result.stdout or "git fetch failed").strip()
        failures.append(f"{label}: {detail[-700:]}")
    joined = " | ".join(failures)
    supervisor.write_state(
        last_fetch_status="FAILED",
        last_fetch_mode="normal+ipv4",
        last_fetch_detail=joined,
        last_fetch_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    raise RuntimeError(joined)


def validate_checkout() -> tuple[bool, str]:
    """Run bounded checks before a new version is accepted."""
    compile_files = [
        "ford_scan.py",
        "discord_command_bot_public.py",
        "local_information_engine_bootstrap.py",
        "local_information_engine_public.py",
        "run_with_env.py",
        "tradysquid_supervisor.py",
        "run_supervisor_simple.py",
        "simple_upgrade_runtime.py",
        "github_upgrade_bridge.py",
        "github_upgrade_patch.py",
        "upgrade_batch_44.py",
        "upgrade_batch_44_live_acceptance.py",
        "applied_upgrades.py",
        "network_compat.py",
    ]
    compile_result = supervisor.run(
        [sys.executable, "-m", "py_compile", *compile_files],
        timeout=180,
    )
    if compile_result.returncode:
        return False, (compile_result.stderr or compile_result.stdout)[-2000:]

    tests = supervisor.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "test_github_upgrade_bridge.py",
            "test_supervisor_availability.py",
            "test_runtime_state_hygiene.py",
            "test_applied_upgrades.py",
            "test_simple_upgrade_flow.py",
        ],
        timeout=300,
    )
    if tests.returncode:
        return False, (tests.stderr or tests.stdout or "focused tests failed")[-2000:]
    return True, "Compilation and focused deployment tests passed"


def no_deployment_discord_configuration() -> list[str]:
    """Discord changes are applied by feature startup jobs, never by deployment."""
    return []


def ensure_services() -> None:
    """Keep services healthy without deployment acceptance gates."""
    supervisor.write_state(
        supervisor="ONLINE",
        supervisor_mode="SIMPLE_TWO_MINUTE_UPDATER",
        supervisor_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        local_sha=supervisor.current_sha(),
        auto_update_enabled=supervisor.AUTO_UPDATE,
        update_interval_seconds=supervisor.UPDATE_SECONDS,
    )
    original_ensure_services()
    statuses = {
        service.name: bool(supervisor.LAST_HEALTH.get(service.name, False))
        for service in supervisor.SERVICES
    }
    supervisor.write_state(
        supervisor="ONLINE",
        supervisor_mode="SIMPLE_TWO_MINUTE_UPDATER",
        service_health=statuses,
        supervisor_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        local_sha=supervisor.current_sha(),
        auto_update_enabled=supervisor.AUTO_UPDATE,
        update_interval_seconds=supervisor.UPDATE_SECONDS,
    )


original_ensure_services = supervisor.ensure_services
supervisor.take_process_ownership = take_process_ownership
supervisor.command_bot_command = command_bot_command
supervisor.information_engine_command = information_engine_command
supervisor.fetch_remote_sha = fetch_remote_sha
supervisor.validate_checkout = validate_checkout
supervisor.run_discord_configuration = no_deployment_discord_configuration
supervisor.ensure_services = ensure_services
supervisor.SERVICES = [
    supervisor.Service(
        service.name,
        command_bot_command
        if service.name == "command-bot"
        else information_engine_command
        if service.name == "information-engine"
        else service.command,
        service.healthy,
    )
    for service in supervisor.SERVICES
]


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
