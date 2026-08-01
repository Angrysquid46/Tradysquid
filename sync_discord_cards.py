"""Clean duplicate Learning Center channels and migrate bot output to cards."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import ford_scan
import sync_learning_center
from discord_cards import message_is_backed, style_message_payload
from run_with_env import load_env

ROOT = Path(__file__).resolve().parent
MIGRATION_LOG = ROOT / "state" / "supervisor-logs" / "card-migration.log"
LEARNING_CATEGORY = "LEARNING CENTER"
CANONICAL_LESSONS = set(sync_learning_center.load_lessons())
KEEP_CHANNELS = CANONICAL_LESSONS | {
    "learning-index",
    "ask-tradebot",
    "examples-and-reviews",
}
ALIASES = {
    "stock-basics": "01-stock-basics",
    "stocks-basics": "01-stock-basics",
    "market-basics": "01-stock-basics",
    "market-and-stock-basics": "01-stock-basics",
    "stocks-and-market-basics": "01-stock-basics",
    "01-market-basics": "01-stock-basics",
    "options-basics": "02-options-basics",
    "option-basics": "02-options-basics",
    "basic-options": "02-options-basics",
    "options-contract-basics": "02-options-basics",
}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _topic_identity(name: str) -> str:
    normalized = _normalized(name)
    if normalized in ALIASES:
        return ALIASES[normalized]
    without_number = re.sub(r"^\d{1,2}-", "", normalized)
    for canonical in CANONICAL_LESSONS:
        canonical_tail = re.sub(r"^\d{1,2}-", "", canonical)
        if without_number == canonical_tail:
            return canonical
    return ""


def cleanup_duplicate_learning_channels(
    tracker: ford_scan.DiscordTracker,
) -> int:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category = next(
        (
            item
            for item in channels
            if item.get("type") == 4
            and str(item.get("name") or "").casefold()
            == LEARNING_CATEGORY.casefold()
        ),
        None,
    )
    if not category:
        raise RuntimeError("Learning Center category was not found.")

    children = [
        item
        for item in channels
        if item.get("type") == 0
        and str(item.get("parent_id") or "") == str(category["id"])
    ]
    kept_topics: set[str] = set()
    deleted = 0
    for channel in children:
        name = _normalized(channel.get("name") or "")
        identity = name if name in KEEP_CHANNELS else _topic_identity(name)
        if not identity:
            continue

        if identity in KEEP_CHANNELS and identity == name and identity not in kept_topics:
            kept_topics.add(identity)
            continue

        if identity in kept_topics or name != identity:
            tracker._request("DELETE", f"/channels/{channel['id']}")
            print(f"Deleted duplicate Learning Center channel #{name}.")
            deleted += 1
        else:
            kept_topics.add(identity)
    return deleted


def _message_channels(tracker: ford_scan.DiscordTracker) -> list[dict[str, Any]]:
    guild_channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    channels = [
        item
        for item in guild_channels
        if item.get("type") in {0, 5, 10, 11, 12}
    ]
    try:
        active = tracker._request(
            "GET", f"/guilds/{tracker.guild_id}/threads/active"
        )
    except ford_scan.DiscordError:
        active = {}
    channels.extend((active or {}).get("threads") or [])

    unique: dict[str, dict[str, Any]] = {}
    for channel in channels:
        channel_id = str(channel.get("id") or "")
        if channel_id:
            unique[channel_id] = channel
    return list(unique.values())


def _all_messages(
    tracker: ford_scan.DiscordTracker,
    channel_id: str,
) -> Iterable[dict[str, Any]]:
    before = ""
    while True:
        path = f"/channels/{channel_id}/messages?limit=100"
        if before:
            path += f"&before={before}"
        batch = tracker._request("GET", path)
        if not isinstance(batch, list) or not batch:
            return
        yield from batch
        if len(batch) < 100:
            return
        before = str(batch[-1].get("id") or "")
        if not before:
            return


def migrate_existing_bot_messages(
    tracker: ford_scan.DiscordTracker,
) -> dict[str, int]:
    totals = {"channels": 0, "messages": 0}
    for channel in _message_channels(tracker):
        changed = 0
        try:
            messages = list(_all_messages(tracker, str(channel["id"])))
        except ford_scan.DiscordError:
            continue
        for message in messages:
            authored_by_bot = (
                (message.get("author") or {}).get("bot")
                or message.get("webhook_id")
            )
            content = str(message.get("content") or "").strip()
            if not authored_by_bot or not content or message_is_backed(message):
                continue
            tracker._request(
                "PATCH",
                f"/channels/{channel['id']}/messages/{message['id']}",
                style_message_payload(
                    {"content": content, "allowed_mentions": {"parse": []}}
                ),
            )
            changed += 1
        if changed:
            totals["channels"] += 1
            totals["messages"] += changed
            print(f"#{channel.get('name')}: migrated {changed} messages to cards.")
    print(
        "Discord card migration complete: "
        f"{totals['messages']} messages across {totals['channels']} channels."
    )
    return totals


def launch_background_migration() -> int:
    """Start the full historical migration without blocking deployment timeout."""
    MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True

    with MIGRATION_LOG.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "run_with_env.py"),
                str(ROOT / "sync_discord_cards.py"),
                "--migrate",
            ],
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            **kwargs,
        )
    print(f"Started background Discord card migration as PID {process.pid}.")
    return process.pid


def main() -> int:
    load_env()
    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN,
        ford_scan.DISCORD_GUILD_ID,
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")
    migrate_existing_bot_messages(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
