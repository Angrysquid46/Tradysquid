"""Phase 9: rivalry event system (Master Spec Section 7). Bounded,
traceable public trash-talk between BLACKTIDE and AXIOM, triggered by
real competition events - never a code path that can open, close, or
size a trade, and never imported by anything that does.

No persona/response-generation logic exists here - no bot exists yet to
generate rivalry messages (Phase 11+). This module is the bounded,
auditable write/read layer a future persona would call.

The eight initial limits below are the spec's own design targets, not
measured values - the spec itself says "Claude must audit actual Discord
behavior and recommend safe final values," which needs a live channel to
audit against. Not available this phase; kept here as clearly-labeled
starting defaults, same basis as Phase 5's manifest grade thresholds and
Phase 7's budget reserve fractions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "rivalry.db"

RIVALRY_MAX_MESSAGES_PER_BOT_PER_EVENT = 3
RIVALRY_MAX_MESSAGES_PER_BOT_PER_DAY = 20
RIVALRY_MAX_TOTAL_MESSAGES_PER_MINUTE = 6
RIVALRY_MIN_MESSAGE_GAP_SECONDS = 20
RIVALRY_MAX_CONVERSATION_ROUNDS = 3
RIVALRY_OPEN_POSITION_CHAT = False
RIVALRY_PRIVATE_STRATEGY_ACCESS = False
RIVALRY_CAN_INFLUENCE_TRADING = False

TRIGGERS = (
    "SESSION_OPEN", "SESSION_CLOSE", "FIRST_WIN_OF_DAY", "FIRST_LOSS_OF_DAY",
    "TRADE_CLOSED_WIN", "TRADE_CLOSED_LOSS", "NEW_COMPETITION_LEADER",
    "LEAD_EXTENDED", "LEAD_LOST", "BANKROLL_MILESTONE", "NEW_BEST_TRADE",
    "NEW_WORST_TRADE", "WINNING_STREAK", "LOSING_STREAK",
    "DRAWDOWN_RECOVERY", "MAJOR_COMEBACK", "GENERATION_BUSTED",
    "GENERATION_RECORD", "GENERATION_COMPLETED", "SESSION_WINNER",
    "LIFETIME_LEADER_CHANGE",
)

# Each bot gets exactly one SESSION_OPEN and one SESSION_CLOSE post per
# day (Phase 14 audit finding - nothing previously enforced this).
_ONCE_PER_DAY_TRIGGERS = ("SESSION_OPEN", "SESSION_CLOSE")

BOTS = ("BLACKTIDE", "AXIOM")

# scoreboard.scoreboard_snapshot()'s own public key set, duplicated here
# rather than pulled in from that module directly - rivalry.py must stay
# structurally incapable of touching the scoreboard, enforced by
# test_module_has_no_reference_to_scoreboard_write_functions banning any
# reference to it at all. test_rivalry.py cross-checks this literal
# against the real one so drift between the two gets caught, without
# rivalry.py ever depending on that module. Phase 14 audit finding:
# public_score_snapshot was unstructured dict[str, Any] - nothing stopped
# an unexpected/private key from riding along.
ALLOWED_PUBLIC_SNAPSHOT_KEYS = frozenset({
    "bot", "generation", "current_bankroll", "generation_pnl", "lifetime_pnl",
    "trade_count_generation", "trade_count_lifetime", "win_rate", "profit_factor",
    "expectancy", "average_winner", "average_loser", "largest_winner", "largest_loser",
    "max_drawdown", "current_drawdown", "bust_count", "current_streak",
    "best_generation", "worst_generation", "generation_over_generation_improvement",
    "current_position_status",
})


class RivalryLimitExceeded(Exception):
    """Raised instead of silently posting anyway - what makes 'no
    infinite autonomous loops' real rather than merely documented."""


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rivalry_events (
            rivalry_event_id TEXT PRIMARY KEY,
            event_group_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trigger TEXT NOT NULL,
            speaker TEXT NOT NULL,
            target TEXT,
            message TEXT NOT NULL,
            public_score_snapshot_json TEXT NOT NULL,
            trade_reference TEXT,
            generation INTEGER,
            reply_to_id TEXT,
            conversation_round INTEGER NOT NULL,
            callbacks_used_json TEXT NOT NULL DEFAULT '[]',
            discord_message_id TEXT
        );
        CREATE INDEX IF NOT EXISTS rivalry_events_speaker_time
            ON rivalry_events(speaker, timestamp DESC);
        CREATE INDEX IF NOT EXISTS rivalry_events_group
            ON rivalry_events(event_group_id);
        """
    )
    connection.commit()
    return connection


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def check_rivalry_limits(
    connection: sqlite3.Connection,
    *,
    speaker: str,
    event_group_id: str,
    trigger: str | None = None,
    now: datetime | None = None,
) -> None:
    """Raises RivalryLimitExceeded if a new message from `speaker` would
    violate any of the bounded-chain limits. Called by record_rivalry_event
    before writing - never bypassable by a caller that skips straight to a
    raw INSERT, since this module owns the only write path."""
    now = now or datetime.now().astimezone()

    per_event = connection.execute(
        "SELECT COUNT(*) AS n FROM rivalry_events WHERE speaker=? AND event_group_id=?",
        (speaker, event_group_id),
    ).fetchone()["n"]
    if per_event >= RIVALRY_MAX_MESSAGES_PER_BOT_PER_EVENT:
        raise RivalryLimitExceeded(
            f"{speaker} already sent {per_event} messages in event {event_group_id!r} "
            f"(max {RIVALRY_MAX_MESSAGES_PER_BOT_PER_EVENT})"
        )

    today = now.date().isoformat()
    per_day = connection.execute(
        "SELECT COUNT(*) AS n FROM rivalry_events WHERE speaker=? AND timestamp LIKE ?",
        (speaker, f"{today}%"),
    ).fetchone()["n"]
    if per_day >= RIVALRY_MAX_MESSAGES_PER_BOT_PER_DAY:
        raise RivalryLimitExceeded(
            f"{speaker} already sent {per_day} messages today "
            f"(max {RIVALRY_MAX_MESSAGES_PER_BOT_PER_DAY})"
        )

    if trigger in _ONCE_PER_DAY_TRIGGERS:
        same_trigger_today = connection.execute(
            "SELECT COUNT(*) AS n FROM rivalry_events "
            "WHERE speaker=? AND trigger=? AND timestamp LIKE ?",
            (speaker, trigger, f"{today}%"),
        ).fetchone()["n"]
        if same_trigger_today >= 1:
            raise RivalryLimitExceeded(
                f"{speaker} already posted {trigger} today (once per day only)"
            )

    one_minute_ago = (now - timedelta(minutes=1)).isoformat()
    total_last_minute = connection.execute(
        "SELECT COUNT(*) AS n FROM rivalry_events WHERE timestamp >= ?",
        (one_minute_ago,),
    ).fetchone()["n"]
    if total_last_minute >= RIVALRY_MAX_TOTAL_MESSAGES_PER_MINUTE:
        raise RivalryLimitExceeded(
            f"{total_last_minute} total rivalry messages in the last minute "
            f"(max {RIVALRY_MAX_TOTAL_MESSAGES_PER_MINUTE})"
        )

    last = connection.execute(
        "SELECT timestamp FROM rivalry_events WHERE speaker=? "
        "ORDER BY timestamp DESC LIMIT 1",
        (speaker,),
    ).fetchone()
    if last is not None:
        gap_seconds = (now - _parse(last["timestamp"])).total_seconds()
        if gap_seconds < RIVALRY_MIN_MESSAGE_GAP_SECONDS:
            raise RivalryLimitExceeded(
                f"{speaker}'s last message was {gap_seconds:.1f}s ago "
                f"(min gap {RIVALRY_MIN_MESSAGE_GAP_SECONDS}s)"
            )


def record_rivalry_event(
    connection: sqlite3.Connection,
    *,
    rivalry_event_id: str,
    event_group_id: str,
    trigger: str,
    speaker: str,
    message: str,
    public_score_snapshot: dict[str, Any],
    target: str | None = None,
    trade_reference: str | None = None,
    generation: int | None = None,
    reply_to_id: str | None = None,
    conversation_round: int = 0,
    callbacks_used: list[str] | None = None,
    discord_message_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if trigger not in TRIGGERS:
        raise ValueError(f"Unknown trigger: {trigger!r}")
    if speaker not in BOTS:
        raise ValueError(f"Unknown speaker: {speaker!r}")
    if target is not None and target not in BOTS:
        raise ValueError(f"Unknown target: {target!r}")
    if conversation_round < 0 or conversation_round >= RIVALRY_MAX_CONVERSATION_ROUNDS:
        raise RivalryLimitExceeded(
            f"conversation round {conversation_round} exceeds finite reply-chain limit "
            f"{RIVALRY_MAX_CONVERSATION_ROUNDS}"
        )
    if reply_to_id:
        parent = connection.execute(
            "SELECT event_group_id, conversation_round FROM rivalry_events "
            "WHERE rivalry_event_id=?", (reply_to_id,),
        ).fetchone()
        if parent is None:
            raise ValueError(f"reply_to_id {reply_to_id!r} does not exist")
        if parent["event_group_id"] != event_group_id:
            raise ValueError("reply must remain inside its original event group")
        if conversation_round != int(parent["conversation_round"]) + 1:
            raise ValueError("reply conversation_round must advance exactly once")
    unexpected_keys = set(public_score_snapshot) - ALLOWED_PUBLIC_SNAPSHOT_KEYS
    if unexpected_keys:
        raise ValueError(
            f"public_score_snapshot has unrecognized key(s) {sorted(unexpected_keys)!r} - "
            "only scoreboard.scoreboard_snapshot()'s own public fields are allowed, so a "
            "private value can't accidentally hitch a ride into rivalry memory"
        )
    position_status = public_score_snapshot.get("current_position_status")
    if position_status is not None and position_status not in ("OPEN", "FLAT"):
        raise ValueError("public position status may expose only OPEN or FLAT")
    existing = connection.execute(
        "SELECT 1 FROM rivalry_events WHERE rivalry_event_id=?", (rivalry_event_id,)
    ).fetchone()
    if existing:
        raise ValueError(f"rivalry_event_id {rivalry_event_id!r} already recorded")

    check_rivalry_limits(
        connection, speaker=speaker, event_group_id=event_group_id, trigger=trigger, now=now
    )

    timestamp = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    connection.execute(
        """
        INSERT INTO rivalry_events (
            rivalry_event_id, event_group_id, timestamp, trigger, speaker, target,
            message, public_score_snapshot_json, trade_reference, generation,
            reply_to_id, conversation_round, callbacks_used_json, discord_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rivalry_event_id, event_group_id, timestamp, trigger, speaker, target,
            message, json.dumps(public_score_snapshot, default=str), trade_reference,
            generation, reply_to_id, conversation_round,
            json.dumps(callbacks_used or []), discord_message_id,
        ),
    )
    connection.commit()
    return {
        "rivalry_event_id": rivalry_event_id, "event_group_id": event_group_id,
        "timestamp": timestamp, "trigger": trigger, "speaker": speaker,
    }


def public_rivalry_history(
    connection: sqlite3.Connection, bot: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Read-only - what a future persona layer calls for prior public
    boasts and relevant history. Never used to derive trading decisions."""
    if bot is None:
        rows = connection.execute(
            "SELECT * FROM rivalry_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM rivalry_events WHERE speaker=? OR target=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (bot, bot, limit),
        ).fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["public_score_snapshot"] = json.loads(record.pop("public_score_snapshot_json"))
        record["callbacks_used"] = json.loads(record.pop("callbacks_used_json"))
        results.append(record)
    return results
