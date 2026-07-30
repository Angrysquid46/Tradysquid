"""Shared Codex/Claude update coordination backed by OneDrive."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONTROL_DIR = (
    Path(os.environ.get("OneDrive", str(ROOT.parent)))
    / "Tradysquid-AI-Control"
)
CONTROL_DIR = Path(os.environ.get("AI_CONTROL_DIR", str(DEFAULT_CONTROL_DIR)))
LOCK_PATH = CONTROL_DIR / "UPDATE_LOCK.json"
ACTIVE_TASK_PATH = CONTROL_DIR / "ACTIVE_TASK.json"
EVENTS_PATH = CONTROL_DIR / "CHANGELOG.jsonl"
STATE_PATH = CONTROL_DIR / "CURRENT_STATE.md"
HISTORY_PATH = CONTROL_DIR / "GIT_HISTORY.md"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout.rstrip()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def repository_snapshot() -> dict[str, Any]:
    status = git("status", "--porcelain")
    return {
        "captured_at": now_iso(),
        "repository": str(ROOT),
        "branch": git("branch", "--show-current"),
        "commit": git("rev-parse", "HEAD"),
        "commit_subject": git("log", "-1", "--pretty=%s"),
        "dirty_files": [
            line[3:] for line in status.splitlines() if len(line) >= 4
        ],
        "remote": git("remote", "get-url", "origin"),
    }


def update_current_state() -> dict[str, Any]:
    snapshot = repository_snapshot()
    lock = None
    if LOCK_PATH.exists():
        try:
            lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lock = {"error": "Unreadable lock file; do not begin an update."}
    lines = [
        "# Tradysquid Current State",
        "",
        "GitHub/main is the authoritative code baseline. The running laptop "
        "services should match this checkout after each completed update.",
        "",
        f"- Captured: {snapshot['captured_at']}",
        f"- Branch: `{snapshot['branch']}`",
        f"- Commit: `{snapshot['commit']}`",
        f"- Subject: {snapshot['commit_subject']}",
        f"- Update lock: {'ACTIVE' if lock else 'clear'}",
    ]
    if lock:
        lines.extend([
            f"- Lock owner: `{lock.get('actor', 'unknown')}`",
            f"- Task: {lock.get('task', 'unknown')}",
            f"- Started: {lock.get('started_at', 'unknown')}",
        ])
    lines.extend(["", "## Uncommitted files", ""])
    lines.extend(
        f"- `{path}`" for path in snapshot["dirty_files"]
    )
    if not snapshot["dirty_files"]:
        lines.append("- None")
    STATE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return snapshot


def update_git_history(limit: int = 100) -> None:
    rows = git(
        "log",
        f"-{limit}",
        "--date=iso-strict",
        "--pretty=format:%H%x09%ad%x09%an%x09%s",
    )
    lines = [
        "# Git Commit History",
        "",
        "This is repository history, not conversation history. Actor-specific "
        "details for coordinated AI work are in CHANGELOG.jsonl.",
        "",
        "| Commit | Date | Git author | Change |",
        "|---|---|---|---|",
    ]
    for row in rows.splitlines():
        commit, date, author, subject = row.split("\t", 3)
        subject = subject.replace("|", "\\|")
        lines.append(
            f"| `{commit[:12]}` | {date} | {author} | {subject} |"
        )
    HISTORY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_event(event: dict[str, Any]) -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def acquire(actor: str, task: str, method: str) -> dict[str, Any]:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "actor": actor,
        "task": task,
        "method": method,
        "started_at": now_iso(),
        "starting_commit": git("rev-parse", "HEAD"),
        "process_id": os.getpid(),
    }
    try:
        descriptor = os.open(
            LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as exc:
        existing = LOCK_PATH.read_text(encoding="utf-8")
        raise RuntimeError(
            "Another update is active. Do not modify files. Lock: " + existing
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    atomic_json(ACTIVE_TASK_PATH, payload)
    append_event({"event": "BEGIN", **payload})
    update_current_state()
    return payload


def finish(
    actor: str,
    summary: str,
    method: str,
    tests: str,
    files: list[str],
    commit: str = "",
) -> dict[str, Any]:
    if not LOCK_PATH.exists():
        raise RuntimeError("No update lock exists; refusing an untracked finish.")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("actor", "").lower() != actor.lower():
        raise RuntimeError(
            f"Lock belongs to {lock.get('actor')}; {actor} cannot release it."
        )
    commit = git("rev-parse", commit or "HEAD")
    event = {
        "event": "COMPLETE",
        "actor": actor,
        "task": lock.get("task"),
        "summary": summary,
        "method": method,
        "tests": tests,
        "files": sorted(set(files)),
        "starting_commit": lock.get("starting_commit"),
        "ending_commit": commit,
        "completed_at": now_iso(),
    }
    append_event(event)
    other = "CLAUDE" if actor.lower() == "codex" else "CODEX"
    (CONTROL_DIR / f"HANDOFF_{other}.md").write_text(
        "\n".join([
            f"# Handoff to {other.title()}",
            "",
            f"- From: {actor}",
            f"- Completed: {event['completed_at']}",
            f"- Task: {event['task']}",
            f"- Summary: {summary}",
            f"- Method: {method}",
            f"- Tests: {tests}",
            f"- Commit: `{commit}`",
            "",
            "## Files",
            *[f"- `{path}`" for path in event["files"]],
            "",
            "Read GitHub/main and CURRENT_STATE.md before beginning new work.",
        ]) + "\n",
        encoding="utf-8",
    )
    LOCK_PATH.unlink()
    ACTIVE_TASK_PATH.unlink(missing_ok=True)
    update_git_history()
    update_current_state()
    return event


def initialize() -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    (CONTROL_DIR / "README.md").write_text(
        "# Tradysquid AI Control\n\n"
        "Operational history shared by the owner, Codex, and Claude. This folder "
        "contains no chat transcripts or credentials.\n\n"
        "Before editing: read CURRENT_STATE.md, CHANGELOG.jsonl, the relevant "
        "handoff, and Git status; then acquire UPDATE_LOCK.json through "
        "ai_coordination.py. Never edit while another actor holds the lock.\n",
        encoding="utf-8",
    )
    EVENTS_PATH.touch(exist_ok=True)
    for actor in ("CODEX", "CLAUDE"):
        path = CONTROL_DIR / f"HANDOFF_{actor}.md"
        if not path.exists():
            path.write_text(
                f"# Handoff to {actor.title()}\n\nNo pending handoff.\n",
                encoding="utf-8",
            )
    update_git_history()
    update_current_state()


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init")
    subcommands.add_parser("status")
    begin = subcommands.add_parser("begin")
    begin.add_argument("--actor", required=True, choices=("Codex", "Claude"))
    begin.add_argument("--task", required=True)
    begin.add_argument("--method", required=True)
    complete = subcommands.add_parser("finish")
    complete.add_argument("--actor", required=True, choices=("Codex", "Claude"))
    complete.add_argument("--summary", required=True)
    complete.add_argument("--method", required=True)
    complete.add_argument("--tests", required=True)
    complete.add_argument("--files", nargs="*", default=[])
    complete.add_argument("--commit", default="")
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "status":
        initialize()
        print(STATE_PATH.read_text(encoding="utf-8"))
    elif args.command == "begin":
        print(json.dumps(acquire(args.actor, args.task, args.method), indent=2))
    elif args.command == "finish":
        print(json.dumps(finish(
            args.actor, args.summary, args.method, args.tests,
            args.files, args.commit,
        ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
