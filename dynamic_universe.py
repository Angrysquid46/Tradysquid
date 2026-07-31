"""Local dynamic universe and provider-event queue.

This module deliberately contains no brokerage order capability. Provider data
is normalized into a small SQLite queue, ranked, deduplicated, and consumed by
the local scanner.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "universe.json"
SCANNER_CONFIG_PATH = ROOT / "config" / "scanner.json"
DB_PATH = ROOT / "state" / "dynamic-universe.db"
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Symbol must contain 1-10 letters, numbers, periods, or hyphens.")
    return symbol


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scanner_config() -> dict[str, Any]:
    return load_json(SCANNER_CONFIG_PATH)


def universe_config() -> dict[str, Any]:
    return load_json(CONFIG_PATH)


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS universe (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            source TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            last_price REAL,
            average_volume REAL,
            options_available INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT
        );
        CREATE INDEX IF NOT EXISTS universe_rank
            ON universe(status, score DESC, symbol);

        CREATE TABLE IF NOT EXISTS provider_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE NOT NULL,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            received_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            payload_json TEXT NOT NULL,
            processed_at TEXT,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS provider_event_queue
            ON provider_events(status, priority DESC, available_at, id);
        """
    )
    connection.commit()
    return connection


@dataclass(frozen=True)
class Candidate:
    symbol: str
    source: str
    score: float = 0
    last_price: float | None = None
    average_volume: float | None = None
    options_available: bool = False
    reason: str = ""
    ttl_minutes: int | None = None


def upsert_candidates(
    candidates: Iterable[Candidate], connection: sqlite3.Connection | None = None
) -> int:
    owned = connection is None
    db = connection or connect()
    count = 0
    try:
        for item in candidates:
            symbol = normalize_symbol(item.symbol)
            timestamp = now_iso()
            expires_at = (
                (datetime.now().astimezone() + timedelta(minutes=item.ttl_minutes))
                .isoformat(timespec="seconds")
                if item.ttl_minutes
                else None
            )
            db.execute(
                """
                INSERT INTO universe(
                    symbol, status, source, score, last_price, average_volume,
                    options_available, reason, discovered_at, updated_at, expires_at
                ) VALUES (?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    status='ACTIVE',
                    source=excluded.source,
                    score=MAX(universe.score, excluded.score),
                    last_price=COALESCE(excluded.last_price, universe.last_price),
                    average_volume=COALESCE(excluded.average_volume, universe.average_volume),
                    options_available=MAX(universe.options_available, excluded.options_available),
                    reason=excluded.reason,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (
                    symbol,
                    item.source,
                    float(item.score),
                    item.last_price,
                    item.average_volume,
                    int(item.options_available),
                    item.reason,
                    timestamp,
                    timestamp,
                    expires_at,
                ),
            )
            count += 1
        db.commit()
        return count
    finally:
        if owned:
            db.close()


def seed_universe(connection: sqlite3.Connection | None = None) -> int:
    config = universe_config()
    return upsert_candidates(
        (
            Candidate(symbol=symbol, source="seed", score=10, reason="baseline liquid universe")
            for symbol in config.get("seed_symbols") or []
        ),
        connection,
    )


def active_symbols(
    connection: sqlite3.Connection | None = None, *, limit: int | None = None
) -> list[str]:
    owned = connection is None
    db = connection or connect()
    try:
        config = universe_config()
        excluded = {
            normalize_symbol(item) for item in config.get("exclude_symbols") or []
        }
        maximum = int(limit or config.get("max_active_symbols") or 75)
        now = now_iso()
        rows = db.execute(
            """
            SELECT symbol FROM universe
            WHERE status='ACTIVE' AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY score DESC, symbol
            LIMIT ?
            """,
            (now, maximum + len(excluded)),
        ).fetchall()
        return [row["symbol"] for row in rows if row["symbol"] not in excluded][:maximum]
    finally:
        if owned:
            db.close()


def next_scan_batch(
    batch_size: int = 12, connection: sqlite3.Connection | None = None
) -> list[str]:
    """Return a rotating slice so a large universe stays inside provider limits."""
    symbols = active_symbols(connection)
    if not symbols:
        return []
    size = max(1, min(int(batch_size), len(symbols)))
    state_path = ROOT / "state" / "universe-scan-cursor.json"
    try:
        cursor = int(json.loads(state_path.read_text(encoding="utf-8")).get("cursor", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        cursor = 0
    chosen = [symbols[(cursor + index) % len(symbols)] for index in range(size)]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"cursor": (cursor + size) % len(symbols), "updated_at": now_iso()}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return chosen


def enqueue_event(
    provider: str,
    event_type: str,
    symbol: str,
    payload: dict[str, Any],
    *,
    priority: int = 0,
    event_key: str = "",
    connection: sqlite3.Connection | None = None,
) -> bool:
    symbol = normalize_symbol(symbol)
    normalized = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    key = event_key.strip() or hashlib.sha256(
        f"{provider}|{event_type}|{symbol}|{normalized}".encode("utf-8")
    ).hexdigest()
    owned = connection is None
    db = connection or connect()
    try:
        cursor = db.execute(
            """
            INSERT OR IGNORE INTO provider_events(
                event_key, provider, event_type, symbol, priority,
                received_at, available_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key, provider, event_type, symbol, priority, now_iso(), now_iso(), normalized),
        )
        db.commit()
        return cursor.rowcount == 1
    finally:
        if owned:
            db.close()


def claim_events(
    limit: int = 25, connection: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    owned = connection is None
    db = connection or connect()
    try:
        rows = db.execute(
            """
            SELECT * FROM provider_events
            WHERE status='PENDING' AND available_at <= ?
            ORDER BY priority DESC, id
            LIMIT ?
            """,
            (now_iso(), max(1, min(limit, 100))),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            db.execute(
                f"UPDATE provider_events SET status='PROCESSING' WHERE id IN ({placeholders})",
                ids,
            )
            db.commit()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
    finally:
        if owned:
            db.close()


def complete_event(
    event_id: int, *, error: str = "", connection: sqlite3.Connection | None = None
) -> None:
    owned = connection is None
    db = connection or connect()
    try:
        db.execute(
            """
            UPDATE provider_events
            SET status=?, processed_at=?, error=?
            WHERE id=?
            """,
            ("ERROR" if error else "DONE", now_iso(), error[:1000], int(event_id)),
        )
        db.commit()
    finally:
        if owned:
            db.close()


def import_robinhood_snapshot(payload: dict[str, Any]) -> int:
    """Import read-only discovery data; order-like fields are rejected."""
    forbidden = {"order", "orders", "trade", "trades", "transfer", "buy", "sell"}
    if forbidden.intersection(str(key).lower() for key in payload):
        raise ValueError("Robinhood adapter accepts read-only market discovery data only.")
    rows = payload.get("symbols") or payload.get("watchlist") or []
    candidates = []
    for row in rows:
        if isinstance(row, str):
            candidates.append(Candidate(row, "robinhood_read_only", 30, reason="read-only discovery"))
            continue
        candidates.append(
            Candidate(
                symbol=row.get("symbol", ""),
                source="robinhood_read_only",
                score=float(row.get("score") or 30),
                last_price=row.get("last_price"),
                average_volume=row.get("average_volume"),
                options_available=bool(row.get("options_available")),
                reason="read-only discovery",
                ttl_minutes=1440,
            )
        )
    return upsert_candidates(candidates)


def initialize() -> list[str]:
    connection = connect()
    try:
        seed_universe(connection)
        return active_symbols(connection)
    finally:
        connection.close()
