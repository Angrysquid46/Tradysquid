"""Clean Learning Center channels, enforce order, and migrate Discord cards."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import ford_scan
from discord_cards import message_is_backed, style_message_payload
from learning_center_catalog import (
    AUXILIARY_CHANNELS,
    LEARNING_CHANNEL_ORDER,
    LEGACY_CHANNEL_ALIASES,
    LESSON_BY_CHANNEL,
    ORDERED_CHANNELS,
)
from run_with_env import load_env

ROOT = Path(__file__).resolve().parent
MIGRATION_LOG = ROOT / "state" / "supervisor-logs" / "card-migration.log"
CHANNEL_MAP_PATH = ROOT / "state" / "learning-channel-map.json"
LEARNING_CATEGORY = "LEARNING CENTER"
CANONICAL_LESSONS = set(ORDERED_CHANNELS)
KEEP_CHANNELS = CANONICAL_LESSONS | set(AUXILIARY_CHANNELS)


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _learning_category_and_children(
    tracker: ford_scan.DiscordTracker,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category = next(
        (
            item
            for item in channels
            if item.get("type") == 4
            and str(item.get("name") or "").casefold() == LEARNING_CATEGORY.casefold()
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
    return category, children


def migrate_legacy_learning_channels(tracker: ford_scan.DiscordTracker) -> int:
    """Rename old numbered channels before the structure sync creates replacements."""
    _, children = _learning_category_and_children(tracker)
    by_name = {_normalized(item.get("name")): item for item in children}
    migrated = 0
    for old_name, new_name in LEGACY_CHANNEL_ALIASES.items():
        old = by_name.get(_normalized(old_name))
        if not old or _normalized(new_name) in by_name:
            continue
        spec = LESSON_BY_CHANNEL.get(new_name)
        payload: dict[str, Any] = {"name": new_name}
        if spec:
            payload["topic"] = spec.topic
        updated = tracker._request("PATCH", f"/channels/{old['id']}", payload)
        by_name.pop(_normalized(old_name), None)
        by_name[_normalized(new_name)] = updated if isinstance(updated, dict) else old
        print(f"Renamed Learning Center #{old_name} to #{new_name}.")
        migrated += 1
    return migrated


def _topic_identity(name: str) -> str:
    normalized = _normalized(name)
    if normalized in KEEP_CHANNELS:
        return normalized
    if normalized in LEGACY_CHANNEL_ALIASES:
        return LEGACY_CHANNEL_ALIASES[normalized]
    without_number = re.sub(r"^\d{1,2}-", "", normalized)
    for canonical in ORDERED_CHANNELS:
        canonical_tail = re.sub(r"^\d{1,2}-", "", canonical)
        if without_number == canonical_tail:
            return canonical
    return ""


def cleanup_duplicate_learning_channels(
    tracker: ford_scan.DiscordTracker,
) -> int:
    _, children = _learning_category_and_children(tracker)
    canonical_present = {
        _normalized(item.get("name"))
        for item in children
        if _normalized(item.get("name")) in KEEP_CHANNELS
    }
    seen: set[str] = set()
    deleted = 0
    for channel in sorted(children, key=lambda item: int(item.get("position") or 0)):
        name = _normalized(channel.get("name") or "")
        identity = _topic_identity(name)
        if not identity:
            continue
        keep = name == identity and identity in KEEP_CHANNELS and identity not in seen
        if keep:
            seen.add(identity)
            continue
        if identity in canonical_present or identity in seen or name != identity:
            tracker._request("DELETE", f"/channels/{channel['id']}")
            print(f"Deleted duplicate Learning Center channel #{name}.")
            deleted += 1
        else:
            seen.add(identity)
    return deleted


def order_learning_channels(tracker: ford_scan.DiscordTracker) -> int:
    """Force index, 01..27, ask, and reviews into exact Discord order."""
    category, children = _learning_category_and_children(tracker)
    by_name = {_normalized(item.get("name")): item for item in children}
    missing = [name for name in LEARNING_CHANNEL_ORDER if name not in by_name]
    if missing:
        raise RuntimeError("Cannot order missing Learning Center channels: " + ", ".join(missing))

    positions = [
        {
            "id": str(by_name[name]["id"]),
            "position": index,
            "parent_id": str(category["id"]),
            "lock_permissions": False,
        }
        for index, name in enumerate(LEARNING_CHANNEL_ORDER)
    ]
    tracker._request("PATCH", f"/guilds/{tracker.guild_id}/channels", positions)
    print(
        "Learning Center order enforced: index, 01 through 27, ask-tradebot, "
        "examples-and-reviews."
    )
    return len(positions)


def write_learning_channel_map(tracker: ford_scan.DiscordTracker) -> dict[str, str]:
    """Persist clickable channel IDs for TradeBot educational citations."""
    _, children = _learning_category_and_children(tracker)
    mapping = {
        _normalized(item.get("name")): str(item.get("id"))
        for item in children
        if _normalized(item.get("name")) in KEEP_CHANNELS and item.get("id")
    }
    missing = [name for name in LEARNING_CHANNEL_ORDER if name not in mapping]
    if missing:
        raise RuntimeError("Learning channel map is incomplete: " + ", ".join(missing))
    CHANNEL_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CHANNEL_MAP_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": 2,
                "guild_id": str(tracker.guild_id),
                "channels": mapping,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(CHANNEL_MAP_PATH)
    print(f"Stored {len(mapping)} Learning Center channel references.")
    return mapping


def _message_channels(tracker: ford_scan.DiscordTracker) -> list[dict[str, Any]]:
    guild_channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    channels = [
        item
        for item in guild_channels
        if item.get("type") in {0, 5, 10, 11, 12}
    ]
    try:
        active = tracker._request("GET", f"/guilds/{tracker.guild_id}/threads/active")
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
                (message.get("author") or {}).get("bot") or message.get("webhook_id")
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
    """Start full historical card migration without blocking deployment."""
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
        ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")
    migrate_existing_bot_messages(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
