"""Provider-event queue for this SPY-exclusive system.

This module used to also track a growable "universe" of tickers to scan
beyond SPY (candidate discovery/scoring, member/owner ticker-add commands,
Robinhood-scan ingestion, a rotating multi-ticker scan batch) - all of that
was removed per explicit owner direction: this system trades SPY
exclusively, and that capability existed only to expand scanning beyond it.
What remains is purely the provider-event queue, still legitimately used to
route TradingView webhook alerts to a visible Discord card (see
local_information_engine.py's provider_event_job / publish_tradingview_signal)
- an unrelated concern from "which tickers get scanned."

This module deliberately contains no brokerage order capability.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCANNER_CONFIG_PATH = ROOT / "config" / "scanner.json"
DB_PATH = ROOT / "state" / "dynamic-universe.db"
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")

# The only ticker this system trades. active_symbols()/initialize()/
# next_scan_batch() below all resolve to exactly this - kept as functions
# (not inlined at every call site) so the several jobs that loop
# "for ticker in dynamic_universe.active_symbols()" keep working unchanged,
# now as a single-ticker loop instead of a rotating multi-ticker one.
FIXED_TICKER = "SPY"


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


def active_symbols(*_args: Any, **_kwargs: Any) -> list[str]:
    return [FIXED_TICKER]


def initialize() -> list[str]:
    return [FIXED_TICKER]


def next_scan_batch(*_args: Any, **_kwargs: Any) -> list[str]:
    return [FIXED_TICKER]


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
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


def recent_tradingview_signal(
    symbol: str, max_age_seconds: int, connection: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Read-only lookup for the most recent TradingView alert for `symbol`
    received within the last `max_age_seconds`, used to gate a live trade
    entry (see spy_scanner.spy_0dte_tradingview_signal). Deliberately does
    NOT claim/consume the row via claim_events()/complete_event() - the
    existing provider-event-queue job still owns that lifecycle for posting
    the Discord research card, and this needs to read the same row without
    racing or stealing it from that consumer."""
    symbol = normalize_symbol(symbol)
    cutoff = (datetime.now().astimezone() - timedelta(seconds=max(0, max_age_seconds))).isoformat(
        timespec="seconds"
    )
    owned = connection is None
    db = connection or connect()
    try:
        row = db.execute(
            """
            SELECT * FROM provider_events
            WHERE provider='tradingview' AND symbol=? AND received_at >= ?
            ORDER BY id DESC LIMIT 1
            """,
            (symbol, cutoff),
        ).fetchone()
        return dict(row) if row else None
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
