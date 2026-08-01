"""Synchronize the long-form options curriculum into readable Discord cards."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ford_scan
from discord_cards import message_has_source, style_message_payload

ROOT = Path(__file__).resolve().parent
CURRICULUM_PATH = ROOT / "learning_center" / "COMPLETE_CURRICULUM.md"
MAX_DISCORD_DESCRIPTION = 3800
CHUNK_TARGET = 3400
MARKER_PREFIX = "Tradysquids curriculum"
CHANNEL_RENAMES = {"01-market-basics": "01-stock-basics"}
CHANNEL_PATTERN = re.compile(
    r"<!-- CHANNEL:(?P<channel>[a-z0-9-]+) -->\s*"
    r"(?P<body>.*?)\s*"
    r"<!-- END:(?P=channel) -->",
    re.DOTALL,
)
LEGACY_HEADINGS = {
    "01-stock-basics": (
        "# Market and Stock Basics",
        "# Stock Basics",
        "# Stocks and Market Basics",
    ),
    "02-options-basics": ("# Options Contract Basics", "# Options Basics"),
    "03-option-chain": ("# Reading an Option Chain",),
    "04-pricing-and-greeks": ("# Pricing and the Greeks",),
    "05-volatility": ("# Volatility and IV",),
    "06-charts": ("# Charts, Candles, and Timeframes",),
    "07-technical-analysis": ("# Technical Analysis",),
    "08-strategies": ("# Core Options Strategies",),
    "09-spreads": ("# Spreads and Multi-Leg Positions",),
    "10-risk-management": ("# Risk Management and Position Sizing",),
    "11-trade-management": ("# Trade Planning and Management",),
    "12-expiration-assignment": ("# Expiration, Exercise, and Assignment",),
    "13-events-and-catalysts": ("# Events and Catalysts",),
    "14-psychology-journaling": ("# Psychology and Journaling",),
    "15-backtesting-stats": ("# Backtesting, Statistics, and Learning",),
    "16-taxes-and-rules": ("# Accounts, Taxes, and Trading Rules",),
    "17-scams-and-myths": ("# Scams, Myths, and Red Flags",),
}


def load_lessons(path: Path = CURRICULUM_PATH) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lessons: dict[str, str] = {}
    for match in CHANNEL_PATTERN.finditer(text):
        channel = CHANNEL_RENAMES.get(match.group("channel"), match.group("channel"))
        lessons[channel] = match.group("body").strip()
    if len(lessons) != 17:
        raise RuntimeError(
            f"Expected 17 curriculum channels, found {len(lessons)} in {path}."
        )
    return lessons


def _split_long_block(block: str, limit: int) -> list[str]:
    words = block.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
        current = word
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(text: str, limit: int = CHUNK_TARGET) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        parts = [paragraph] if len(paragraph) <= limit else _split_long_block(paragraph, limit)
        for part in parts:
            candidate = f"{current}\n\n{part}".strip() if current else part
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    if not chunks:
        raise RuntimeError("Curriculum lesson produced no Discord message parts.")
    return chunks


def lesson_marker(channel: str, part: int, total: int) -> str:
    return f"**{MARKER_PREFIX} · #{channel} · Part {part}/{total}**"


def expected_messages(channel: str, lesson: str) -> list[str]:
    chunks = chunk_markdown(lesson)
    messages = [
        f"{lesson_marker(channel, index, len(chunks))}\n\n{chunk}"
        for index, chunk in enumerate(chunks, start=1)
    ]
    if any(len(message) > MAX_DISCORD_DESCRIPTION for message in messages):
        raise RuntimeError(f"{channel} produced an oversized lesson card.")
    return messages


def _recent_messages(
    tracker: ford_scan.DiscordTracker,
    channel_id: str,
) -> list[dict[str, Any]]:
    result = tracker._request("GET", f"/channels/{channel_id}/messages?limit=100")
    return result if isinstance(result, list) else []


def _is_legacy_lesson(message: dict[str, Any], channel_name: str) -> bool:
    search_text = ford_scan.message_search_text(message).lstrip()
    if MARKER_PREFIX in search_text:
        return False
    return any(
        search_text.startswith(heading)
        for heading in LEGACY_HEADINGS.get(channel_name, ())
    )


def synchronize_channel(
    tracker: ford_scan.DiscordTracker,
    channel: dict[str, Any],
    channel_name: str,
    lesson: str,
) -> tuple[int, int, int]:
    expected = expected_messages(channel_name, lesson)
    recent = _recent_messages(tracker, str(channel["id"]))
    prefix = f"{MARKER_PREFIX} · #{channel_name} · Part "
    existing = [
        message
        for message in recent
        if ((message.get("author") or {}).get("bot") or message.get("webhook_id"))
        and prefix in ford_scan.message_search_text(message)
    ]
    by_marker = {
        ford_scan.message_search_text(message).splitlines()[0].strip("*"): message
        for message in existing
    }

    created = updated = deleted = 0
    expected_markers: set[str] = set()
    for index, content in enumerate(expected, start=1):
        marker = lesson_marker(channel_name, index, len(expected)).strip("*")
        expected_markers.add(marker)
        payload = style_message_payload(
            {"content": content, "allowed_mentions": {"parse": []}}
        )
        message = by_marker.get(marker)
        if message:
            if not message_has_source(message, content):
                tracker._request(
                    "PATCH",
                    f"/channels/{channel['id']}/messages/{message['id']}",
                    payload,
                )
                updated += 1
        else:
            message = tracker._request(
                "POST",
                f"/channels/{channel['id']}/messages",
                payload,
            )
            created += 1

        if index == 1 and isinstance(message, dict) and message.get("id"):
            try:
                tracker._request(
                    "PUT",
                    f"/channels/{channel['id']}/pins/{message['id']}",
                )
            except ford_scan.DiscordError as exc:
                if "HTTP 403" not in str(exc):
                    raise

    for marker, message in by_marker.items():
        if marker not in expected_markers:
            tracker._request(
                "DELETE",
                f"/channels/{channel['id']}/messages/{message['id']}",
            )
            deleted += 1

    for message in recent:
        if _is_legacy_lesson(message, channel_name):
            tracker._request(
                "DELETE",
                f"/channels/{channel['id']}/messages/{message['id']}",
            )
            deleted += 1

    return created, updated, deleted


def synchronize_curriculum(
    tracker: ford_scan.DiscordTracker | None = None,
) -> dict[str, int]:
    lessons = load_lessons()
    tracker = tracker or ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN,
        ford_scan.DISCORD_GUILD_ID,
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")

    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    text_channels = {
        str(item.get("name") or "").casefold(): item
        for item in channels
        if item.get("type") == 0
    }
    totals = {"created": 0, "updated": 0, "deleted": 0, "channels": 0}
    missing: list[str] = []

    for channel_name, lesson in lessons.items():
        channel = text_channels.get(channel_name.casefold())
        if not channel:
            missing.append(channel_name)
            continue
        created, updated, deleted = synchronize_channel(
            tracker, channel, channel_name, lesson
        )
        totals["created"] += created
        totals["updated"] += updated
        totals["deleted"] += deleted
        totals["channels"] += 1
        print(
            f"#{channel_name}: {created} created, "
            f"{updated} updated, {deleted} removed."
        )

    if missing:
        raise RuntimeError(
            "Missing Discord learning channels: " + ", ".join(sorted(missing))
        )
    print(
        "Expanded curriculum synchronized: "
        f"{totals['channels']} channels, {totals['created']} created, "
        f"{totals['updated']} updated, {totals['deleted']} removed."
    )
    return totals


def validate_curriculum() -> dict[str, int]:
    lessons = load_lessons()
    counts = {
        channel: len(expected_messages(channel, lesson))
        for channel, lesson in lessons.items()
    }
    print(
        f"Validated {len(counts)} lessons and "
        f"{sum(counts.values())} Discord card parts."
    )
    return counts


if __name__ == "__main__":
    validate_curriculum()
