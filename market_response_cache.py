"""Small cross-process SQLite cache for identical factual provider responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "state" / "market-response-cache.db"


def cache_key(path: str, params: dict[str, Any]) -> str:
    body = json.dumps([path, sorted(params.items())], separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL)")
    return db


def get(key: str) -> dict[str, Any] | None:
    db = _connect()
    try:
        row = db.execute("SELECT payload,expires_at FROM responses WHERE key=?", (key,)).fetchone()
        if row is None or float(row[1]) <= time.time():
            return None
        return json.loads(row[0])
    finally:
        db.close()


def put(key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    db = _connect()
    try:
        with db:
            db.execute("INSERT INTO responses(key,payload,expires_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at",
                       (key, json.dumps(payload, separators=(",", ":"), default=str), time.time() + ttl_seconds))
    finally:
        db.close()
