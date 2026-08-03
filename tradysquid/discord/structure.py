from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


MAX_CHANNELS_PER_CATEGORY = 50
MAPPING_PREFIX = "discord.channel."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name(value: Any) -> str:
    return str(getattr(value, "name", ""))


def _category_name(channel: Any) -> str:
    category = getattr(channel, "category", None)
    return _name(category)


def _channel_id(channel: Any) -> str:
    return str(getattr(channel, "id", ""))


def _category_id(category: Any) -> str:
    return str(getattr(category, "id", ""))


def _category_channels(category: Any) -> list[Any]:
    return list(getattr(category, "text_channels", []) or [])


def _has_capacity(category: Any) -> bool:
    return len(_category_channels(category)) < MAX_CHANNELS_PER_CATEGORY


class DiscordStructureService:
    """Reconcile the declarative Discord structure without destructive cleanup.

    Existing channels are searched across the whole guild. A required channel is
    never recreated merely because it currently lives under another category.
    Full categories use deterministic managed overflow categories.
    """

    def __init__(self, schema: dict[str, Any], database: Any | None = None) -> None:
        self.schema = schema
        self.database = database

    def _saved_mappings(self) -> dict[str, str]:
        if self.database is None:
            return {}
        try:
            rows = self.database.query(
                "SELECT key,value_json FROM settings WHERE key LIKE ?",
                (f"{MAPPING_PREFIX}%",),
            )
        except Exception:
            return {}
        output: dict[str, str] = {}
        for row in rows:
            try:
                value = json.loads(str(row["value_json"]))
            except (TypeError, ValueError, KeyError):
                continue
            stable_key = str(row.get("key", ""))[len(MAPPING_PREFIX) :].casefold()
            channel_id = str(value.get("channel_id", "")) if isinstance(value, dict) else ""
            if stable_key and channel_id:
                output[stable_key] = channel_id
        return output

    def _persist_mapping(
        self,
        *,
        stable_key: str,
        requested_category: str,
        actual_category: str,
        channel: Any,
        action: str,
        duplicates: list[str],
    ) -> None:
        if self.database is None:
            return
        details = {
            "stable_key": stable_key,
            "channel_id": _channel_id(channel),
            "channel_name": _name(channel),
            "action": action,
            "duplicates": duplicates,
            "requested_category": requested_category,
            "actual_category": actual_category,
            "updated_at": _utc_now(),
        }
        self.database.execute(
            "INSERT OR REPLACE INTO settings(key,value_json,updated_at) VALUES (?,?,?)",
            (
                f"{MAPPING_PREFIX}{stable_key}",
                json.dumps(details, sort_keys=True),
                details["updated_at"],
            ),
        )

    @staticmethod
    def _all_text_channels(guild: Any, categories: list[Any]) -> list[Any]:
        channels: list[Any] = []
        seen: set[str] = set()
        for channel in list(getattr(guild, "text_channels", []) or []):
            key = _channel_id(channel) or f"object:{id(channel)}"
            if key not in seen:
                seen.add(key)
                channels.append(channel)
        for category in categories:
            for channel in _category_channels(category):
                key = _channel_id(channel) or f"object:{id(channel)}"
                if key not in seen:
                    seen.add(key)
                    channels.append(channel)
        return channels

    @staticmethod
    def _canonical_match(
        matches: list[Any], intended_category: Any, saved_channel_id: str | None
    ) -> Any:
        if saved_channel_id:
            for channel in matches:
                if _channel_id(channel) == saved_channel_id:
                    return channel

        intended_id = _category_id(intended_category)
        in_intended = [
            channel
            for channel in matches
            if _category_id(getattr(channel, "category", None)) == intended_id
        ]
        candidates = in_intended or matches
        return sorted(
            candidates,
            key=lambda channel: (
                _channel_id(channel) == "",
                _channel_id(channel),
                _category_name(channel).casefold(),
            ),
        )[0]

    async def _ensure_category(
        self,
        guild: Any,
        categories: list[Any],
        categories_by_name: dict[str, Any],
        name: str,
    ) -> tuple[Any, str]:
        existing = categories_by_name.get(name.casefold())
        if existing is not None:
            return existing, "category-reused"
        category = await guild.create_category(
            name, reason="Tradysquid declarative structure"
        )
        categories.append(category)
        categories_by_name[name.casefold()] = category
        return category, "category-created"

    async def _overflow_category(
        self,
        guild: Any,
        categories: list[Any],
        categories_by_name: dict[str, Any],
        base_name: str,
    ) -> tuple[Any, str]:
        index = 2
        while index < 100:
            overflow_name = f"{base_name} {index}"
            category = categories_by_name.get(overflow_name.casefold())
            if category is not None:
                if _has_capacity(category):
                    return category, "overflow-category-reused"
                index += 1
                continue
            category = await guild.create_category(
                overflow_name,
                reason="Tradysquid managed overflow for Discord category capacity",
            )
            categories.append(category)
            categories_by_name[overflow_name.casefold()] = category
            return category, "overflow-category-created"
        raise RuntimeError(
            f"No Discord category capacity is available for managed category {base_name}"
        )

    @staticmethod
    async def _try_move(channel: Any, category: Any) -> bool:
        edit = getattr(channel, "edit", None)
        if edit is None:
            return False
        try:
            await edit(
                category=category,
                reason="Tradysquid declarative structure reconciliation",
            )
            return True
        except Exception:
            return False

    async def sync(self, guild: Any) -> list[dict[str, Any]]:
        categories = list(getattr(guild, "categories", []) or [])
        categories_by_name = {
            _name(category).casefold(): category for category in categories
        }
        all_channels = self._all_text_channels(guild, categories)
        saved_mappings = self._saved_mappings()
        receipts: list[dict[str, Any]] = []

        for definition in self.schema.get("categories", []):
            requested_category_name = str(definition["name"])
            intended_category, category_action = await self._ensure_category(
                guild,
                categories,
                categories_by_name,
                requested_category_name,
            )

            for requested_channel_name in definition.get("channels", []):
                channel_name = str(requested_channel_name)
                stable_key = channel_name.casefold()
                matches = [
                    channel
                    for channel in all_channels
                    if _name(channel).casefold() == stable_key
                ]
                duplicate_ids: list[str] = []
                capacity_action: str | None = None

                if matches:
                    channel = self._canonical_match(
                        matches,
                        intended_category,
                        saved_mappings.get(stable_key),
                    )
                    duplicate_ids = [
                        _channel_id(candidate)
                        for candidate in matches
                        if candidate is not channel
                    ]
                    if getattr(channel, "category", None) is intended_category:
                        action = "channel-reused-intended-category"
                    else:
                        action = "channel-reused-other-category"
                        if _has_capacity(intended_category):
                            moved = await self._try_move(channel, intended_category)
                            if moved:
                                action = "channel-moved-to-intended-category"
                    actual_category = _category_name(channel)
                else:
                    target_category = intended_category
                    if not _has_capacity(target_category):
                        target_category, capacity_action = await self._overflow_category(
                            guild,
                            categories,
                            categories_by_name,
                            requested_category_name,
                        )
                    channel = await guild.create_text_channel(
                        channel_name,
                        category=target_category,
                        reason="Tradysquid declarative structure",
                    )
                    all_channels.append(channel)
                    if channel not in _category_channels(target_category):
                        text_channels = getattr(target_category, "text_channels", None)
                        if isinstance(text_channels, list):
                            text_channels.append(channel)
                    action = "channel-created"
                    actual_category = _category_name(channel) or _name(target_category)

                receipt = {
                    "stable_key": stable_key,
                    "requested_category": requested_category_name,
                    "actual_category": actual_category,
                    "channel": channel_name,
                    "id": _channel_id(channel),
                    "action": action,
                    "category_action": category_action,
                    "capacity_action": capacity_action,
                    "duplicate_channel_ids": duplicate_ids,
                    "duplicate_count": len(duplicate_ids),
                }
                receipts.append(receipt)
                self._persist_mapping(
                    stable_key=stable_key,
                    requested_category=requested_category_name,
                    actual_category=actual_category,
                    channel=channel,
                    action=action,
                    duplicates=duplicate_ids,
                )

        if self.database is not None:
            summary = {
                "categories_created": sum(
                    item["category_action"] == "category-created" for item in receipts
                ),
                "overflow_categories_created": sum(
                    item["capacity_action"] == "overflow-category-created"
                    for item in receipts
                ),
                "overflow_categories_reused": sum(
                    item["capacity_action"] == "overflow-category-reused"
                    for item in receipts
                ),
                "channels_created": sum(
                    item["action"] == "channel-created" for item in receipts
                ),
                "channels_reused": sum(
                    item["action"].startswith("channel-reused") for item in receipts
                ),
                "channels_moved": sum(
                    item["action"] == "channel-moved-to-intended-category"
                    for item in receipts
                ),
                "duplicate_channels_detected": sum(
                    int(item["duplicate_count"]) for item in receipts
                ),
                "mappings": receipts,
            }
            self.database.execute(
                "INSERT INTO discord_sync_receipts(id,component,status,details_json,observed_at) "
                "VALUES (?,?,?,?,?)",
                (
                    f"discord-structure:{_utc_now()}",
                    "discord-structure",
                    "PASS",
                    json.dumps(summary, sort_keys=True),
                    _utc_now(),
                ),
            )

        return receipts
