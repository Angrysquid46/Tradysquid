"""Clean duplicate Learning Center channels and migrate bot output to cards."""

from __future__ import annotations

import re

import ford_scan
import sync_learning_center
from discord_cards import message_is_backed, style_message_payload

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
    kept_ids: set[str] = set()
    deleted = 0
    for channel in children:
        name = _normalized(channel.get("name") or "")
        identity = name if name in KEEP_CHANNELS else _topic_identity(name)
        if not identity:
            continue

        if identity in KEEP_CHANNELS and identity == name and identity not in kept_ids:
            kept_ids.add(identity)
            continue

        if identity in kept_ids or name != identity:
            tracker._request("DELETE", f"/channels/{channel['id']}")
            print(f"Deleted duplicate Learning Center channel #{name}.")
            deleted += 1
        else:
            kept_ids.add(identity)

    return deleted


def migrate_existing_bot_messages(
    tracker: ford_scan.DiscordTracker,
    *,
    per_channel_limit: int = 100,
) -> dict[str, int]:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    totals = {"channels": 0, "messages": 0}
    for channel in channels:
        if channel.get("type") != 0:
            continue
        try:
            recent = tracker._request(
                "GET",
                f"/channels/{channel['id']}/messages?limit={per_channel_limit}",
            )
        except ford_scan.DiscordError:
            continue
        changed = 0
        for message in recent if isinstance(recent, list) else []:
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
