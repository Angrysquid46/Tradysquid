"""Phase 13: AXIOM's own scheduler - same Job/due()/single-instance-lock
*shape* as local_information_engine.py's proven pattern, but a fully
separate implementation with its own state store and its own port. Not
importable from local_information_engine.py, and nothing here imports it
- no shared scheduler module exists anywhere in this repo (confirmed by
search before writing this), so each bot needs its own.
"""

from __future__ import annotations

import os
import socket
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import market_data

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "state" / "axiom.db"

# Not 8765 (local_information_engine.py), 8081 (discord_command_bot.py), or
# 8876 (tradysquid_supervisor.py) - AXIOM's own single-instance guard.
LOCK_HOST = "127.0.0.1"
LOCK_PORT = int(os.environ.get("AXIOM_LOCK_PORT", "8879"))

POLL_SECONDS = 5


@dataclass
class Job:
    name: str
    interval: timedelta
    callback: Callable[[sqlite3.Connection], str]
    market_hours_only: bool = False
    retry_interval: timedelta | None = None


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS engine_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    return connection


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO engine_state(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, _iso_now()),
    )
    connection.commit()


def get_state(connection: sqlite3.Connection, key: str, default: str = "") -> str:
    row = connection.execute("SELECT value FROM engine_state WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def due(connection: sqlite3.Connection, job: Job, now: datetime) -> bool:
    interval = job.interval
    if job.retry_interval and get_state(connection, f"job-error:{job.name}") == "1":
        interval = job.retry_interval
    last = get_state(connection, f"job:{job.name}")
    if last:
        try:
            if now - datetime.fromisoformat(last) < interval:
                return False
        except ValueError:
            pass
    if job.market_hours_only:
        market_open, _ = market_data.market_is_open_now()
        return market_open
    return True


def run_job(connection: sqlite3.Connection, job: Job) -> str:
    now = _iso_now()
    try:
        detail = job.callback(connection)
        set_state(connection, f"job:{job.name}", now)
        set_state(connection, f"job-error:{job.name}", "0")
        return detail
    except Exception as exc:  # noqa: BLE001 - a job failure must not kill the loop
        set_state(connection, f"job:{job.name}", now)
        set_state(connection, f"job-error:{job.name}", "1")
        return f"ERROR: {exc}"


def acquire_instance_lock() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        listener.bind((LOCK_HOST, LOCK_PORT))
        listener.listen(8)
        listener.setblocking(False)
    except OSError as exc:
        listener.close()
        raise RuntimeError("AXIOM is already running.") from exc
    return listener
