"""Durable, local-first trade lifecycle intelligence and synchronization state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "trade-intelligence.db"
LIBRARY_PATH = ROOT / "learning_center" / "COMPREHENSIVE_TRADING_LIBRARY.md"
SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def learning_version() -> str:
    try:
        return digest_bytes(LIBRARY_PATH.read_bytes())[:12]
    except OSError:
        return "unavailable"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS lifecycle_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            event_kind TEXT NOT NULL,
            event_key TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            learning_version TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(trade_id, event_kind, event_key)
        );
        CREATE INDEX IF NOT EXISTS lifecycle_trade_time
            ON lifecycle_events(trade_id, observed_at);

        CREATE TABLE IF NOT EXISTS chart_snapshots (
            trade_id TEXT NOT NULL,
            event_key TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            source_timestamp TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            PRIMARY KEY(trade_id, event_key)
        );

        CREATE TABLE IF NOT EXISTS research_sources (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            published_at TEXT NOT NULL,
            ticker TEXT NOT NULL,
            play_style TEXT NOT NULL,
            claims_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            confidence TEXT NOT NULL,
            quality TEXT NOT NULL,
            learning_concepts_json TEXT NOT NULL,
            usage_terms TEXT NOT NULL,
            used_in_trade_id TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_acknowledgements (
            trade_id TEXT NOT NULL,
            consumer TEXT NOT NULL,
            trade_version TEXT NOT NULL,
            acknowledged_at TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            PRIMARY KEY(trade_id, consumer)
        );

        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    db.execute(
        "INSERT INTO metadata(key,value,updated_at) VALUES('schema_version',?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
        (str(SCHEMA_VERSION), now_iso()),
    )
    db.commit()
    return db


@contextmanager
def database():
    db = connect()
    try:
        yield db
        db.commit()
    finally:
        db.close()


def canonical_payload(row: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "trade_id": row.get("trade_id"),
        "ticker": row.get("ticker"),
        "play_type": row.get("play_type"),
        "direction": row.get("call_or_put"),
        "outcome": row.get("outcome"),
        "signal": row.get("last_signal"),
        "mark": row.get("last_mark"),
        "pl_dollars": row.get("current_pl_dollars") or row.get("realized_pl_dollars"),
        "pl_pct": row.get("current_pl_pct") or row.get("pct_gain_loss"),
        "thesis": row.get("thesis"),
        "confirmation": row.get("entry_confirmation"),
        "invalidation": row.get("invalidation"),
        "risk_plan": row.get("risk_plan"),
        "evidence_limitations": row.get("evidence_limitations"),
    }
    payload.update(extra or {})
    return payload


def trade_version(row: dict[str, Any]) -> str:
    """Stable version shared by every consumer of one canonical trade."""
    encoded = json.dumps(canonical_payload(row), sort_keys=True, separators=(",", ":"), default=str)
    return digest_bytes(encoded.encode("utf-8"))[:16]


def record_event(
    row: dict[str, Any], event_kind: str, event_key: str, *,
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> bool:
    if not str(row.get("trade_id") or "").strip():
        return False
    payload = canonical_payload(row, extra)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    with database() as db:
        cursor = db.execute(
            "INSERT OR IGNORE INTO lifecycle_events"
            "(trade_id,event_kind,event_key,observed_at,learning_version,evidence_hash,payload_json) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                str(row.get("trade_id") or ""), event_kind, event_key,
                observed_at or now_iso(), str(row.get("learning_version") or learning_version()),
                digest_bytes(encoded.encode("utf-8")), encoded,
            ),
        )
        return cursor.rowcount > 0


def register_snapshot(
    row: dict[str, Any], event_key: str, path: Path, *,
    source_timestamp: str, timeframe: str = "5m/1d/1w/1mo",
) -> bool:
    content_hash = digest_bytes(path.read_bytes())
    trade_id = str(row.get("trade_id") or "")
    with database() as db:
        previous = db.execute(
            "SELECT content_hash FROM chart_snapshots WHERE trade_id=? ORDER BY observed_at DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
        if previous and str(previous["content_hash"]) == content_hash:
            return False
        db.execute(
            "INSERT OR REPLACE INTO chart_snapshots"
            "(trade_id,event_key,observed_at,source_timestamp,timeframe,content_hash,path) "
            "VALUES(?,?,?,?,?,?,?)",
            (trade_id, event_key, now_iso(), source_timestamp, timeframe, content_hash, str(path)),
        )
    return True


def forget_snapshot(trade_id: str, event_key: str) -> None:
    """Make a failed publication retryable without losing the local image."""
    with database() as db:
        db.execute(
            "DELETE FROM chart_snapshots WHERE trade_id=? AND event_key=?",
            (trade_id, event_key),
        )


def store_research_source(item: dict[str, Any]) -> str:
    stable = "|".join(str(item.get(key) or "") for key in ("source_url", "published_at", "ticker", "claim"))
    source_id = digest_bytes(stable.encode("utf-8"))
    with database() as db:
        db.execute(
            """INSERT OR IGNORE INTO research_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                source_id, str(item.get("source_name") or "Unknown"), str(item.get("source_url") or ""),
                str(item.get("retrieved_at") or now_iso()), str(item.get("published_at") or ""),
                str(item.get("ticker") or "").upper(), str(item.get("play_style") or ""),
                json.dumps(item.get("claims") or [item.get("claim") or ""]),
                json.dumps(item.get("evidence") or []), str(item.get("confidence") or "UNREVIEWED"),
                str(item.get("quality") or "UNREVIEWED"), json.dumps(item.get("learning_concepts") or []),
                str(item.get("usage_terms") or "Verify source terms before reuse."),
                str(item.get("used_in_trade_id") or ""), str(item.get("status") or "REVIEW"),
            ),
        )
    return source_id


