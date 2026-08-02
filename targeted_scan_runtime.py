"""Debounced event-triggered options scans.

TradingView and other high-priority discovery events previously changed universe
ranking but could still wait for the next rotating 15-minute batch. This module
adds a durable targeted queue. It scans only the affected symbols, preserves
the ordinary rotation as a fallback, and yields whenever the shared Tradier
budget is too close to its safety reserve.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import market_data_runtime

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "targeted-scans.db"
STATE_PATH = ROOT / "state" / "targeted-scan-status.json"
ENABLED = os.environ.get("TARGETED_SCAN_ENABLED", "true").casefold() == "true"
MIN_PRIORITY = int(os.environ.get("TARGETED_SCAN_MIN_EVENT_PRIORITY", "75"))
COOLDOWN_SECONDS = max(
    15, int(os.environ.get("TARGETED_SCAN_COOLDOWN_SECONDS", "60"))
)
MAX_SYMBOLS_PER_RUN = max(
    1, min(4, int(os.environ.get("TARGETED_SCAN_MAX_SYMBOLS", "2")))
)
MIN_TRADIER_AVAILABLE = max(
    8, int(os.environ.get("TARGETED_SCAN_MIN_TRADIER_AVAILABLE", "18"))
)
EVENT_PROVIDERS = {
    item.strip().casefold()
    for item in os.environ.get(
        "TARGETED_SCAN_EVENT_PROVIDERS",
        "tradingview,discord_member,robinhood_mcp",
    ).split(",")
    if item.strip()
}
_INSTALLED = False


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS targeted_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            priority INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            claimed_at TEXT,
            completed_at TEXT,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS targeted_scan_queue
            ON targeted_scans(status, priority DESC, available_at, id);
        CREATE TABLE IF NOT EXISTS targeted_scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            result TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS targeted_scan_runs_symbol
            ON targeted_scan_runs(symbol, id DESC);
        """
    )
    connection.commit()
    return connection


def _write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(STATE_PATH)


def enqueue(
    symbol: str,
    *,
    provider: str,
    event_type: str,
    priority: int,
    reason: str,
) -> bool:
    symbol = str(symbol or "").strip().upper()
    if not ENABLED or not symbol:
        return False
    bucket = int(now().timestamp()) // max(COOLDOWN_SECONDS, 1)
    dedupe_key = hashlib.sha256(
        f"{symbol}|{provider}|{event_type}|{bucket}".encode("utf-8")
    ).hexdigest()
    connection = _connect()
    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO targeted_scans(
                dedupe_key, symbol, provider, event_type, priority, reason,
                created_at, available_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dedupe_key,
                symbol,
                provider[:80],
                event_type[:80],
                int(priority),
                reason[:500],
                now_iso(),
                now_iso(),
            ),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def _recently_completed(connection: sqlite3.Connection, symbol: str) -> bool:
    row = connection.execute(
        """
        SELECT completed_at FROM targeted_scan_runs
        WHERE symbol=? AND result='OK'
        ORDER BY id DESC LIMIT 1
        """,
        (symbol,),
    ).fetchone()
    if row is None:
        return False
    try:
        completed = datetime.fromisoformat(str(row["completed_at"]))
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=now().tzinfo)
    except (TypeError, ValueError):
        return False
    return now() - completed < timedelta(seconds=COOLDOWN_SECONDS)


def claim(limit: int = MAX_SYMBOLS_PER_RUN) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT * FROM targeted_scans
            WHERE status='PENDING' AND available_at <= ?
            ORDER BY priority DESC, id
            LIMIT ?
            """,
            (now_iso(), max(1, min(int(limit), 10))),
        ).fetchall()
        selected: list[sqlite3.Row] = []
        seen: set[str] = set()
        for row in rows:
            symbol = str(row["symbol"])
            if symbol in seen or _recently_completed(connection, symbol):
                connection.execute(
                    """
                    UPDATE targeted_scans
                    SET status='SKIPPED', completed_at=?
                    WHERE id=?
                    """,
                    (now_iso(), int(row["id"])),
                )
                continue
            seen.add(symbol)
            selected.append(row)
        if selected:
            ids = [int(row["id"]) for row in selected]
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"""
                UPDATE targeted_scans
                SET status='PROCESSING', claimed_at=?, attempts=attempts+1
                WHERE id IN ({placeholders})
                """,
                [now_iso(), *ids],
            )
        connection.commit()
        return [dict(row) for row in selected]
    finally:
        connection.close()


def _finish(item: dict[str, Any], *, result: str, detail: str) -> None:
    connection = _connect()
    try:
        if result == "RETRY":
            attempts = int(item.get("attempts") or 0) + 1
            delay = min(900, max(30, 30 * 2 ** min(attempts, 4)))
            available = now() + timedelta(seconds=delay)
            connection.execute(
                """
                UPDATE targeted_scans
                SET status='PENDING', available_at=?, error=?
                WHERE id=?
                """,
                (
                    available.isoformat(timespec="seconds"),
                    detail[:1000],
                    int(item["id"]),
                ),
            )
        else:
            connection.execute(
                """
                UPDATE targeted_scans
                SET status=?, completed_at=?, error=?
                WHERE id=?
                """,
                (
                    "DONE" if result == "OK" else "ERROR",
                    now_iso(),
                    detail[:1000],
                    int(item["id"]),
                ),
            )
        connection.execute(
            """
            INSERT INTO targeted_scan_runs(
                symbol, started_at, completed_at, result, detail
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                item["symbol"],
                str(item.get("claimed_at") or now_iso()),
                now_iso(),
                result,
                detail[:1000],
            ),
        )
        connection.commit()
    finally:
        connection.close()


