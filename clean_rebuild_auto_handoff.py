"""Launch the audited clean rebuild from the laptop's existing main updater.

The legacy supervisor watches origin/main every two minutes. This module is the
one-time bridge from that running updater to the exact audited clean-rebuild
commit. It never reads or logs secret values. The PowerShell handoff preserves
the full local environment and performs live setup with rollback.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
LAUNCH_RECEIPT = STATE_DIR / "clean-rebuild-auto-launch.json"
FINAL_RECEIPT = STATE_DIR / "clean-rebuild-auto-handoff.json"
STOP_FLAG = STATE_DIR / "supervisor-stop.flag"
EXPECTED_CLEAN_COMMIT = "831559b1de1cd90eb8df47e32e5462eabf4b8fa0"
CLEAN_BRANCH = "clean-rebuild"
ARCHIVE_BRANCH = "archive/current-failed-implementation"
MAX_ATTEMPTS = 3
LAUNCH_GRACE_SECONDS = 45 * 60
RETRY_BACKOFF_SECONDS = 15 * 60
SUCCESS_STATUSES = {"PASS"}
FAILURE_STATUSES = {"FAILED", "ROLLED_BACK", "BLOCKED"}


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_datetime().isoformat()


def _run(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_receipt() -> dict[str, Any]:
    return _read_json(LAUNCH_RECEIPT)


def _read_final_receipt() -> dict[str, Any]:
    return _read_json(FINAL_RECEIPT)


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


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(receipt: dict[str, Any], now: datetime) -> float:
    observed = _parse_time(receipt.get("observed_at"))
    if observed is None:
        return float("inf")
    return max((now - observed).total_seconds(), 0.0)


def _targets_expected(receipt: dict[str, Any]) -> bool:
    return str(receipt.get("expected_clean_commit") or "") == EXPECTED_CLEAN_COMMIT


def _attempt_count(receipt: dict[str, Any]) -> int:
    try:
        return max(int(receipt.get("attempt_count") or 0), 0)
    except (TypeError, ValueError):
        return 0


def evaluate_handoff(
    previous: dict[str, Any],
    final: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a deterministic launch decision from both local receipt files."""

    current_time = now or _now_datetime()
    previous_matches = _targets_expected(previous)
    final_matches = _targets_expected(final)
    attempts = _attempt_count(previous) if previous_matches else 0
    previous_time = _parse_time(previous.get("observed_at"))
    final_time = _parse_time(final.get("observed_at"))
    final_is_current = final_matches and (
        not previous_matches
        or previous_time is None
        or (final_time is not None and final_time >= previous_time)
    )

    if final_is_current:
        final_status = _normalize_status(final.get("status"))
        if final_status in SUCCESS_STATUSES:
            return {
                "action": "complete",
                "attempt_count": attempts,
                "reason": "current final PASS receipt",
                "final_status": final_status,
            }
        if final_status in FAILURE_STATUSES:
            if attempts >= MAX_ATTEMPTS:
                return {
                    "action": "blocked",
                    "attempt_count": attempts,
                    "reason": "maximum automatic attempts reached",
                    "final_status": final_status,
                }
            age = _age_seconds(final, current_time)
            if age < RETRY_BACKOFF_SECONDS:
                return {
                    "action": "wait",
                    "attempt_count": attempts,
                    "reason": "failure retry backoff",
                    "retry_after_seconds": RETRY_BACKOFF_SECONDS - age,
                    "final_status": final_status,
                }
            return {
                "action": "launch",
                "attempt_count": attempts + 1,
                "reason": "retry after current failed handoff",
                "final_status": final_status,
            }
        if _age_seconds(final, current_time) < LAUNCH_GRACE_SECONDS:
            return {
                "action": "wait",
                "attempt_count": attempts,
                "reason": "current final receipt has an unresolved status",
                "final_status": final_status,
            }

    if previous_matches:
        previous_status = _normalize_status(previous.get("status"))
        previous_age = _age_seconds(previous, current_time)
        if previous_status in SUCCESS_STATUSES:
            return {
                "action": "complete",
                "attempt_count": attempts,
                "reason": "launch receipt already records PASS",
            }
        if previous_status == "LAUNCHED" and previous_age < LAUNCH_GRACE_SECONDS:
            return {
                "action": "wait",
                "attempt_count": attempts,
                "reason": "handoff process is still inside its grace window",
                "retry_after_seconds": LAUNCH_GRACE_SECONDS - previous_age,
            }
        if attempts >= MAX_ATTEMPTS:
            return {
                "action": "blocked",
                "attempt_count": attempts,
                "reason": "maximum automatic attempts reached",
            }
        if previous_status in FAILURE_STATUSES and previous_age < RETRY_BACKOFF_SECONDS:
            return {
                "action": "wait",
                "attempt_count": attempts,
                "reason": "launcher failure retry backoff",
                "retry_after_seconds": RETRY_BACKOFF_SECONDS - previous_age,
            }

    return {
        "action": "launch",
        "attempt_count": attempts + 1,
        "reason": "no current successful handoff receipt",
    }


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


def _stale_stop_flag(now: datetime) -> bool:
    if not STOP_FLAG.exists():
        return False
    try:
        modified = datetime.fromtimestamp(STOP_FLAG.stat().st_mtime, timezone.utc)
    except OSError:
        return False
    return (now - modified).total_seconds() >= LAUNCH_GRACE_SECONDS


def launch_if_needed() -> bool:
    """Start one detached live handoff and tell the supervisor launcher to exit."""

    if os.name != "nt":
        return False
    if _current_branch() != "main":
        return False

    now = _now_datetime()
    previous = _read_receipt()
    final = _read_final_receipt()
    decision = evaluate_handoff(previous, final, now=now)
    action = str(decision["action"])

    if action == "complete":
        if _normalize_status(previous.get("status")) != "PASS":
            _write_receipt(
                "PASS",
                attempt_count=int(decision.get("attempt_count") or 0),
                final_receipt_path=str(FINAL_RECEIPT),
                final_status=decision.get("final_status", "PASS"),
            )
        return False
    if action == "blocked":
        if _normalize_status(previous.get("status")) != "BLOCKED":
            _write_receipt(
                "BLOCKED",
                attempt_count=int(decision.get("attempt_count") or 0),
                error=str(decision.get("reason") or "automatic handoff blocked"),
                final_receipt_path=str(FINAL_RECEIPT),
            )
        return False
    if action == "wait":
        return False

    if STOP_FLAG.exists():
        if not _stale_stop_flag(now):
            return False
        STOP_FLAG.unlink(missing_ok=True)

    attempt_count = int(decision.get("attempt_count") or 1)
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
            attempt_count=attempt_count,
            process_id=process.pid,
            repository_path=str(ROOT),
            worktree_path=str(worktree),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            final_receipt_path=str(FINAL_RECEIPT),
            reason=str(decision.get("reason") or "automatic handoff"),
        )
        return True
    except Exception as exc:  # noqa: BLE001 - launcher must leave legacy alive
        STOP_FLAG.unlink(missing_ok=True)
        _write_receipt(
            "FAILED",
            attempt_count=attempt_count,
            error=f"{type(exc).__name__}: {exc}",
            repository_path=str(ROOT),
            next_retry_after=(
                _now_datetime() + timedelta(seconds=RETRY_BACKOFF_SECONDS)
            ).isoformat(),
        )
        return False
