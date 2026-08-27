"""Run Tradysquid with one deliberately small two-minute deployment path.

Discord and diagnostics are runtime responsibilities, never deployment gates.
The updater only fetches, performs safe preflight, fast-forwards, validates,
rolls back when necessary, and exits once so the BAT launcher restarts the stack.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import network_compat
import deployment_validation_manifest as validation_manifest

network_compat.install()

import tradysquid_supervisor as supervisor

ROOT = Path(__file__).resolve().parent
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
    validation_manifest.validate_manifest()
    compile_result = supervisor.run(
        [sys.executable, "-m", "py_compile", *validation_manifest.COMPILE_MODULES],
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
            *validation_manifest.FOCUSED_TEST_MODULES,
        ],
        timeout=480,
    )
    if tests.returncode:
        return False, (tests.stderr or tests.stdout or "focused tests failed")[-2000:]
    return True, "Compilation and focused deployment tests passed"


def no_deployment_discord_configuration() -> list[str]:
    """Feature startup jobs own Discord changes after the new code starts."""
    return []


def _prepare_runtime_backup(paths: list[str]) -> list[str]:
    """Prove runtime data can be copied before stopping any healthy service."""
    target_root = supervisor.RUNTIME_BACKUP_DIR
    if target_root.exists():
        shutil.rmtree(target_root)
    saved: list[str] = []
    for relative in paths:
        source = ROOT / relative
        if not source.exists() or not source.is_file():
            continue
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if target.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Runtime backup verification failed for {relative}")
        saved.append(relative)
    return saved


def _clean_tracked_runtime(paths: list[str]) -> None:
    if not paths:
        return
    result = supervisor.git("checkout", "--", *paths, timeout=120)
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout or "could not clean runtime files")[-1200:]
        )


def _rollback(local: str, saved_runtime: list[str], detail: str) -> None:
    supervisor.git("reset", "--hard", local, timeout=120)
    supervisor.restore_runtime_changes(saved_runtime)
    supervisor.write_state(
        last_update_status="ROLLED_BACK",
        last_update_detail=detail,
        rollback_result="OK",
        deployed_sha=local,
        local_sha=local,
        last_known_working_sha=local,
        last_deployment_finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    supervisor.discord_post(
        "↩️ **Tradysquid update rolled back**\n"
        f"Restored `{local[:12]}` after validation failed.\n"
        f"```{detail[:1100]}```",
        "workflow-log",
    )


def deploy_if_needed(*, force: bool = False) -> bool:
    """Safely install a newer main commit; return True for one BAT restart."""
    branch_result = supervisor.git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    if branch != "main":
        detail = f"Automatic deployment requires main, not {branch or 'unknown'}"
        supervisor.write_state(last_update_status="WRONG_BRANCH", last_update_detail=detail)
        return False

    local = supervisor.git("rev-parse", "HEAD", check=True).stdout.strip()
    try:
        remote = fetch_remote_sha()
    except RuntimeError as exc:
        supervisor.supervisor_log(f"Update check failed: {exc}")
        supervisor.write_state(last_update_status="FETCH_FAILED", last_update_detail=str(exc))
        return False
    if remote == local and not force:
        # A Git client or an operator can fast-forward the shared checkout
        # outside this process.  In that case the files match origin/main,
        # but the managed services can still be executing the older loaded
        # modules.  Reconcile the recorded deployed version before treating
        # the checkout as a no-op, so the main loop performs one controlled
        # restart after validating the already-present code.
        state = supervisor.state_payload()
        deployed = str(state.get("deployed_sha") or "")
        if deployed and not local.startswith(deployed):
            valid, validation_detail = validate_checkout()
            if not valid:
                supervisor.write_state(
                    last_update_status="RECONCILIATION_FAILED",
                    last_update_detail=validation_detail,
                )
                return False
            supervisor.write_state(
                last_update_status="DEPLOYED",
                last_update_detail=(
                    "Reconciled externally fast-forwarded main checkout. "
                    + validation_detail
                )[:1600],
                rollback_result="NOT_NEEDED",
                deployed_sha=local,
                local_sha=local,
                last_known_working_sha=local,
                last_deployment_finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                discord_results=[],
            )
            supervisor.discord_post(
                "✅ **Tradysquid code reconciliation validated**\n"
                f"Restarting services on `{local[:12]}`.",
                "workflow-log",
            )
            return True
        return False

    try:
        dirty_paths = supervisor.dirty_tracked_paths()
    except RuntimeError as exc:
        supervisor.write_state(last_update_status="STATUS_FAILED", last_update_detail=str(exc))
        return False
    blocked = [path for path in dirty_paths if not supervisor.runtime_mutable(path)]
    if blocked:
        detail = "Unexpected tracked changes block deployment: " + ", ".join(blocked[:12])
        supervisor.write_state(last_update_status="DIRTY", last_update_detail=detail)
        return False

    ancestor = supervisor.git("merge-base", "--is-ancestor", local, remote)
    if ancestor.returncode:
        detail = "origin/main is not a safe fast-forward from the laptop checkout"
        supervisor.write_state(last_update_status="NON_FAST_FORWARD", last_update_detail=detail)
        return False

    runtime_paths = [path for path in dirty_paths if supervisor.runtime_mutable(path)]
    try:
        saved_runtime = _prepare_runtime_backup(runtime_paths)
    except (OSError, RuntimeError) as exc:
        detail = f"Runtime backup preflight failed before service stop: {exc}"
        supervisor.write_state(last_update_status="BACKUP_FAILED", last_update_detail=detail)
        return False

    backup_ref = f"refs/heads/backup/auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    backup_result = supervisor.git("update-ref", backup_ref, local)
    if backup_result.returncode:
        detail = (backup_result.stderr or backup_result.stdout or "rollback ref failed")[-1200:]
        supervisor.write_state(last_update_status="BACKUP_REF_FAILED", last_update_detail=detail)
        return False

    supervisor.write_state(
        last_update_status="DEPLOYING",
        last_update_detail=f"{local[:12]} -> {remote[:12]}",
        last_deployment_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        last_known_working_sha=local,
        rollback_ref=backup_ref,
    )
    supervisor.discord_post(
        f"🔄 **Tradysquid deployment started**\n`{local[:12]}` → `{remote[:12]}`",
        "workflow-log",
    )

    supervisor.stop_all_services()
    try:
        _clean_tracked_runtime(runtime_paths)
        merge = supervisor.git("merge", "--ff-only", "origin/main", timeout=180)
        if merge.returncode:
            detail = (merge.stderr or merge.stdout or "git merge failed")[-1500:]
            _rollback(local, saved_runtime, detail)
            return True

        valid, validation_detail = validate_checkout()
        if not valid:
            _rollback(local, saved_runtime, validation_detail)
            return True

        supervisor.restore_runtime_changes(saved_runtime)
        supervisor.DISCORD_CHANNEL_CACHE.clear()
        supervisor.write_state(
            last_update_status="DEPLOYED",
            last_update_detail=validation_detail,
            rollback_result="NOT_NEEDED",
            deployed_sha=remote,
            local_sha=remote,
            last_known_working_sha=remote,
            last_deployment_finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            discord_results=[],
        )
        supervisor.discord_post(
            "✅ **Tradysquid code update validated**\n"
            f"Installed `{remote[:12]}`. Services will restart once; runtime diagnostics will verify the result.",
            "workflow-log",
        )
        return True
    except Exception as exc:
        _rollback(local, saved_runtime, f"{type(exc).__name__}: {exc}")
        return True


def _tracked_start_service(service: supervisor.Service) -> bool:
    before = supervisor.PROCESSES.get(service.name)
    before_pid = before.pid if before and before.poll() is None else None
    started = original_start_service(service)
    after = supervisor.PROCESSES.get(service.name)
    after_pid = after.pid if after and after.poll() is None else None
    if started and after_pid and after_pid != before_pid:
        state = supervisor.state_payload()
        counts = state.get("service_restart_counts") if isinstance(state.get("service_restart_counts"), dict) else {}
        times = state.get("service_last_started_at") if isinstance(state.get("service_last_started_at"), dict) else {}
        counts[service.name] = int(counts.get(service.name) or 0) + 1
        times[service.name] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        supervisor.write_state(service_restart_counts=counts, service_last_started_at=times)
    return started


def ensure_services() -> None:
    """Keep services healthy without deployment or Discord acceptance gates."""
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
    process_ids = {
        name: process.pid
        for name, process in supervisor.PROCESSES.items()
        if process and process.poll() is None
    }
    supervisor.write_state(
        supervisor="ONLINE",
        supervisor_mode="SIMPLE_TWO_MINUTE_UPDATER",
        service_health=statuses,
        service_process_ids=process_ids,
        expected_ports={
            "command-bot": 8080,
            "information-engine": 8765,
            "supervisor": 8876,
            "ngrok": 4040,
        },
        supervisor_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        local_sha=supervisor.current_sha(),
        auto_update_enabled=supervisor.AUTO_UPDATE,
        update_interval_seconds=supervisor.UPDATE_SECONDS,
    )


original_ensure_services = supervisor.ensure_services
original_start_service = supervisor.start_service
supervisor.take_process_ownership = take_process_ownership
supervisor.command_bot_command = command_bot_command
supervisor.information_engine_command = information_engine_command
supervisor.fetch_remote_sha = fetch_remote_sha
supervisor.validate_checkout = validate_checkout
supervisor.run_discord_configuration = no_deployment_discord_configuration
supervisor.deploy_if_needed = deploy_if_needed
supervisor.start_service = _tracked_start_service
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
    import clean_rebuild_auto_handoff

    if clean_rebuild_auto_handoff.launch_if_needed():
        raise SystemExit(76)
    raise SystemExit(supervisor.main())
