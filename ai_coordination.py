"""Shared Codex/Claude update coordination backed by OneDrive."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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

# Repository-native mirror (Master Spec Section 12/13). The OneDrive files
# above remain the real cross-process exclusion lock - git can't provide
# atomic exclusive-create across two independent working trees the way a
# synced folder can. These governance/ files are a git-committed, always
# up to date snapshot of the same state, so a fresh checkout with no
# OneDrive access can still answer "what's active, what's next" from repo
# state alone.
GOVERNANCE_DIR = Path(os.environ.get("AI_GOVERNANCE_DIR", str(ROOT / "governance")))
GOV_PROJECT_STATE_PATH = GOVERNANCE_DIR / "PROJECT_STATE.json"
GOV_PHASES_PATH = GOVERNANCE_DIR / "PHASES.json"
GOV_ACTIVE_HANDOFF_PATH = GOVERNANCE_DIR / "ACTIVE_HANDOFF.json"
GOV_CHANGELOG_PATH = GOVERNANCE_DIR / "CHANGELOG.jsonl"
GOV_OWNERSHIP_PATH = GOVERNANCE_DIR / "OWNERSHIP.json"
GOV_IMMUTABLE_RULES_PATH = GOVERNANCE_DIR / "IMMUTABLE_RULES.json"

PHASE_STATUSES = {"not_started", "in_progress", "complete"}

def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
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


def _load_json_file(path: Path, problems: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        # A missing governance file is not itself a schema violation - most
        # test fixtures and partial checkouts never populate every governance
        # file, only the ones a given acquire()/checkpoint()/finish() call
        # actually writes. Schema validation only judges the shape of
        # content that is present.
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        problems.append(f"schema:{path.name}:unreadable")
        return None
    if not isinstance(value, dict):
        problems.append(f"schema:{path.name}:not_an_object")
        return None
    return value


def validate_governance_schema() -> list[str]:
    """Plain shape/type checks on the governance/ files - Phase 4 (Section 19).

    Same checks tests/unit/test_governance_phase0.py already encodes as
    one-off assertions, pulled into runtime code so a malformed file is
    caught by verify() and not only by CI. Deliberately plain dict/
    isinstance checks, not jsonschema/pydantic - nothing else in this repo
    uses either.
    """
    problems: list[str] = []

    state = _load_json_file(GOV_PROJECT_STATE_PATH, problems)
    if state is not None:
        for key, expected in (
            ("observed_head_at_write", str), ("branch", str), ("last_updated", str),
        ):
            if not isinstance(state.get(key), expected):
                problems.append(f"schema:PROJECT_STATE.json:missing_key:{key}")
        if "active_lock" not in state:
            problems.append("schema:PROJECT_STATE.json:missing_key:active_lock")
        if "current_phase" not in state:
            problems.append("schema:PROJECT_STATE.json:missing_key:current_phase")

    phases_doc = _load_json_file(GOV_PHASES_PATH, problems)
    if phases_doc is not None:
        phases = phases_doc.get("phases")
        if not isinstance(phases, list):
            problems.append("schema:PHASES.json:missing_key:phases")
        else:
            for entry in phases:
                if not isinstance(entry, dict):
                    problems.append("schema:PHASES.json:phase_not_an_object")
                    continue
                if not isinstance(entry.get("phase_number"), int):
                    problems.append("schema:PHASES.json:phase_number_not_int")
                if not isinstance(entry.get("name"), str):
                    problems.append("schema:PHASES.json:name_not_str")
                if entry.get("status") not in PHASE_STATUSES:
                    problems.append("schema:PHASES.json:status_not_in_enum")
                if not isinstance(entry.get("discovered_subphases"), list):
                    problems.append("schema:PHASES.json:discovered_subphases_not_list")

    handoff = _load_json_file(GOV_ACTIVE_HANDOFF_PATH, problems)
    if handoff is not None:
        if not isinstance(handoff.get("active"), bool):
            problems.append("schema:ACTIVE_HANDOFF.json:active_not_bool")
        elif handoff["active"]:
            for key in ("work_id", "actor", "task"):
                if not handoff.get(key):
                    problems.append(f"schema:ACTIVE_HANDOFF.json:missing_key:{key}")

    ownership = _load_json_file(GOV_OWNERSHIP_PATH, problems)
    if ownership is not None:
        classes = ownership.get("ownership_classes")
        if not isinstance(classes, list) or not classes:
            problems.append("schema:OWNERSHIP.json:missing_key:ownership_classes")
            classes = []
        entries = ownership.get("entries")
        if not isinstance(entries, list):
            problems.append("schema:OWNERSHIP.json:missing_key:entries")
        else:
            for entry in entries:
                if not isinstance(entry, dict):
                    problems.append("schema:OWNERSHIP.json:entry_not_an_object")
                    continue
                for key in ("path", "owner", "readers", "writers", "protected"):
                    if key not in entry:
                        problems.append(f"schema:OWNERSHIP.json:entry_missing_key:{key}")
                if entry.get("owner") is not None and classes and entry.get("owner") not in classes:
                    problems.append(f"schema:OWNERSHIP.json:unknown_owner:{entry.get('path')}")

    rules = _load_json_file(GOV_IMMUTABLE_RULES_PATH, problems)
    if rules is not None:
        for key in ("immutable_competition_rules", "private_competitor_boundary"):
            if not isinstance(rules.get(key), dict):
                problems.append(f"schema:IMMUTABLE_RULES.json:missing_key:{key}")

    return problems


def check_state_freshness() -> dict[str, Any]:
    """Detect governance/PROJECT_STATE.json going stale (Section 13's
    PROJECT_STATE_STALE convention, previously only prose in a notes
    field). A lock being active means a task is legitimately mid-flight -
    that is not staleness, it is normal, and must not be flagged."""
    result: dict[str, Any] = {
        "stale": False,
        "recorded_commit": None,
        "actual_commit": None,
        "reason": None,
    }
    if not GOV_PROJECT_STATE_PATH.exists():
        return result
    try:
        state = json.loads(GOV_PROJECT_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result
    try:
        actual_commit = git("rev-parse", "HEAD")
    except RuntimeError:
        return result
    recorded_commit = state.get("observed_head_at_write")
    result["recorded_commit"] = recorded_commit
    result["actual_commit"] = actual_commit
    if LOCK_PATH.exists():
        return result
    try:
        state_commit = git("log", "-1", "--format=%H", "--", "governance/PROJECT_STATE.json")
    except RuntimeError:
        state_commit = ""
    result["state_record_commit"] = state_commit
    if not state_commit or state_commit != actual_commit:
        result["stale"] = True
        result["reason"] = "PROJECT_STATE_STALE"
    return result


def load_ownership() -> dict[str, Any]:
    if not GOV_OWNERSHIP_PATH.exists():
        return {"ownership_classes": [], "entries": []}
    try:
        return json.loads(GOV_OWNERSHIP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ownership_classes": [], "entries": []}


def _ownership_entry_for(path: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = path.replace("\\", "/")
    best: dict[str, Any] | None = None
    best_length = -1
    for entry in entries:
        entry_path = str(entry.get("path") or "")
        if not entry_path:
            continue
        if entry_path.endswith("/"):
            matches = normalized == entry_path.rstrip("/") or normalized.startswith(entry_path)
        else:
            matches = normalized == entry_path
        if matches and len(entry_path) > best_length:
            best = entry
            best_length = len(entry_path)
    return best


def check_ownership(actor: str, paths: Iterable[str]) -> list[str]:
    """Section 11 write-guard: which of `paths` is `actor` not authorized to
    write, per governance/OWNERSHIP.json. A path with no matching entry is
    NOT a violation - most of the tree is intentionally unassigned until
    later phases create it (OWNERSHIP.json's own not_yet_assigned list);
    enforcement only ever applies to paths that already have an explicit,
    protected entry."""
    ownership = load_ownership()
    entries = ownership.get("entries") or []
    violations: list[str] = []
    for path in paths:
        entry = _ownership_entry_for(path, entries)
        if entry is None or not entry.get("protected"):
            continue
        writers = entry.get("writers") or []
        if actor not in writers:
            violations.append(
                f"ownership:{path}:owner={entry.get('owner')}:writers={writers}:actor={actor}"
            )
    return violations


def enforce_ownership(actor: str, paths: Iterable[str]) -> None:
    violations = check_ownership(actor, paths)
    if violations:
        raise RuntimeError(
            "Ownership write-guard rejected this finish (Section 11): "
            + "; ".join(violations)
        )


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


def append_governance_event(event: dict[str, Any]) -> None:
    GOVERNANCE_DIR.mkdir(parents=True, exist_ok=True)
    with GOV_CHANGELOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def update_project_state(phase: str | None = None, subphase: str | None = None) -> dict[str, Any]:
    """Refresh governance/PROJECT_STATE.json - the repo-native mirror of
    current commit/branch/lock, readable without OneDrive access."""
    snapshot = repository_snapshot()
    lock = None
    if LOCK_PATH.exists():
        try:
            lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            lock = None
    if phase is None or subphase is None:
        previous_phase, previous_subphase = None, None
        if GOV_PROJECT_STATE_PATH.exists():
            try:
                previous = json.loads(GOV_PROJECT_STATE_PATH.read_text(encoding="utf-8"))
                previous_phase = previous.get("current_phase")
                previous_subphase = previous.get("current_subphase")
            except (json.JSONDecodeError, OSError):
                pass
        phase = phase if phase is not None else previous_phase
        subphase = subphase if subphase is not None else previous_subphase
    state = {
        "last_updated": now_iso(),
        "branch": snapshot["branch"],
        "observed_head_at_write": snapshot["commit"],
        "commit_subject": snapshot["commit_subject"],
        "current_phase": phase,
        "current_subphase": subphase,
        "active_lock": (
            None if lock is None else {
                "actor": lock.get("actor"),
                "task": lock.get("task"),
                "work_id": lock.get("work_id"),
                "started_at": lock.get("started_at"),
            }
        ),
        "notes": (
            "Exact synchronization is derived from Git: when no lock is active, "
            "the newest commit containing governance/PROJECT_STATE.json must equal HEAD. "
            "observed_head_at_write is provenance, not a self-referential equality claim."
        ),
        "synchronization_semantics": "state_record_commit_equals_head_when_lock_clear",
    }
    atomic_json(GOV_PROJECT_STATE_PATH, state)
    return state


def update_active_handoff(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Refresh governance/ACTIVE_HANDOFF.json - the Section 12 step 9
    STARTED-record fields, or an explicit cleared shape when no task is
    active."""
    if payload is None:
        record: dict[str, Any] = {"active": False, "work_id": None, "cleared_at": now_iso()}
    else:
        record = {"active": True, **payload}
    atomic_json(GOV_ACTIVE_HANDOFF_PATH, record)
    return record


def acquire(actor: str, task: str, method: str, **handoff_fields: Any) -> dict[str, Any]:
    preflight = verify()
    if not preflight["lock_available"]:
        existing = json.dumps(preflight.get("lock"), indent=2)
        raise RuntimeError(
            "Another update is active. Do not modify files. Lock: " + existing
        )
    payload = {
        "work_id": str(uuid.uuid4()),
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

    phase = handoff_fields.get("phase")
    handoff_record = {
        **payload,
        "owner_request": handoff_fields.get("reason", ""),
        "before_state": handoff_fields.get("before_state", ""),
        "reason": handoff_fields.get("reason", ""),
        "intended_scope": handoff_fields.get("intended_scope", ""),
        "expected_effects": handoff_fields.get("expected_effects", ""),
        "required_tests": handoff_fields.get("required_tests", ""),
        "risks": handoff_fields.get("risks", ""),
        "next_safe_action_if_interrupted": handoff_fields.get("next_safe_action", ""),
        "phase": phase,
    }
    update_active_handoff(handoff_record)
    update_project_state(phase=phase)
    append_governance_event({"event": "BEGIN", **payload, "phase": phase})
    return payload


def checkpoint(actor: str, summary: str, next_safe_action: str) -> dict[str, Any]:
    if not LOCK_PATH.exists() or not ACTIVE_TASK_PATH.exists():
        raise RuntimeError("No active coordinated task exists.")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    active = json.loads(ACTIVE_TASK_PATH.read_text(encoding="utf-8"))
    if lock.get("actor", "").lower() != actor.lower():
        raise RuntimeError(
            f"Lock belongs to {lock.get('actor')}; {actor} cannot checkpoint it."
        )
    if not lock.get("work_id"):
        work_id = str(uuid.uuid4())
        lock["work_id"] = work_id
        active["work_id"] = work_id
        atomic_json(LOCK_PATH, lock)
    active.update({
        "last_checkpoint_at": now_iso(),
        "last_successful_action": summary,
        "next_safe_action": next_safe_action,
    })
    atomic_json(ACTIVE_TASK_PATH, active)
    event = {
        "event": "CHECKPOINT",
        "actor": actor,
        "work_id": lock.get("work_id"),
        "task": lock.get("task"),
        "summary": summary,
        "next_safe_action": next_safe_action,
        "checkpointed_at": active["last_checkpoint_at"],
    }
    append_event(event)

    existing_handoff: dict[str, Any] = {}
    if GOV_ACTIVE_HANDOFF_PATH.exists():
        try:
            existing_handoff = json.loads(GOV_ACTIVE_HANDOFF_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_handoff = {}
    handoff_record = {
        **existing_handoff,
        **active,
        "next_safe_action_if_interrupted": next_safe_action,
    }
    update_active_handoff(handoff_record)
    update_project_state(phase=existing_handoff.get("phase"))
    append_governance_event(event)
    return event


def process_is_running(process_id: int) -> bool:
    """Return whether a recorded coordination owner process is still alive."""
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def takeover(from_actor: str, to_actor: str, reason: str) -> dict[str, Any]:
    """Transfer an interrupted task without discarding its work or identity."""
    if not LOCK_PATH.exists() or not ACTIVE_TASK_PATH.exists():
        raise RuntimeError("No active coordinated task exists to take over.")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    active = json.loads(ACTIVE_TASK_PATH.read_text(encoding="utf-8"))
    if lock.get("actor", "").lower() != from_actor.lower():
        raise RuntimeError(f"Lock belongs to {lock.get('actor')}, not {from_actor}.")
    process_id = int(lock.get("process_id") or 0)
    if process_is_running(process_id):
        raise RuntimeError(
            f"Recorded {from_actor} process {process_id} is still running; refusing takeover."
        )
    transferred_at = now_iso()
    previous_process_id = process_id
    for record in (lock, active):
        record["actor"] = to_actor
        record["process_id"] = os.getpid()
        record["taken_over_from"] = from_actor
        record["previous_process_id"] = previous_process_id
        record["takeover_reason"] = reason
        record["taken_over_at"] = transferred_at
    atomic_json(LOCK_PATH, lock)
    atomic_json(ACTIVE_TASK_PATH, active)
    event = {
        "event": "TAKEOVER",
        "actor": to_actor,
        "from_actor": from_actor,
        "work_id": lock.get("work_id"),
        "task": lock.get("task"),
        "previous_process_id": previous_process_id,
        "reason": reason,
        "taken_over_at": transferred_at,
    }
    append_event(event)
    append_governance_event(event)
    existing_handoff = json.loads(GOV_ACTIVE_HANDOFF_PATH.read_text(encoding="utf-8"))
    update_active_handoff({**existing_handoff, **active})
    update_current_state()
    update_project_state(phase=existing_handoff.get("phase"))
    return event


def verify() -> dict[str, Any]:
    problems: list[str] = []
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    for path in (STATE_PATH, EVENTS_PATH):
        if not path.exists():
            problems.append(f"missing:{path.name}")
    lock = None
    active = None
    for path, label in ((LOCK_PATH, "lock"), (ACTIVE_TASK_PATH, "active_task")):
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                problems.append(f"unreadable:{path.name}")
                continue
            if label == "lock":
                lock = value
            else:
                active = value
    if (lock is None) != (active is None):
        problems.append("lock_active_task_mismatch")
    if lock and active:
        for field in ("actor", "task", "work_id", "starting_commit"):
            if lock.get(field) != active.get(field):
                problems.append(f"lock_active_mismatch:{field}")
        if not lock.get("work_id"):
            problems.append("missing:work_id")
    problems.extend(validate_governance_schema())
    freshness = check_state_freshness()
    if freshness["stale"]:
        problems.append("state_stale:commit_mismatch")
    result = {
        "status": (
            "BLOCKED" if problems else
            "READY_ACTIVE" if lock else
            "READY_CLEAR"
        ),
        "lock_available": not problems and lock is None,
        "control_dir": str(CONTROL_DIR),
        "repository": str(ROOT),
        "lock": lock,
        "problems": problems,
    }
    if problems:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


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
    enforce_ownership(actor, files)
    commit = git("rev-parse", commit or "HEAD")
    event = {
        "event": "COMPLETE",
        "actor": actor,
        "work_id": lock.get("work_id"),
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

    update_active_handoff(None)
    update_project_state()
    append_governance_event(event)
    return event


def mark_phase_status(
    phase_number: int,
    status: str,
    completion_evidence: str | None = None,
) -> dict[str, Any]:
    """Atomic, validated governance/PHASES.json status transition (Section
    19). Every phase so far has been hand-edited directly; this is the one
    governance file that update_project_state()/update_active_handoff()
    don't already write through atomic_json(). Enforces the same invariants
    tests/unit/test_governance_phase0.py already checks: status is a known
    value, started phases stay a contiguous prefix from 0, and a phase
    cannot be marked complete without non-empty completion_evidence."""
    if status not in PHASE_STATUSES:
        raise ValueError(f"Unknown phase status: {status!r}")
    if status == "complete" and not (completion_evidence or "").strip():
        raise ValueError("completion_evidence is required to mark a phase complete")
    if not GOV_PHASES_PATH.exists():
        raise RuntimeError(f"{GOV_PHASES_PATH} does not exist")
    data = json.loads(GOV_PHASES_PATH.read_text(encoding="utf-8"))
    phases = data.get("phases") or []
    target = next((p for p in phases if p.get("phase_number") == phase_number), None)
    if target is None:
        raise ValueError(f"No phase {phase_number} in {GOV_PHASES_PATH}")

    projected = [
        (status if p.get("phase_number") == phase_number else p.get("status"))
        for p in phases
    ]
    started = [
        p["phase_number"] for p, s in zip(phases, projected) if s != "not_started"
    ]
    if started != list(range(len(started))):
        raise ValueError(
            f"Marking phase {phase_number} as {status!r} would break the "
            f"contiguous-prefix invariant: started phases would be {started}"
        )

    target["status"] = status
    if completion_evidence is not None:
        target["completion_evidence"] = completion_evidence
    atomic_json(GOV_PHASES_PATH, data)
    return target


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
    subcommands.add_parser("verify")
    transfer = subcommands.add_parser("takeover")
    transfer.add_argument("--from-actor", required=True, choices=("Codex", "Claude"))
    transfer.add_argument("--to-actor", required=True, choices=("Codex", "Claude"))
    transfer.add_argument("--reason", required=True)
    begin = subcommands.add_parser("begin")
    begin.add_argument("--actor", required=True, choices=("Codex", "Claude"))
    begin.add_argument("--task", required=True)
    begin.add_argument("--method", required=True)
    begin.add_argument("--phase", default=None, help="Section 19 phase this task belongs to, e.g. 'Phase 0'")
    begin.add_argument("--reason", default="")
    begin.add_argument("--before-state", default="")
    begin.add_argument("--intended-scope", default="")
    begin.add_argument("--expected-effects", default="")
    begin.add_argument("--required-tests", default="")
    begin.add_argument("--risks", default="")
    begin.add_argument("--next-safe-action", default="")
    complete = subcommands.add_parser("finish")
    progress = subcommands.add_parser("checkpoint")
    progress.add_argument("--actor", required=True, choices=("Codex", "Claude"))
    progress.add_argument("--summary", required=True)
    progress.add_argument("--next-safe-action", required=True)
    complete.add_argument("--actor", required=True, choices=("Codex", "Claude"))
    complete.add_argument("--summary", required=True)
    complete.add_argument("--method", required=True)
    complete.add_argument("--tests", required=True)
    complete.add_argument("--files", nargs="*", default=[])
    complete.add_argument("--commit", default="")
    ownership_check = subcommands.add_parser("check-ownership")
    ownership_check.add_argument(
        "--actor", required=True, choices=("Codex", "Claude", "Owner")
    )
    ownership_check.add_argument("--paths", nargs="*", default=[])
    phase_status = subcommands.add_parser("set-phase-status")
    phase_status.add_argument("--phase-number", required=True, type=int)
    phase_status.add_argument("--status", required=True, choices=sorted(PHASE_STATUSES))
    phase_status.add_argument("--completion-evidence", default=None)
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "status":
        initialize()
        print(STATE_PATH.read_text(encoding="utf-8"))
    elif args.command == "begin":
        print(json.dumps(acquire(
            args.actor, args.task, args.method,
            phase=args.phase,
            reason=args.reason,
            before_state=args.before_state,
            intended_scope=args.intended_scope,
            expected_effects=args.expected_effects,
            required_tests=args.required_tests,
            risks=args.risks,
            next_safe_action=args.next_safe_action,
        ), indent=2))
    elif args.command == "checkpoint":
        print(json.dumps(checkpoint(
            args.actor, args.summary, args.next_safe_action,
        ), indent=2))
    elif args.command == "verify":
        print(json.dumps(verify(), indent=2))
    elif args.command == "takeover":
        print(json.dumps(takeover(
            args.from_actor, args.to_actor, args.reason,
        ), indent=2))
    elif args.command == "finish":
        print(json.dumps(finish(
            args.actor, args.summary, args.method, args.tests,
            args.files, args.commit,
        ), indent=2))
    elif args.command == "check-ownership":
        violations = check_ownership(args.actor, args.paths)
        print(json.dumps({"actor": args.actor, "paths": args.paths, "violations": violations}, indent=2))
        if violations:
            return 1
    elif args.command == "set-phase-status":
        print(json.dumps(mark_phase_status(
            args.phase_number, args.status, args.completion_evidence,
        ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
