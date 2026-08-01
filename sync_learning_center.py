"""Synchronize the comprehensive stock and options library into Discord cards."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ford_scan
from discord_cards import message_has_source, style_message_payload
from learning_center_catalog import LESSONS, LESSON_BY_CHANNEL, ORDERED_CHANNELS

ROOT = Path(__file__).resolve().parent
CURRICULUM_PATH = ROOT / "learning_center" / "COMPREHENSIVE_TRADING_LIBRARY.md"
MAX_DISCORD_DESCRIPTION = 3900
CHUNK_TARGET = 3350
MARKER_PREFIX = "Tradysquids curriculum"
CHANNEL_PATTERN = re.compile(
    r"<!-- CHANNEL:(?P<channel>[a-z0-9-]+) -->\s*"
    r"(?P<body>.*?)\s*"
    r"<!-- END:(?P=channel) -->",
    re.DOTALL,
)


def load_lessons(path: Path = CURRICULUM_PATH) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    parsed = {
        match.group("channel"): match.group("body").strip()
        for match in CHANNEL_PATTERN.finditer(text)
    }
    missing = [channel for channel in ORDERED_CHANNELS if channel not in parsed]
    unexpected = [channel for channel in parsed if channel not in LESSON_BY_CHANNEL]
    if missing or unexpected or len(parsed) != len(LESSONS):
        raise RuntimeError(
            "Learning library catalog mismatch. "
            f"Missing: {missing or 'none'}; unexpected: {unexpected or 'none'}; "
            f"expected {len(LESSONS)}, found {len(parsed)}."
        )
    return {channel: parsed[channel] for channel in ORDERED_CHANNELS}


def _split_long_block(block: str, limit: int) -> list[str]:
    lines = block.splitlines() or [block]
    pieces: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        words = line.split()
        line_piece = ""
        for word in words:
            candidate = f"{line_piece} {word}".strip()
            if len(candidate) <= limit:
                line_piece = candidate
            else:
                if line_piece:
                    pieces.append(line_piece)
                line_piece = word
        current = line_piece
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(text: str, limit: int = CHUNK_TARGET) -> list[str]:
    """Split at section and paragraph boundaries while retaining Markdown."""
    blocks = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        parts = [block] if len(block) <= limit else _split_long_block(block, limit)
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
        raise RuntimeError("A Learning Center lesson produced no Discord cards.")
    return chunks


def lesson_marker(channel: str, part: int, total: int) -> str:
    return f"**{MARKER_PREFIX} · #{channel} · Part {part}/{total}**"


def _remove_duplicate_h1(chunk: str) -> str:
    lines = chunk.splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        return "\n".join(lines[1:]).strip()
    return chunk


def expected_messages(channel: str, lesson: str) -> list[str]:
    spec = LESSON_BY_CHANNEL[channel]
    chunks = chunk_markdown(lesson)
    messages: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        body = _remove_duplicate_h1(chunk) if index == 1 else chunk
        messages.append(
            "\n".join(
                [
                    lesson_marker(channel, index, len(chunks)),
                    f"# {spec.number:02d} · {spec.title} · Part {index}/{len(chunks)}",
                    body or "Continue to the next card.",
                ]
            ).strip()
        )
    if any(len(message) > MAX_DISCORD_DESCRIPTION for message in messages):
        lengths = [len(message) for message in messages]
        raise RuntimeError(f"{channel} produced oversized lesson cards: {lengths}")
    return messages


def _recent_messages(
    tracker: ford_scan.DiscordTracker,
    channel_id: str,
) -> list[dict[str, Any]]:
    result = tracker._request("GET", f"/channels/{channel_id}/messages?limit=100")
    return result if isinstance(result, list) else []


def _is_old_learning_message(message: dict[str, Any], channel: str) -> bool:
    if not ((message.get("author") or {}).get("bot") or message.get("webhook_id")):
        return False
    text = ford_scan.message_search_text(message).strip()
    current_prefix = f"{MARKER_PREFIX} · #{channel} · Part "
    if MARKER_PREFIX in text and current_prefix not in text:
        return True
    spec = LESSON_BY_CHANNEL[channel]
    first_line = text.splitlines()[0].strip("#* `") if text else ""
    return (
        bool(first_line)
        and spec.title.casefold() in first_line.casefold()
        and MARKER_PREFIX not in text
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
                    "PUT", f"/channels/{channel['id']}/pins/{message['id']}"
                )
            except ford_scan.DiscordError as exc:
                if "HTTP 403" not in str(exc):
                    raise

    for marker, message in by_marker.items():
        if marker not in expected_markers:
            tracker._request(
                "DELETE", f"/channels/{channel['id']}/messages/{message['id']}"
            )
            deleted += 1

    for message in recent:
        if message in existing:
            continue
        if _is_old_learning_message(message, channel_name):
            tracker._request(
                "DELETE", f"/channels/{channel['id']}/messages/{message['id']}"
            )
            deleted += 1

    return created, updated, deleted


def synchronize_curriculum(
    tracker: ford_scan.DiscordTracker | None = None,
) -> dict[str, int]:
    lessons = load_lessons()
    tracker = tracker or ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")

    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    text_channels = {
        str(item.get("name") or "").casefold(): item
        for item in channels
        if item.get("type") == 0
    }
    totals = {"created": 0, "updated": 0, "deleted": 0, "channels": 0, "cards": 0}
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
        totals["cards"] += len(expected_messages(channel_name, lesson))
        print(
            f"#{channel_name}: {created} created, {updated} updated, "
            f"{deleted} removed."
        )

    if missing:
        raise RuntimeError("Missing Discord learning channels: " + ", ".join(missing))
    print(
        "Comprehensive Learning Center synchronized: "
        f"{totals['channels']} channels, {totals['cards']} cards, "
        f"{totals['created']} created, {totals['updated']} updated, "
        f"{totals['deleted']} removed."
    )
    return totals


def validate_curriculum() -> dict[str, int]:
    lessons = load_lessons()
    counts = {
        channel: len(expected_messages(channel, lesson))
        for channel, lesson in lessons.items()
    }
    if tuple(counts) != ORDERED_CHANNELS:
        raise RuntimeError("Learning Center validation order does not match catalog.")
    print(
        f"Validated {len(counts)} ordered lessons and "
        f"{sum(counts.values())} Discord cards."
    )
    return counts


if __name__ == "__main__":
    validate_curriculum()