def acknowledge(trade_id: str, consumer: str, trade_version: str, status: str = "OK", detail: str = "") -> None:
    with database() as db:
        db.execute(
            "INSERT INTO sync_acknowledgements VALUES(?,?,?,?,?,?) ON CONFLICT(trade_id,consumer) DO UPDATE SET "
            "trade_version=excluded.trade_version,acknowledged_at=excluded.acknowledged_at,status=excluded.status,detail=excluded.detail",
            (trade_id, consumer, trade_version, now_iso(), status, detail),
        )


def acknowledge_many(rows: list[dict[str, Any]], consumers: tuple[str, ...]) -> int:
    """Commit a completed reporting fan-out in one durable transaction."""
    values = []
    timestamp = now_iso()
    for row in rows:
        trade_id = str(row.get("trade_id") or "")
        if not trade_id:
            continue
        version = trade_version(row)
        values.extend((trade_id, consumer, version, timestamp, "OK", "") for consumer in consumers)
    with database() as db:
        db.executemany(
            "INSERT INTO sync_acknowledgements VALUES(?,?,?,?,?,?) ON CONFLICT(trade_id,consumer) DO UPDATE SET "
            "trade_version=excluded.trade_version,acknowledged_at=excluded.acknowledged_at,status=excluded.status,detail=excluded.detail",
            values,
        )
    return len(values)


def needs_sync(row: dict[str, Any], consumer: str) -> bool:
    trade_id = str(row.get("trade_id") or "")
    if not trade_id:
        return False
    with database() as db:
        existing = db.execute(
            "SELECT trade_version,status FROM sync_acknowledgements WHERE trade_id=? AND consumer=?",
            (trade_id, consumer),
        ).fetchone()
    return not existing or existing["status"] != "OK" or existing["trade_version"] != trade_version(row)


