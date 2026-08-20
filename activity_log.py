"""One append-only file recording what this system actually did.

Owner: "I want it off of discord in a file so you can see it, and I want
you to log all activity ... because I want you to know something before I
have to hunt it down."

The immediate reason is 2026-08-20 12:00:49, when twelve positions opened
across twelve strategies on one contract, every row stamped "Manually
forced via /force-all-strategies". The owner did not run it. Discord
signature verification had passed, so the request was genuinely signed -
and a scan of all 123 channels found ZERO interactions that day. There was
nothing left to read: the only record of the invocation was the trades it
produced.

That is what this fixes. Every interaction is recorded BEFORE it is
verified or acted on, so a burst can be traced to an interaction id, a
user and a source address even when Discord shows nothing.

## Rules this file follows

- **Never raises.** Logging that can break the caller is worse than no
  logging. Every write is wrapped; a failure prints to stderr and returns.
- **Append-only JSONL**, one event per line, so a partial write costs one
  line rather than the file.
- **No secrets.** Tokens, signatures and authorization headers are
  recorded as present/absent, never by value. The bot token is in this
  process's environment and must not end up in a file.
- **Rotates by size**, so a runaway loop cannot fill the disk.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_PATH = Path("state/activity.jsonl")
MAX_BYTES = 20 * 1024 * 1024        # ~20MB, then rotate once
KEEP_ROTATIONS = 3

_LOCK = threading.Lock()

# Anything whose value must never be written, only its presence.
_REDACT = ("token", "secret", "signature", "authorization", "password",
           "api_key", "apikey", "public_key")


def _safe(key: str, value: Any) -> Any:
    if any(marker in key.lower() for marker in _REDACT):
        return "<present>" if value else "<absent>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: _safe(k, v) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [_safe(key, v) for v in list(value)[:40]]
    return str(value)[:500]


def _rotate_if_needed() -> None:
    try:
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size < MAX_BYTES:
            return
        for index in range(KEEP_ROTATIONS - 1, 0, -1):
            older = LOG_PATH.with_suffix(f".jsonl.{index}")
            newer = LOG_PATH.with_suffix(f".jsonl.{index + 1}")
            if older.exists():
                older.replace(newer)
        LOG_PATH.replace(LOG_PATH.with_suffix(".jsonl.1"))
    except OSError:
        pass


def record(event: str, **fields: Any) -> None:
    """Append one event. Never raises, whatever happens."""
    try:
        entry = {
            "at": datetime.now(timezone.utc).astimezone().isoformat(),
            "event": event,
            "pid": os.getpid(),
        }
        entry.update({key: _safe(key, value) for key, value in fields.items()})
        line = json.dumps(entry, default=str)
        with _LOCK:
            _rotate_if_needed()
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception as exc:                      # logging must never break a caller
        print(f"activity_log failed for {event}: {type(exc).__name__}: {exc}",
              file=sys.stderr)


def read(limit: int = 200, event: str | None = None) -> list[dict[str, Any]]:
    """Most recent events, newest last. For reading the file back."""
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if event and entry.get("event") != event:
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return list(reversed(out))
