"""Private, read-only Discord synchronization for strategy profiles.

PR 1 publishes one persistent card per play style and keeps the private control
surface current. It intentionally contains no strategy mutation path. Runtime
consumers must acknowledge a profile before its card may report ACTIVE.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import ford_scan
import strategy_control_cards
import strategy_profiles

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "strategy-control-sync.json"
CATEGORY_NAME = "STRATEGY CONTROL CENTER"
CHANNEL_SPECS = {
    "strategy-control": "Private, read-only live strategy cards. Editing arrives only through validated owner controls.",
    "trade-overrides": "Private future per-trade override review. No write controls are active in PR 1.",
    "strategy-change-log": "Private immutable strategy change and validation receipts.",
    "strategy-recommendations": "Private Learning Center recommendations requiring owner approval.",
}
SYNC_INTERVAL_SECONDS = max(
    60,
    min(3600, int(os.environ.get("STRATEGY_CONTROL_SYNC_SECONDS", "300"))),
)

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_MESSAGES = 1 << 13
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
BOT_ALLOW = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | MANAGE_MESSAGES
    | EMBED_LINKS
    | ATTACH_FILES
    | READ_MESSAGE_HISTORY
)

_SYNC_LOCK = threading.Lock()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def permission_overwrites(guild_id: str, bot_user_id: str) -> list[dict[str, str | int]]:
    """Deny normal members and allow TradeBot; guild owner/admins bypass the deny."""
    return [
        {
            "id": str(guild_id),
            "type": 0,
            "allow": "0",
            "deny": str(VIEW_CHANNEL),
        },
        {
            "id": str(bot_user_id),
            "type": 1,
            "allow": str(BOT_ALLOW),
            "deny": "0",
        },
    ]


def _write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def _channel_inventory(tracker: Any) -> list[dict[str, Any]]:
    response = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    if not isinstance(response, list):
        raise RuntimeError("Discord channel inventory was not a list")
    return [item for item in response if isinstance(item, dict)]


def _apply_private_overwrites(
    tracker: Any,
    channel_id: str,
    guild_id: str,
    bot_user_id: str,
) -> None:
    tracker._request(
        "PUT",
        f"/channels/{channel_id}/permissions/{guild_id}",
        {"type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)},
    )
    tracker._request(
        "PUT",
        f"/channels/{channel_id}/permissions/{bot_user_id}",
        {"type": 1, "allow": str(BOT_ALLOW), "deny": "0"},
    )


def ensure_private_channels(tracker: Any) -> dict[str, str]:
    """Create or repair the private category and four control channels."""
    inventory = _channel_inventory(tracker)
    bot_user = tracker._request("GET", "/users/@me")
    bot_user_id = str((bot_user or {}).get("id") or "")
    guild_id = str(tracker.guild_id or "")
    if not bot_user_id or not guild_id:
        raise RuntimeError("Discord guild or TradeBot identity is unavailable")

    category = next(
        (
            item
            for item in inventory
            if int(item.get("type") or -1) == 4
            and normalized(item.get("name")) == normalized(CATEGORY_NAME)
        ),
        None,
    )
    if category is None:
        category = tracker._request(
            "POST",
            f"/guilds/{guild_id}/channels",
            {
                "name": CATEGORY_NAME,
                "type": 4,
                "permission_overwrites": permission_overwrites(guild_id, bot_user_id),
            },
        )
        if not isinstance(category, dict) or not category.get("id"):
            raise RuntimeError("Discord did not create the strategy-control category")
        inventory.append(category)
    category_id = str(category["id"])
    _apply_private_overwrites(tracker, category_id, guild_id, bot_user_id)

    channel_ids: dict[str, str] = {}
    for name, topic in CHANNEL_SPECS.items():
        channel = next(
            (
                item
                for item in inventory
                if int(item.get("type") or -1) == 0
                and normalized(item.get("name")) == normalized(name)
            ),
            None,
        )
        if channel is None:
            channel = tracker._request(
                "POST",
                f"/guilds/{guild_id}/channels",
                {
                    "name": name,
                    "type": 0,
                    "parent_id": category_id,
                    "topic": topic,
                    "permission_overwrites": permission_overwrites(
                        guild_id, bot_user_id
                    ),
                },
            )
            if not isinstance(channel, dict) or not channel.get("id"):
                raise RuntimeError(f"Discord did not create #{name}")
            inventory.append(channel)
        else:
            changes: dict[str, Any] = {}
            if str(channel.get("parent_id") or "") != category_id:
                changes["parent_id"] = category_id
            if str(channel.get("topic") or "") != topic:
                changes["topic"] = topic
            if changes:
                channel = tracker._request(
                    "PATCH", f"/channels/{channel['id']}", changes
                )
        channel_id = str(channel["id"])
        _apply_private_overwrites(tracker, channel_id, guild_id, bot_user_id)
        channel_ids[name] = channel_id
    return channel_ids


def _message_contains(message: dict[str, Any], token: str) -> bool:
    return token in json.dumps(message, sort_keys=True, default=str)


def upsert_profile_card(
    tracker: Any,
    channel_id: str,
    card: dict[str, Any],
    token: str,
) -> str:
    """Update one bot-owned singleton card and remove bot-owned duplicates."""
    response = tracker._request(
        "GET", f"/channels/{channel_id}/messages?limit=100"
    )
    messages = response if isinstance(response, list) else []
    matches = [
        message
        for message in messages
        if isinstance(message, dict)
        and bool((message.get("author") or {}).get("bot"))
        and _message_contains(message, token)
    ]
    payload = {
        "content": "",
        "embeds": [card],
        "allowed_mentions": {"parse": []},
    }
    if matches:
        keeper = matches[0]
        message_id = str(keeper.get("id") or "")
        if not message_id:
            raise RuntimeError(f"Existing strategy card {token} has no message ID")
        tracker._request(
            "PATCH", f"/channels/{channel_id}/messages/{message_id}", payload
        )
        for duplicate in matches[1:]:
            duplicate_id = str(duplicate.get("id") or "")
            if duplicate_id:
                tracker._request(
                    "DELETE",
                    f"/channels/{channel_id}/messages/{duplicate_id}",
                )
        return message_id
    created = tracker._request("POST", f"/channels/{channel_id}/messages", payload)
    message_id = str((created or {}).get("id") or "")
    if not message_id:
        raise RuntimeError(f"Discord did not create strategy card {token}")
    return message_id


def sync_once(tracker: Any | None = None) -> dict[str, Any]:
    """Synchronize private channels and six read-only live-proof cards once."""
    with _SYNC_LOCK:
        tracker = tracker or ford_scan.DiscordTracker(
            ford_scan.DISCORD_BOT_TOKEN,
            ford_scan.DISCORD_GUILD_ID,
        )
        if not tracker.ready:
            raise RuntimeError("Discord strategy control requires a ready bot tracker")
        channel_ids = ensure_private_channels(tracker)
        document = strategy_profiles.load_document()
        runtime = strategy_profiles.load_runtime_state()
        snapshot = strategy_profiles.registry_snapshot(document, runtime)
        cards = strategy_control_cards.all_profile_cards(
            document=document,
            runtime_state=runtime,
            page="overview",
        )
        control_channel = channel_ids["strategy-control"]
        message_ids: dict[str, str] = {}
        for profile_snapshot, card in zip(snapshot["profiles"], cards, strict=True):
            profile_name = str(profile_snapshot["name"])
            token = strategy_control_cards.card_token(profile_name)
            message_ids[profile_name] = upsert_profile_card(
                tracker, control_channel, card, token
            )
        statuses = {
            str(item["name"]): str(item["runtime_status"])
            for item in snapshot["profiles"]
        }
        payload = {
            "status": "OK",
            "synced_at": ford_scan.now_ct().isoformat(timespec="seconds"),
            "category": CATEGORY_NAME,
            "channels": channel_ids,
            "cards": message_ids,
            "profile_statuses": statuses,
            "read_only": True,
            "updater_involved": False,
        }
        _write_state(payload)
        return payload


def worker() -> None:
    while True:
        try:
            sync_once()
        except Exception as exc:
            _write_state(
                {
                    "status": "ERROR",
                    "synced_at": ford_scan.now_ct().isoformat(timespec="seconds"),
                    "error": f"{type(exc).__name__}: {exc}",
                    "read_only": True,
                    "updater_involved": False,
                }
            )
        time.sleep(SYNC_INTERVAL_SECONDS)


def start_worker() -> threading.Thread | None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return None
        thread = threading.Thread(
            target=worker,
            name="strategy-control-sync",
            daemon=True,
        )
        thread.start()
        _WORKER_STARTED = True
        return thread


def validate_contract() -> dict[str, Any]:
    overwrites = permission_overwrites("guild", "bot")
    if overwrites[0]["deny"] != str(VIEW_CHANNEL):
        raise RuntimeError("normal members are not denied strategy-control visibility")
    if int(str(overwrites[1]["allow"])) & VIEW_CHANNEL == 0:
        raise RuntimeError("TradeBot cannot view strategy-control channels")
    cards = strategy_control_cards.all_profile_cards()
    if len(cards) != len(strategy_profiles.PROFILE_IDENTITIES):
        raise RuntimeError("one strategy card per profile was not rendered")
    if any(card.get("components") for card in cards):
        raise RuntimeError("PR 1 strategy cards must remain read-only")
    return {
        "profiles": len(cards),
        "channels": list(CHANNEL_SPECS),
        "read_only": True,
        "sync_seconds": SYNC_INTERVAL_SECONDS,
    }