def status() -> dict[str, Any]:
    connection = _connect()
    try:
        counts = {
            str(row["status"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM targeted_scans GROUP BY status
                """
            ).fetchall()
        }
        recent = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM targeted_scan_runs ORDER BY id DESC LIMIT 10"
            ).fetchall()
        ]
    finally:
        connection.close()
    return {
        "updated_at": now_iso(),
        "enabled": ENABLED,
        "counts": counts,
        "recent": recent,
        "tradier_budget": market_data_runtime.budget_snapshot(),
    }


def install(
    engine: Any,
    dynamic_universe: Any,
    multi_ticker_scan: Any,
    ford_scan: Any,
) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_enqueue = dynamic_universe.enqueue_event

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
        created = original_enqueue(
            provider,
            event_type,
            symbol,
            payload,
            priority=priority,
            event_key=event_key,
            connection=connection,
        )
        provider_key = str(provider or "").casefold()
        if created and (
            provider_key in EVENT_PROVIDERS or int(priority) >= MIN_PRIORITY
        ):
            enqueue(
                symbol,
                provider=provider_key or "provider-event",
                event_type=str(event_type or "event"),
                priority=int(priority),
                reason=str(
                    payload.get("reason")
                    or payload.get("message")
                    or event_type
                ),
            )
        return created

    dynamic_universe.enqueue_event = enqueue_event

    def targeted_options_scan_job(connection: sqlite3.Connection) -> str:
        if not ENABLED:
            return "disabled"
        budget = market_data_runtime.budget_snapshot()
        if int(budget.get("available") or 0) < MIN_TRADIER_AVAILABLE:
            summary = status()
            summary["last_result"] = "deferred for Tradier safety reserve"
            _write_state(summary)
            return (
                f"deferred; Tradier available {budget.get('available')}/"
                f"{budget.get('allowed')}"
            )
        items = claim(MAX_SYMBOLS_PER_RUN)
        if not items:
            summary = status()
            summary["last_result"] = "queue empty"
            _write_state(summary)
            return "queue empty"
        symbols = [str(item["symbol"]) for item in items]
        started = now_iso()
        detail = ""
        try:
            with engine.POSITION_FILE_LOCK:
                exit_code = multi_ticker_scan.main(symbols)
            if exit_code:
                raise RuntimeError(
                    "targeted multi-ticker scan returned failure"
                )
            detail = f"targeted scan completed for {', '.join(symbols)}"
            for item in items:
                item["claimed_at"] = started
                _finish(item, result="OK", detail=detail)
            engine.store_observation(
                connection,
                "targeted-options-scan",
                {
                    "symbols": symbols,
                    "events": [
                        {
                            "provider": item["provider"],
                            "event_type": item["event_type"],
                            "priority": item["priority"],
                        }
                        for item in items
                    ],
                    "completed_at": now_iso(),
                    "tradier_budget": market_data_runtime.budget_snapshot(),
                },
            )
            result = detail
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            for item in items:
                item["claimed_at"] = started
                _finish(item, result="RETRY", detail=detail)
            raise
        finally:
            summary = status()
            summary["last_result"] = detail
            _write_state(summary)
        return result

    if not any(job.name == "targeted-options-scan" for job in engine.JOBS):
        job = engine.Job(
            "targeted-options-scan",
            timedelta(seconds=15),
            targeted_options_scan_job,
            market_hours_only=True,
            background=True,
            provider_heavy=True,
            retry_interval=timedelta(seconds=30),
        )
        insert_at = next(
            (
                index + 1
                for index, existing in enumerate(engine.JOBS)
                if existing.name == "position-tracker"
            ),
            1,
        )
        engine.JOBS.insert(insert_at, job)

    engine.TARGETED_SCAN_RUNTIME = "event-triggered-targeted-scan-v1"
    _write_state(status())
    _INSTALLED = True


__all__ = ["enqueue", "install", "status"]
