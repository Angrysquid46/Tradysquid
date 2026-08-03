"""Launch the tested clean rebuild from the laptop's existing main updater.

The legacy supervisor watches origin/main every two minutes. This module is the
one-time bridge from that running updater to the tested clean-rebuild branch.
It never reads or logs secret values. The PowerShell handoff preserves the full
local environment and performs live setup with rollback.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
LAUNCH_RECEIPT = STATE_DIR / "clean-rebuild-auto-launch.json"
STOP_FLAG = STATE_DIR / "supervisor-stop.flag"
EXPECTED_CLEAN_COMMIT = "a27b61b1198e575f66e339001b4c120e7085e0cd"
CLEAN_BRANCH = "clean-rebuild"
ARCHIVE_BRANCH = "archive/current-failed-implementation"
TERMINAL_STATUSES = {"LAUNCHED", "PASS", "ROLLED_BACK", "FAILED", "BLOCKED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _read_receipt() -> dict[str, Any]:
    if not LAUNCH_RECEIPT.exists():
        return {}
    try:
        value = json.loads(LAUNCH_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_receipt(status: str, **details: Any) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "expected_clean_commit": EXPECTED_CLEAN_COMMIT,
        "observed_at": _now(),
        "secret_values_written": False,
        **details,
    }
    temporary = LAUNCH_RECEIPT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(LAUNCH_RECEIPT)


def _current_branch() -> str:
    result = _run("branch", "--show-current", timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _prepare_worktree() -> Path:
    parent = ROOT.parent
    worktree = parent / f"Tradysquid-clean-handoff-{EXPECTED_CLEAN_COMMIT[:12]}"

    _run("worktree", "remove", "--force", str(worktree), timeout=120)
    if worktree.exists():
        shutil.rmtree(worktree, ignore_errors=True)
    _run("worktree", "prune", timeout=60)

    result = _run(
        "worktree",
        "add",
        "--detach",
        str(worktree),
        EXPECTED_CLEAN_COMMIT,
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git worktree add failed").strip()
        raise RuntimeError(detail[-1500:])
    return worktree


def launch_if_needed() -> bool:
    """Start one detached live handoff and tell the supervisor to exit."""

    if os.name != "nt":
        return False
    if _current_branch() != "main":
        return False

    previous = _read_receipt()
    if (
        previous.get("expected_clean_commit") == EXPECTED_CLEAN_COMMIT
        and str(previous.get("status") or "").upper() in TERMINAL_STATUSES
    ):
        return False
    if STOP_FLAG.exists():
        return False

    try:
        fetch = _run(
            "fetch",
            "origin",
            f"+refs/heads/{CLEAN_BRANCH}:refs/remotes/origin/{CLEAN_BRANCH}",
            f"+refs/heads/{ARCHIVE_BRANCH}:refs/remotes/origin/{ARCHIVE_BRANCH}",
            timeout=180,
        )
        if fetch.returncode != 0:
            detail = (fetch.stderr or fetch.stdout or "clean branch fetch failed").strip()
            raise RuntimeError(detail[-1500:])

        observed = _run("rev-parse", f"refs/remotes/origin/{CLEAN_BRANCH}", timeout=30)
        observed_commit = observed.stdout.strip() if observed.returncode == 0 else ""
        if observed_commit != EXPECTED_CLEAN_COMMIT:
            raise RuntimeError(
                "clean-rebuild moved after validation; "
                f"expected {EXPECTED_CLEAN_COMMIT}, observed {observed_commit or 'unknown'}"
            )

        worktree = _prepare_worktree()
        script = worktree / "scripts" / "auto_install_clean_rebuild.ps1"
        if not script.exists():
            raise RuntimeError(f"automatic handoff script is missing: {script}")

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        stdout_path = STATE_DIR / "clean-rebuild-auto-launch.stdout.log"
        stderr_path = STATE_DIR / "clean-rebuild-auto-launch.stderr.log"
        STOP_FLAG.write_text(
            f"clean rebuild handoff {EXPECTED_CLEAN_COMMIT}\n",
            encoding="utf-8",
        )

        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ExpectedCleanCommit",
            EXPECTED_CLEAN_COMMIT,
            "-RepositoryPath",
            str(ROOT),
        ]
        creation_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        with stdout_path.open("a", encoding="utf-8") as stdout_handle, stderr_path.open(
            "a", encoding="utf-8"
        ) as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=worktree,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creation_flags,
            )

        _write_receipt(
            "LAUNCHED",
            process_id=process.pid,
            repository_path=str(ROOT),
            worktree_path=str(worktree),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
        )
        return True
    except Exception as exc:  # noqa: BLE001 - launcher must leave legacy alive
        STOP_FLAG.unlink(missing_ok=True)
        _write_receipt(
            "FAILED",
            error=f"{type(exc).__name__}: {exc}",
            repository_path=str(ROOT),
        )
        return False
