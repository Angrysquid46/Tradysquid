"""Phase 10: Learning Center shell (Master Spec Section 15). The
43-chapter options-education curriculum's stable structure - chapter
list, Discord channel naming, LC-XX-YY lesson IDs, and a registry with
zero real content yet (population is Phase 16).

This is deliberately separate from the repo's existing, narrower
Learning Center system (learning_center_catalog.py and friends - 32
freeform topic channels, no LC-XX-YY scheme). Per explicit owner
direction, that system is not extended or reused here; this is a fresh
build for Section 15's specific 43-chapter curriculum, alongside it.

Never imported by anything that makes trading decisions - Section 15's
own isolation requirement ("autonomous BLACKTIDE and Claude trading
processes must be mechanically prevented from importing, searching,
querying, training from, or using Learning Center strategy content"),
the same architectural statement rivalry.py already makes for Section 7.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "learning_center_index.db"

# Section 15's curriculum, exactly as listed - chapter number -> title.
CHAPTERS: dict[int, str] = {
    1: "Definitions",
    2: "Covered Call Writing",
    3: "Call Buying",
    4: "Other Call Buying Strategies",
    5: "Naked Call Writing",
    6: "Ratio Call Writing",
    7: "Bull Spreads Using Call Options",
    8: "Bear Spreads Using Call Options",
    9: "Calendar Spreads",
    10: "Butterfly Spread",
    11: "Ratio Call Spreads",
    12: "Combining Calendar and Ratio Spreads",
    13: "Reverse Spreads",
    14: "Diagonalizing a Spread",
    15: "Put Option Basics",
    16: "Put Option Buying",
    17: "Put Buying with Stock Ownership",
    18: "Buying Puts with Call Purchases",
    19: "Sale of a Put",
    20: "Sale of a Straddle",
    21: "Synthetic Stock Positions",
    22: "Basic Put Spreads",
    23: "Spreads Combining Calls and Puts",
    24: "Ratio Spreads Using Puts",
    25: "LEAPS / Long-Term Option Strategies",
    26: "Buying Options and Treasury Bills",
    27: "Arbitrage",
    28: "Mathematical Applications",
    29: "Index Option Products and Futures",
    30: "Stock Index Hedging",
    31: "Index Spreading",
    32: "Structured Products",
    33: "Mathematical Considerations for Index Products",
    34: "Futures and Futures Options",
    35: "Futures Option Strategies for Futures Spreads",
    36: "Basics of Volatility Trading",
    37: "How Volatility Affects Popular Strategies",
    38: "Distribution of Stock Prices",
    39: "Volatility Trading Techniques",
    40: "Advanced Concepts",
    41: "Volatility Derivatives",
    42: "Taxes",
    43: "The Best Strategy?",
}

PUBLICATION_STATES = ("DRAFT", "PUBLISHED", "RETIRED")

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    slug = _SLUG_STRIP_RE.sub("-", title.lower()).strip("-")
    return slug


def chapter_channel_name(chapter: int) -> str:
    """lc- prefix avoids colliding with sync_discord_structure.py's
    existing unrelated LEARNING CENTER channels (e.g. 07-technical-
    analysis is not curriculum chapter 7)."""
    if chapter not in CHAPTERS:
        raise ValueError(f"Unknown chapter: {chapter!r} (must be 1-43)")
    return f"lc-{chapter:02d}-{_slugify(CHAPTERS[chapter])}"


def lesson_id(chapter: int, lesson_number: int) -> str:
    if chapter not in CHAPTERS:
        raise ValueError(f"Unknown chapter: {chapter!r} (must be 1-43)")
    if lesson_number < 1:
        raise ValueError(f"lesson_number must be >= 1, got {lesson_number!r}")
    return f"LC-{chapter:02d}-{lesson_number:02d}"


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            lesson_id TEXT PRIMARY KEY,
            chapter INTEGER NOT NULL,
            lesson_number INTEGER NOT NULL,
            chapter_title TEXT NOT NULL,
            lesson_title TEXT NOT NULL,
            topics_json TEXT NOT NULL DEFAULT '[]',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            related_concepts_json TEXT NOT NULL DEFAULT '[]',
            discord_channel TEXT NOT NULL,
            discord_message_id TEXT,
            jump_link TEXT,
            version TEXT NOT NULL DEFAULT '1',
            publication_state TEXT NOT NULL DEFAULT 'DRAFT',
            registered_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS lessons_chapter ON lessons(chapter, lesson_number);
        """
    )
    connection.commit()
    return connection


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def register_lesson(
    connection: sqlite3.Connection,
    *,
    chapter: int,
    lesson_number: int,
    lesson_title: str,
    topics: list[str] | None = None,
    keywords: list[str] | None = None,
    related_concepts: list[str] | None = None,
    discord_message_id: str | None = None,
    jump_link: str | None = None,
    version: str = "1",
    publication_state: str = "DRAFT",
) -> str:
    if chapter not in CHAPTERS:
        raise ValueError(f"Unknown chapter: {chapter!r} (must be 1-43)")
    if publication_state not in PUBLICATION_STATES:
        raise ValueError(f"Unknown publication_state: {publication_state!r}")
    the_id = lesson_id(chapter, lesson_number)
    connection.execute(
        """
        INSERT INTO lessons (
            lesson_id, chapter, lesson_number, chapter_title, lesson_title,
            topics_json, keywords_json, related_concepts_json, discord_channel,
            discord_message_id, jump_link, version, publication_state, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lesson_id) DO UPDATE SET
            lesson_title=excluded.lesson_title, topics_json=excluded.topics_json,
            keywords_json=excluded.keywords_json,
            related_concepts_json=excluded.related_concepts_json,
            discord_message_id=excluded.discord_message_id,
            jump_link=excluded.jump_link, version=excluded.version,
            publication_state=excluded.publication_state
        """,
        (
            the_id, chapter, lesson_number, CHAPTERS[chapter], lesson_title,
            json.dumps(topics or []), json.dumps(keywords or []),
            json.dumps(related_concepts or []), chapter_channel_name(chapter),
            discord_message_id, jump_link, version, publication_state, _now_iso(),
        ),
    )
    connection.commit()
    return the_id


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for key in ("topics_json", "keywords_json", "related_concepts_json"):
        record[key[: -len("_json")]] = json.loads(record.pop(key))
    return record


def lessons_for_chapter(connection: sqlite3.Connection, chapter: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM lessons WHERE chapter=? ORDER BY lesson_number ASC", (chapter,)
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_lessons(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """Read-only substring search over title/topics/keywords - what human
    Q&A calls to search and link directly to lessons, once real content
    exists (Phase 16). No ranking sophistication needed for an empty
    shell; this just has to find the right rows once they exist."""
    like = f"%{query.lower()}%"
    rows = connection.execute(
        """
        SELECT * FROM lessons
        WHERE lower(lesson_title) LIKE ? OR lower(topics_json) LIKE ? OR lower(keywords_json) LIKE ?
        ORDER BY chapter ASC, lesson_number ASC
        """,
        (like, like, like),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]
