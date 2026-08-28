"""Phase 9: Discord surface manifest and health tracking (Master Spec
Section 14). Every dynamic Discord surface gets an explicit declaration
(owner, purpose, producer, publisher, update cadence) plus an event
history this module derives a health state from - genuinely greenfield,
nothing like this existed before this phase.

Health states are Section 14's exact eight names. Six are derived purely
from timing (HEALTHY/QUIET_VALID/NO_DATA_EXPECTED/STALE/PRODUCER_OFFLINE/
PUBLISH_FAILED) - enough data already exists to compute those. The other
two (DESYNCHRONIZED/MISCONFIGURED) require comparing declared state
against what is actually live in Discord, which needs a real channel to
check against - not built this phase (see the Phase 9 plan's "explicitly
not doing"). set_surface_status can still record either if some other
process determines one applies; compute_health just never derives them
on its own yet.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "discord_surfaces.db"

HEALTHY = "HEALTHY"
QUIET_VALID = "QUIET_VALID"
NO_DATA_EXPECTED = "NO_DATA_EXPECTED"
STALE = "STALE"
PRODUCER_OFFLINE = "PRODUCER_OFFLINE"
PUBLISH_FAILED = "PUBLISH_FAILED"
DESYNCHRONIZED = "DESYNCHRONIZED"
MISCONFIGURED = "MISCONFIGURED"

HEALTH_STATES = (
    HEALTHY, QUIET_VALID, NO_DATA_EXPECTED, STALE,
    PRODUCER_OFFLINE, PUBLISH_FAILED, DESYNCHRONIZED, MISCONFIGURED,
)

UPDATE_MODE_PERIODIC = "PERIODIC"
UPDATE_MODE_EVENT_DRIVEN = "EVENT_DRIVEN"
UPDATE_MODES = (UPDATE_MODE_PERIODIC, UPDATE_MODE_EVENT_DRIVEN)

EVENT_TYPES = ("EVENT", "UPDATE", "PUBLISH", "ERROR")

SURFACE_STATUSES = ("UPDATED", "VERIFIED_UNAFFECTED", "RETIRED", DESYNCHRONIZED, MISCONFIGURED)

# The complete dynamic competition presentation inventory.  Operational
# channels that contain ordinary stream messages are not singleton/dynamic
# surfaces.  Every competition card has one stable owner and producer here.
CANONICAL_COMPETITION_SURFACES: tuple[dict[str, object], ...] = ()


# Per-bot RIPTIDE/BLACKTIDE dashboard surfaces (rivalry_presentation.
# publish_bot_surfaces) - same registration requirement as
# CANONICAL_COMPETITION_SURFACES above (record_surface_event() raises on
# an unregistered surface_id), generated rather than hand-duplicated since
# both bots' surface sets are identical in shape. AXIOM (Claude's
# competitor) permanently removed 2026-08-27 (owner directive) - dropped
# from this generator so reconcile_canonical_bot_surfaces below retires
# its surfaces via the same register-then-retire-obsolete path every
# other surface uses.
CANONICAL_BOT_SURFACES = tuple(
    {
        "surface_id": f"{bot.lower()}-{suffix}", "category": bot,
        "channel": channel.format(bot=bot.lower()), "owner": "Codex",
        "purpose": purpose.format(bot),
        "producer": "rivalry_presentation.publish_bot_surfaces",
        "publisher": "discord_transport.DiscordTracker", "update_mode": update_mode,
        "expected_silence": expected_silence,
        **({"max_silence_minutes": 10} if update_mode == UPDATE_MODE_PERIODIC else {}),
        "event_types": event_types, "schema_version": "phase15-v1",
    }
    for bot in ("BLACKTIDE", "RIPTIDE")
    for suffix, channel, purpose, update_mode, expected_silence, event_types in (
        ("dashboard-card", "{bot}-dashboard", "{}'s balance/generation/P&L/win-rate stat card",
         UPDATE_MODE_PERIODIC, False, ("PUBLISH",)),
        ("dashboard-chart", "{bot}-dashboard", "{}'s bankroll-history chart",
         UPDATE_MODE_PERIODIC, False, ("PUBLISH",)),
        ("held-trade-card", "{bot}-held-trades", "{}'s current OPEN/FLAT position card",
         UPDATE_MODE_EVENT_DRIVEN, True, ("PUBLISH",)),
        ("winners-card", "{bot}-winners", "{}'s immutable one-card-per-winning-close receipts",
         UPDATE_MODE_EVENT_DRIVEN, True, ("PUBLISH",)),
        ("losers-card", "{bot}-losers", "{}'s immutable one-card-per-losing-close receipts",
         UPDATE_MODE_EVENT_DRIVEN, True, ("PUBLISH",)),
    )
)


def reconcile_canonical_bot_surfaces(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Same idempotent register-then-retire-obsolete shape as
    reconcile_canonical_competition_surfaces, for the per-bot surfaces."""
    active_ids = {item["surface_id"] for item in CANONICAL_BOT_SURFACES}
    for item in CANONICAL_BOT_SURFACES:
        register_surface(connection, **item)
    rows = connection.execute(
        "SELECT surface_id FROM surfaces WHERE category IN ('AXIOM', 'BLACKTIDE', 'RIPTIDE')"
    ).fetchall()
    retired: list[str] = []
    for row in rows:
        surface_id = row["surface_id"]
        if surface_id not in active_ids:
            connection.execute(
                "UPDATE surfaces SET enabled=0, status='RETIRED' WHERE surface_id=?",
                (surface_id,),
            )
            retired.append(surface_id)
    connection.commit()
    return tuple(retired)


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS surfaces (
            surface_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            channel TEXT NOT NULL,
            owner TEXT NOT NULL,
            purpose TEXT NOT NULL,
            producer TEXT NOT NULL,
            publisher TEXT NOT NULL,
            event_types TEXT NOT NULL DEFAULT '',
            update_mode TEXT NOT NULL,
            expected_silence INTEGER NOT NULL,
            max_silence_minutes INTEGER,
            persistent_message_id TEXT,
            schema_version TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'UPDATED',
            registered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS surface_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surface_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            at TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS surface_events_surface_time
            ON surface_events(surface_id, at DESC);
        """
    )
    connection.commit()
    return connection


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def register_surface(
    connection: sqlite3.Connection,
    *,
    surface_id: str,
    category: str,
    channel: str,
    owner: str,
    purpose: str,
    producer: str,
    publisher: str,
    update_mode: str,
    expected_silence: bool,
    max_silence_minutes: int | None = None,
    event_types: tuple[str, ...] = (),
    persistent_message_id: str | None = None,
    schema_version: str = "",
    enabled: bool = True,
) -> None:
    if update_mode not in UPDATE_MODES:
        raise ValueError(f"Unknown update_mode: {update_mode!r}")
    if update_mode == UPDATE_MODE_PERIODIC and not expected_silence and max_silence_minutes is None:
        raise ValueError(
            "PERIODIC surfaces that are not expected_silence need max_silence_minutes "
            "to know when they've gone stale"
        )
    connection.execute(
        """
        INSERT INTO surfaces (
            surface_id, category, channel, owner, purpose, producer, publisher,
            event_types, update_mode, expected_silence, max_silence_minutes,
            persistent_message_id, schema_version, enabled, status, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UPDATED', ?)
        ON CONFLICT(surface_id) DO UPDATE SET
            category=excluded.category, channel=excluded.channel, owner=excluded.owner,
            purpose=excluded.purpose, producer=excluded.producer, publisher=excluded.publisher,
            event_types=excluded.event_types, update_mode=excluded.update_mode,
            expected_silence=excluded.expected_silence,
            max_silence_minutes=excluded.max_silence_minutes,
            persistent_message_id=excluded.persistent_message_id,
            schema_version=excluded.schema_version, enabled=excluded.enabled
        """,
        (
            surface_id, category, channel, owner, purpose, producer, publisher,
            ",".join(event_types), update_mode, int(expected_silence), max_silence_minutes,
            persistent_message_id, schema_version, int(enabled), _now_iso(),
        ),
    )
    connection.commit()


def reconcile_canonical_competition_surfaces(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Upsert the authoritative competition cards and retire obsolete ones.

    This is idempotent and local.  Live Discord comparison/publishing is done
    by rivalry_presentation so an outage cannot corrupt manifest ownership.
    """
    active_ids = {item["surface_id"] for item in CANONICAL_COMPETITION_SURFACES}
    for item in CANONICAL_COMPETITION_SURFACES:
        register_surface(connection, **item)
    rows = connection.execute(
        "SELECT surface_id FROM surfaces WHERE category='RIVALRY'"
    ).fetchall()
    retired: list[str] = []
    for row in rows:
        surface_id = row["surface_id"]
        if surface_id not in active_ids:
            connection.execute(
                "UPDATE surfaces SET enabled=0, status='RETIRED' WHERE surface_id=?",
                (surface_id,),
            )
            retired.append(surface_id)
    connection.commit()
    return tuple(retired)


def record_surface_event(
    connection: sqlite3.Connection,
    *,
    surface_id: str,
    event_type: str,
    detail: str = "",
) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type!r}")
    exists = connection.execute(
        "SELECT 1 FROM surfaces WHERE surface_id=?", (surface_id,)
    ).fetchone()
    if not exists:
        raise ValueError(f"surface_id {surface_id!r} was never registered")
    connection.execute(
        "INSERT INTO surface_events (surface_id, event_type, at, detail) VALUES (?, ?, ?, ?)",
        (surface_id, event_type, _now_iso(), detail[:1000]),
    )
    connection.commit()


def _get_surface(connection: sqlite3.Connection, surface_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM surfaces WHERE surface_id=?", (surface_id,)
    ).fetchone()


def _last_event(connection: sqlite3.Connection, surface_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM surface_events WHERE surface_id=? ORDER BY at DESC, id DESC LIMIT 1",
        (surface_id,),
    ).fetchone()


def compute_health(
    connection: sqlite3.Connection, surface_id: str, *, now: datetime | None = None
) -> str:
    """Derives one of the six timing-based states. DESYNCHRONIZED and
    MISCONFIGURED are never derived here - they require comparing
    declared state against live Discord state, not built this phase."""
    surface = _get_surface(connection, surface_id)
    if surface is None:
        raise ValueError(f"surface_id {surface_id!r} was never registered")
    if not surface["enabled"]:
        return NO_DATA_EXPECTED

    last = _last_event(connection, surface_id)
    now = now or datetime.now().astimezone()

    if last is not None and last["event_type"] == "ERROR":
        return PUBLISH_FAILED

    if last is None:
        if surface["expected_silence"]:
            return QUIET_VALID
        return PRODUCER_OFFLINE

    last_at = datetime.fromisoformat(last["at"])
    age_minutes = (now - last_at).total_seconds() / 60

    if surface["update_mode"] == UPDATE_MODE_EVENT_DRIVEN:
        return HEALTHY

    # PERIODIC
    if surface["expected_silence"]:
        return HEALTHY
    max_silence = surface["max_silence_minutes"]
    if max_silence is not None and age_minutes > max_silence:
        return STALE
    return HEALTHY


def set_surface_status(connection: sqlite3.Connection, surface_id: str, status: str) -> None:
    if status not in SURFACE_STATUSES:
        raise ValueError(f"Unknown surface status: {status!r}")
    cursor = connection.execute(
        "UPDATE surfaces SET status=? WHERE surface_id=?", (status, surface_id)
    )
    if cursor.rowcount == 0:
        raise ValueError(f"surface_id {surface_id!r} was never registered")
    connection.commit()


def surface_snapshot(connection: sqlite3.Connection, surface_id: str) -> dict[str, Any]:
    surface = _get_surface(connection, surface_id)
    if surface is None:
        raise ValueError(f"surface_id {surface_id!r} was never registered")
    last = _last_event(connection, surface_id)
    return {
        **dict(surface),
        "health": compute_health(connection, surface_id),
        "last_event_type": last["event_type"] if last else None,
        "last_event_at": last["at"] if last else None,
    }