def pending_rows(rows: list[dict[str, Any]], consumers: tuple[str, ...]) -> list[dict[str, Any]]:
    if not rows or not consumers:
        return []
    trade_ids = [str(row.get("trade_id") or "") for row in rows if row.get("trade_id")]
    if not trade_ids:
        return []
    placeholders = ",".join("?" for _ in trade_ids)
    consumer_placeholders = ",".join("?" for _ in consumers)
    with database() as db:
        existing = db.execute(
            f"SELECT trade_id,consumer,trade_version,status FROM sync_acknowledgements "
            f"WHERE trade_id IN ({placeholders}) AND consumer IN ({consumer_placeholders})",
            (*trade_ids, *consumers),
        ).fetchall()
    lookup = {(row["trade_id"], row["consumer"]): row for row in existing}
    pending = []
    for row in rows:
        trade_id = str(row.get("trade_id") or "")
        version = trade_version(row)
        if any(
            (record := lookup.get((trade_id, consumer))) is None
            or record["status"] != "OK"
            or record["trade_version"] != version
            for consumer in consumers
        ):
            pending.append(row)
    return pending


def score_research_queue(limit: int = 250) -> dict[str, int]:
    """Score stored provenance separately from network collection."""
    counts = {"ready": 0, "needs_source": 0}
    with database() as db:
        rows = db.execute(
            "SELECT source_id,confidence,quality,source_url FROM research_sources WHERE status='REVIEW' LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            primary = row["confidence"] == "PRIMARY-SOURCE"
            has_url = str(row["source_url"] or "").startswith(("http://", "https://"))
            status = "READY" if primary and has_url else "NEEDS-ORIGINAL-SOURCE"
            db.execute("UPDATE research_sources SET status=? WHERE source_id=?", (status, row["source_id"]))
            counts["ready" if status == "READY" else "needs_source"] += 1
    return counts


def apply_retention(*, temporary_age_seconds: int = 86400) -> dict[str, int]:
    """Remove only failed temporary artifacts and stale DB pointers; preserve evidence."""
    removed_temporary = 0
    now = datetime.now().timestamp()
    snapshot_root = ROOT / "docs" / "trade-snapshots"
    for path in snapshot_root.glob("*.tmp") if snapshot_root.exists() else []:
        try:
            if now - path.stat().st_mtime >= temporary_age_seconds:
                path.unlink()
                removed_temporary += 1
        except OSError:
            continue
    removed_missing = 0
    with database() as db:
        rows = db.execute("SELECT trade_id,event_key,path FROM chart_snapshots").fetchall()
        for row in rows:
            if not Path(str(row["path"])).exists():
                db.execute(
                    "DELETE FROM chart_snapshots WHERE trade_id=? AND event_key=?",
                    (row["trade_id"], row["event_key"]),
                )
                removed_missing += 1
        db.execute(
            "INSERT INTO metadata(key,value,updated_at) VALUES('retention_policy',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            ("preserve canonical entry/material-HOLD/exit evidence; remove failed temp files and stale pointers only", now_iso()),
        )
    return {"temporary_files_removed": removed_temporary, "missing_pointers_removed": removed_missing}


def health() -> dict[str, Any]:
    with database() as db:
        research_ready = db.execute(
            "SELECT COUNT(*) FROM research_sources WHERE status='READY'"
        ).fetchone()[0]
        research_needs_source = db.execute(
            "SELECT COUNT(*) FROM research_sources WHERE status='NEEDS-ORIGINAL-SOURCE'"
        ).fetchone()[0]
        return {
            "schema_version": SCHEMA_VERSION,
            "learning_version": learning_version(),
            "lifecycle_events": db.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0],
            "snapshots": db.execute("SELECT COUNT(*) FROM chart_snapshots").fetchone()[0],
            "research_sources": db.execute("SELECT COUNT(*) FROM research_sources").fetchone()[0],
            "pending_research": db.execute(
                "SELECT COUNT(*) FROM research_sources WHERE status NOT IN ('USED','DISMISSED')"
            ).fetchone()[0],
            "research_ready": research_ready,
            "research_needs_original_source": research_needs_source,
            "failed_syncs": db.execute("SELECT COUNT(*) FROM sync_acknowledgements WHERE status!='OK'").fetchone()[0],
        }
