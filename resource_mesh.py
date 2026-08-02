"""Atomic file-spool mesh shared by the production PC and one optional worker PC.

The mesh intentionally uses ordinary JSON files and atomic renames instead of a
message broker. It works on a local folder, an authenticated Windows SMB share,
or another folder synchronized between two trusted machines. The production
system keeps operating when the worker is offline; pending tasks simply remain
in the inbox until either the remote worker or the local fallback claims them.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = ROOT / "state" / "resource-mesh"
ALLOWED_KINDS = {
    "ticker-enrichment",
    "macro-refresh",
    "compute-statistics",
    "health-probe",
}


def mesh_root() -> Path:
    configured = os.environ.get("RESOURCE_MESH_ROOT", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_ROOT


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def _dirs() -> dict[str, Path]:
    root = mesh_root()
    values = {
        "root": root,
        "inbox": root / "inbox",
        "processing": root / "processing",
        "outbox": root / "outbox",
        "failed": root / "failed",
        "archive": root / "archive",
        "dedupe": root / "dedupe",
        "cache": root / "cache",
    }
    for path in values.values():
        path.mkdir(parents=True, exist_ok=True)
    return values


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _dedupe_hash(kind: str, dedupe_key: str) -> str:
    return hashlib.sha256(f"{kind}|{dedupe_key}".encode("utf-8")).hexdigest()


def submit_task(
    kind: str,
    payload: dict[str, Any],
    *,
    priority: int = 50,
    dedupe_key: str = "",
    dedupe_seconds: int = 900,
    expires_seconds: int = 86_400,
) -> dict[str, Any]:
    kind = str(kind or "").strip().casefold()
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Unsupported resource mesh task kind: {kind}")
    paths = _dirs()
    dedupe_value = dedupe_key.strip() or json.dumps(
        payload, sort_keys=True, default=str
    )
    digest = _dedupe_hash(kind, dedupe_value)
    marker = paths["dedupe"] / f"{digest}.json"
    existing = _read_json(marker)
    current = now()
    if existing:
        try:
            valid_until = datetime.fromisoformat(
                str(existing.get("valid_until") or "")
            )
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=current.tzinfo)
        except (TypeError, ValueError):
            valid_until = current - timedelta(seconds=1)
        if current < valid_until:
            return {
                "created": False,
                "task_id": str(existing.get("task_id") or ""),
                "status": str(existing.get("status") or "deduplicated"),
                "dedupe_hash": digest,
            }

    task_id = uuid.uuid4().hex
    created_ms = int(time.time() * 1000)
    normalized_priority = max(0, min(999, int(priority)))
    filename = f"P{999-normalized_priority:03d}-{created_ms}-{task_id}.json"
    task = {
        "schema_version": 1,
        "task_id": task_id,
        "kind": kind,
        "priority": normalized_priority,
        "created_at": now_iso(),
        "expires_at": (
            current + timedelta(seconds=max(60, expires_seconds))
        ).isoformat(timespec="seconds"),
        "dedupe_hash": digest,
        "payload": payload,
        "origin": {
            "host": socket.gethostname(),
            "process_id": os.getpid(),
        },
    }
    _atomic_json(paths["inbox"] / filename, task)
    _atomic_json(
        marker,
        {
            "task_id": task_id,
            "kind": kind,
            "status": "PENDING",
            "created_at": task["created_at"],
            "valid_until": (
                current + timedelta(seconds=max(5, dedupe_seconds))
            ).isoformat(timespec="seconds"),
        },
    )
    return {
        "created": True,
        "task_id": task_id,
        "status": "PENDING",
        "dedupe_hash": digest,
    }


def claim_task(worker_id: str) -> tuple[Path, dict[str, Any]] | None:
    paths = _dirs()
    for source in sorted(paths["inbox"].glob("*.json")):
        destination = paths["processing"] / f"{worker_id}-{source.name}"
        try:
            os.replace(source, destination)
        except OSError:
            continue
        task = _read_json(destination)
        if not task:
            destination.replace(paths["failed"] / destination.name)
            continue
        try:
            expires = datetime.fromisoformat(str(task.get("expires_at") or ""))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=now().tzinfo)
        except (TypeError, ValueError):
            expires = now() + timedelta(days=1)
        if now() > expires:
            finish_task(
                destination,
                task,
                worker_id=worker_id,
                status="EXPIRED",
                result={},
                error="task expired before it was claimed",
            )
            continue
        return destination, task
    return None


def finish_task(
    processing_path: Path,
    task: dict[str, Any],
    *,
    worker_id: str,
    status: str,
    result: dict[str, Any],
    error: str = "",
) -> Path:
    paths = _dirs()
    completed = {
        "schema_version": 1,
        "task_id": task.get("task_id"),
        "kind": task.get("kind"),
        "status": status,
        "created_at": task.get("created_at"),
        "completed_at": now_iso(),
        "worker": {
            "worker_id": worker_id,
            "host": socket.gethostname(),
            "process_id": os.getpid(),
        },
        "payload": task.get("payload") or {},
        "result": result,
        "error": str(error or "")[:4000],
        "dedupe_hash": task.get("dedupe_hash"),
    }
    target_dir = paths["outbox"] if status == "OK" else paths["failed"]
    target = target_dir / (
        f"{task.get('task_id')}-{str(status).casefold()}.json"
    )
    _atomic_json(target, completed)
    try:
        processing_path.unlink()
    except OSError:
        pass
    digest = str(task.get("dedupe_hash") or "")
    if digest:
        marker = paths["dedupe"] / f"{digest}.json"
        current = _read_json(marker) or {}
        current.update(status=status, completed_at=completed["completed_at"])
        _atomic_json(marker, current)
    return target


def collect_results(limit: int = 100) -> list[dict[str, Any]]:
    paths = _dirs()
    output: list[dict[str, Any]] = []
    for source in sorted(paths["outbox"].glob("*.json"))[: max(1, int(limit))]:
        claimed = paths["processing"] / f"collector-{source.name}"
        try:
            os.replace(source, claimed)
        except OSError:
            continue
        payload = _read_json(claimed)
        archive = paths["archive"] / now().strftime("%Y-%m-%d")
        archive.mkdir(parents=True, exist_ok=True)
        destination = archive / source.name
        try:
            os.replace(claimed, destination)
        except OSError:
            try:
                claimed.unlink()
            except OSError:
                pass
        if payload:
            output.append(payload)
    return output


def write_heartbeat(worker_id: str, *, role: str, detail: str = "") -> None:
    paths = _dirs()
    _atomic_json(
        paths["root"] / "worker-heartbeat.json",
        {
            "worker_id": worker_id,
            "role": role,
            "host": socket.gethostname(),
            "process_id": os.getpid(),
            "updated_at": now_iso(),
            "detail": detail[:500],
        },
    )


def read_heartbeat() -> dict[str, Any]:
    return _read_json(_dirs()["root"] / "worker-heartbeat.json") or {}


def worker_available(max_age_seconds: int = 120) -> bool:
    heartbeat = read_heartbeat()
    try:
        updated = datetime.fromisoformat(
            str(heartbeat.get("updated_at") or "")
        )
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=now().tzinfo)
    except (TypeError, ValueError):
        return False
    return now() - updated <= timedelta(seconds=max(10, max_age_seconds))


def task_counts() -> dict[str, int]:
    paths = _dirs()
    return {
        name: len(list(paths[name].glob("*.json")))
        for name in ("inbox", "processing", "outbox", "failed")
    }


def cache_path(name: str) -> Path:
    clean = "".join(
        character
        for character in str(name)
        if character.isalnum() or character in "-_."
    )
    if not clean:
        raise ValueError("cache name is empty")
    return _dirs()["cache"] / clean


def load_cache(
    name: str, *, max_age_seconds: int | None = None
) -> dict[str, Any] | None:
    path = cache_path(name)
    payload = _read_json(path)
    if payload is None or max_age_seconds is None:
        return payload
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    return payload if age <= max_age_seconds else None


def save_cache(name: str, payload: dict[str, Any]) -> Path:
    path = cache_path(name)
    _atomic_json(path, payload)
    return path


def list_failed(limit: int = 20) -> list[dict[str, Any]]:
    paths = _dirs()
    values: list[dict[str, Any]] = []
    for path in sorted(paths["failed"].glob("*.json"), reverse=True)[:limit]:
        payload = _read_json(path)
        if payload:
            values.append(payload)
    return values


__all__ = [
    "ALLOWED_KINDS",
    "cache_path",
    "claim_task",
    "collect_results",
    "finish_task",
    "list_failed",
    "load_cache",
    "mesh_root",
    "read_heartbeat",
    "save_cache",
    "submit_task",
    "task_counts",
    "worker_available",
    "write_heartbeat",
]
