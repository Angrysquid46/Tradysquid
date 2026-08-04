from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .layout import (
    CHANNEL_ALIASES,
    INVENTED_CATEGORIES,
    MIGRATION_CHANNEL_NAMES,
)

MAX_CHANNELS_PER_CATEGORY = 50
MAPPING_PREFIX = "discord.channel."
MIGRATION_STATE_KEY = "discord.layout.restore-original-dashboard-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name(value: Any) -> str:
    return str(getattr(value, "name", ""))


def _object_id(value: Any) -> str:
    return str(getattr(value, "id", ""))


def _category(channel: Any) -> Any | None:
    return getattr(channel, "category", None)


def _category_name(channel: Any) -> str:
    return _name(_category(channel))


def _category_channels(category: Any) -> list[Any]:
    channels = getattr(category, "channels", None)
    if channels is not None:
        return list(channels or [])
    output: list[Any] = []
    for attribute in ("text_channels", "forums"):
        for channel in list(getattr(category, attribute, []) or []):
            if channel not in output:
                output.append(channel)
    return output


def _all_channels(guild: Any, categories: Iterable[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()

    def add(channel: Any) -> None:
        key = _object_id(channel) or f"object:{id(channel)}"
        if key not in seen:
            seen.add(key)
            output.append(channel)

    for attribute in ("channels", "text_channels", "forums"):
        for channel in list(getattr(guild, attribute, []) or []):
            if channel not in categories and _name(channel):
                add(channel)
    for category in categories:
        for channel in _category_channels(category):
            add(channel)
    return output


def _channel_type(channel: Any) -> str:
    explicit = getattr(channel, "type", None)
    text = str(explicit or channel.__class__.__name__).casefold()
    return "forum" if "forum" in text else "text"


def _spec(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value["name"]), str(value.get("type", "text"))
    return str(value), "text"


def _has_capacity(category: Any) -> bool:
    return len(_category_channels(category)) < MAX_CHANNELS_PER_CATEGORY


class DiscordStructureService:
    """Restore and resolve the established Tradysquid dashboard.

    Ordinary startup is resolution-only. The one-time migration may move an
    original channel back from an invented clean-rebuild category, but it never
    moves aliases, never creates overflow categories, and never creates a second
    dashboard.
    """

    def __init__(self, schema: dict[str, Any], database: Any | None = None) -> None:
        self.schema = schema
        self.database = database
        self.resolved_channels: dict[str, Any] = {}
        self.cleanup_candidates: list[Any] = []
        self.invented_categories: list[Any] = []
        self.missing_channels: list[str] = []
        self.migration_active = False

    def _setting(self, key: str) -> Any:
        if self.database is None:
            return None
        rows = self.database.query("SELECT value_json FROM settings WHERE key=?", (key,))
        if not rows:
            return None
        try:
            return json.loads(rows[0]["value_json"])
        except (KeyError, TypeError, ValueError):
            return None

    def _put_setting(self, key: str, value: Any) -> None:
        if self.database is None:
            return
        self.database.execute(
            "INSERT OR REPLACE INTO settings(key,value_json,updated_at) VALUES (?,?,?)",
            (key, json.dumps(value, sort_keys=True, default=str), _utc_now()),
        )

    def _saved_mappings(self) -> dict[str, str]:
        if self.database is None:
            return {}
        rows = self.database.query(
            "SELECT key,value_json FROM settings WHERE key LIKE ?",
            (f"{MAPPING_PREFIX}%",),
        )
        output: dict[str, str] = {}
        for row in rows:
            try:
                value = json.loads(str(row["value_json"]))
            except (TypeError, ValueError, KeyError):
                continue
            stable_key = str(row["key"])[len(MAPPING_PREFIX) :].casefold()
            channel_id = str(value.get("channel_id", "")) if isinstance(value, dict) else ""
            if stable_key and channel_id:
                output[stable_key] = channel_id
        return output

    def _persist_mapping(
        self,
        *,
        canonical_name: str,
        requested_category: str,
        channel: Any,
        action: str,
        aliases: tuple[str, ...],
        duplicates: list[str],
    ) -> None:
        details = {
            "stable_key": canonical_name.casefold(),
            "channel_id": _object_id(channel),
            "channel_name": _name(channel),
            "requested_category": requested_category,
            "actual_category": _category_name(channel),
            "action": action,
            "aliases": list(aliases),
            "duplicates": duplicates,
            "migration_source": "restore-original-dashboard-v1",
            "updated_at": _utc_now(),
        }
        self._put_setting(f"{MAPPING_PREFIX}{canonical_name.casefold()}", details)

    def _migration_enabled(self) -> bool:
        migration = self.schema.get("migration", {})
        if not bool(migration.get("restore_original_layout", False)):
            return False
        current = self._setting(MIGRATION_STATE_KEY)
        return not (isinstance(current, dict) and current.get("status") == "PASS")

    @staticmethod
    def _sort_key(channel: Any) -> tuple[bool, str, str]:
        channel_id = _object_id(channel)
        return (not bool(channel_id), channel_id, _category_name(channel).casefold())

    def _choose(
        self,
        *,
        canonical_name: str,
        requested_type: str,
        intended_category: Any | None,
        channels: list[Any],
        saved_channel_id: str | None,
    ) -> tuple[Any | None, list[Any], str]:
        canonical_key = canonical_name.casefold()
        aliases = {item.casefold() for item in CHANNEL_ALIASES.get(canonical_name, ())}
        typed = [
            channel
            for channel in channels
            if requested_type == "text"
            or _channel_type(channel) == requested_type
            or not getattr(channel, "type", None)
        ]
        exact = [channel for channel in typed if _name(channel).casefold() == canonical_key]
        alias_matches = [
            channel for channel in typed if _name(channel).casefold() in aliases
        ]
        intended_id = _object_id(intended_category)

        def in_intended(items: list[Any]) -> list[Any]:
            return [
                channel
                for channel in items
                if intended_id and _object_id(_category(channel)) == intended_id
            ]

        exact_intended = sorted(in_intended(exact), key=self._sort_key)
        if exact_intended:
            return exact_intended[0], exact + alias_matches, "channel-reused-original"

        exact_saved = [
            channel for channel in exact if _object_id(channel) == saved_channel_id
        ]
        if exact_saved:
            return exact_saved[0], exact + alias_matches, "channel-reused-saved-original"

        if exact:
            return (
                sorted(exact, key=self._sort_key)[0],
                exact + alias_matches,
                "channel-reused-original-other-category",
            )

        alias_intended = sorted(in_intended(alias_matches), key=self._sort_key)
        if alias_intended:
            return alias_intended[0], alias_matches, "channel-reused-legacy-alias"

        alias_saved = [
            channel for channel in alias_matches if _object_id(channel) == saved_channel_id
        ]
        if alias_saved:
            return alias_saved[0], alias_matches, "channel-reused-saved-alias"

        if alias_matches:
            return (
                sorted(alias_matches, key=self._sort_key)[0],
                alias_matches,
                "channel-reused-alias-other-category",
            )

        return None, [], "channel-missing"

    @staticmethod
    async def _try_move(channel: Any, category: Any) -> bool:
        edit = getattr(channel, "edit", None)
        if edit is None:
            return False
        try:
            await edit(
                category=category,
                reason="Restore the owner-approved Tradysquid dashboard layout",
            )
            return True
        except Exception:
            return False

    async def _create_missing(
        self, guild: Any, category: Any, name: str, requested_type: str
    ) -> Any | None:
        if not self.schema.get("allow_create_missing", False):
            return None
        if category is None or not _has_capacity(category):
            return None
        if requested_type == "forum" and hasattr(guild, "create_forum_channel"):
            return await guild.create_forum_channel(
                name,
                category=category,
                reason="Owner-approved Tradysquid original dashboard",
            )
        creator = getattr(guild, "create_text_channel", None)
        if creator is None:
            return None
        return await creator(
            name,
            category=category,
            reason="Owner-approved Tradysquid original dashboard",
        )

    async def sync(self, guild: Any) -> list[dict[str, Any]]:
        categories = list(getattr(guild, "categories", []) or [])
        categories_by_name = {
            _name(category).casefold(): category for category in categories
        }
        channels = _all_channels(guild, categories)
        saved_mappings = self._saved_mappings()
        self.resolved_channels = {}
        self.cleanup_candidates = []
        self.missing_channels = []
        self.invented_categories = [
            category
            for category in categories
            if _name(category).upper() in INVENTED_CATEGORIES
        ]
        self.migration_active = self._migration_enabled()
        receipts: list[dict[str, Any]] = []

        selected_ids: set[str] = set()
        duplicate_objects: list[Any] = []

        for category_definition in self.schema.get("categories", []):
            requested_category_name = str(category_definition["name"])
            intended_category = categories_by_name.get(requested_category_name.casefold())
            category_status = (
                "category-reused" if intended_category is not None else "category-missing"
            )

            for raw_channel in category_definition.get("channels", []):
                canonical_name, requested_type = _spec(raw_channel)
                aliases = CHANNEL_ALIASES.get(canonical_name, ())
                selected, candidates, action = self._choose(
                    canonical_name=canonical_name,
                    requested_type=requested_type,
                    intended_category=intended_category,
                    channels=channels,
                    saved_channel_id=saved_mappings.get(canonical_name.casefold()),
                )

                moved = False
                if (
                    selected is not None
                    and intended_category is not None
                    and _name(selected).casefold() == canonical_name.casefold()
                    and _category(selected) is not intended_category
                    and self.migration_active
                ):
                    moved = await self._try_move(selected, intended_category)
                    if moved:
                        action = "channel-restored-to-original-category"

                if selected is None:
                    selected = await self._create_missing(
                        guild,
                        intended_category,
                        canonical_name,
                        requested_type,
                    )
                    if selected is not None:
                        channels.append(selected)
                        action = "channel-created-owner-approved"
                    else:
                        self.missing_channels.append(canonical_name)
                        receipts.append(
                            {
                                "stable_key": canonical_name.casefold(),
                                "requested_category": requested_category_name,
                                "actual_category": None,
                                "channel": canonical_name,
                                "id": None,
                                "action": "channel-missing",
                                "category_action": category_status,
                                "aliases": list(aliases),
                                "duplicate_channel_ids": [],
                                "duplicate_count": 0,
                                "moved": False,
                            }
                        )
                        continue

                selected_id = _object_id(selected)
                selected_ids.add(selected_id)
                self.resolved_channels[canonical_name.casefold()] = selected
                self.resolved_channels[_name(selected).casefold()] = selected
                for alias in aliases:
                    self.resolved_channels.setdefault(alias.casefold(), selected)

                duplicates = [
                    candidate
                    for candidate in candidates
                    if _object_id(candidate) != selected_id
                ]
                duplicate_objects.extend(duplicates)
                duplicate_ids = [_object_id(candidate) for candidate in duplicates]
                self._persist_mapping(
                    canonical_name=canonical_name,
                    requested_category=requested_category_name,
                    channel=selected,
                    action=action,
                    aliases=aliases,
                    duplicates=duplicate_ids,
                )
                receipts.append(
                    {
                        "stable_key": canonical_name.casefold(),
                        "requested_category": requested_category_name,
                        "actual_category": _category_name(selected),
                        "channel": canonical_name,
                        "resolved_channel_name": _name(selected),
                        "id": selected_id,
                        "action": action,
                        "category_action": category_status,
                        "aliases": list(aliases),
                        "duplicate_channel_ids": duplicate_ids,
                        "duplicate_count": len(duplicate_ids),
                        "moved": moved,
                    }
                )

        seen_cleanup: set[str] = set()
        for candidate in [
            *duplicate_objects,
            *[
                channel
                for category in self.invented_categories
                for channel in _category_channels(category)
                if _name(channel).casefold() in MIGRATION_CHANNEL_NAMES
            ],
        ]:
            candidate_id = _object_id(candidate)
            if (
                candidate_id
                and candidate_id not in selected_ids
                and candidate_id not in seen_cleanup
            ):
                seen_cleanup.add(candidate_id)
                self.cleanup_candidates.append(candidate)

        summary = {
            "status": "PASS" if not self.missing_channels else "DEGRADED",
            "layout": self.schema.get("layout", "original-dashboard"),
            "migration_active": self.migration_active,
            "categories_found": sum(
                item["category_action"] == "category-reused" for item in receipts
            ),
            "categories_missing": sorted(
                {
                    item["requested_category"]
                    for item in receipts
                    if item["category_action"] == "category-missing"
                }
            ),
            "channels_resolved": sum(item["id"] is not None for item in receipts),
            "channels_missing": sorted(self.missing_channels),
            "channels_restored": sum(
                item["action"] == "channel-restored-to-original-category"
                for item in receipts
            ),
            "cleanup_candidates": [
                {
                    "id": _object_id(channel),
                    "name": _name(channel),
                    "category": _category_name(channel),
                }
                for channel in self.cleanup_candidates
            ],
            "invented_categories": [
                _name(category) for category in self.invented_categories
            ],
            "observed_at": _utc_now(),
        }
        self._put_setting("discord.layout.last-sync", summary)
        if self.database is not None:
            self.database.execute(
                "INSERT INTO discord_sync_receipts(id,component,status,details_json,observed_at) "
                "VALUES (?,?,?,?,?)",
                (
                    f"structure:{_utc_now()}",
                    "structure-original-layout",
                    summary["status"],
                    json.dumps(summary, sort_keys=True),
                    _utc_now(),
                ),
            )
        return receipts

    @staticmethod
    async def _is_bot_only(channel: Any, bot_user_id: str) -> bool:
        if bool(getattr(channel, "human_authored", False)):
            return False
        if list(getattr(channel, "threads", []) or []):
            return False
        messages = getattr(channel, "messages", None)
        if messages is not None:
            for message in list(messages):
                author = getattr(message, "author", None)
                if author is None:
                    continue
                if str(getattr(author, "id", "")) != str(bot_user_id) and not bool(
                    getattr(author, "bot", False)
                ):
                    return False
            return True
        history = getattr(channel, "history", None)
        if history is None:
            return False
        try:
            async for message in history(limit=None, oldest_first=False):
                author = getattr(message, "author", None)
                if author is None:
                    continue
                if str(getattr(author, "id", "")) != str(bot_user_id) and not bool(
                    getattr(author, "bot", False)
                ):
                    return False
            return True
        except Exception:
            return False

    async def cleanup(
        self,
        guild: Any,
        *,
        protected_channel_ids: set[str],
        bot_user_id: str,
    ) -> dict[str, Any]:
        if not bool(
            self.schema.get("migration", {}).get("cleanup_invented_categories", False)
        ):
            return {
                "status": "SKIPPED",
                "deleted_channels": [],
                "blocked_channels": [],
                "deleted_categories": [],
            }

        categories = list(getattr(guild, "categories", []) or [])
        all_channels = _all_channels(guild, categories)
        candidate_ids = {
            _object_id(item)
            for item in self.cleanup_candidates
            if (
                _category_name(item).upper() in INVENTED_CATEGORIES
                and _name(item).casefold() in MIGRATION_CHANNEL_NAMES
            )
            or _name(item).casefold() == "shadow-candidates"
        }
        candidate_ids.update(
            _object_id(channel)
            for channel in all_channels
            if _name(channel).casefold() == "shadow-candidates"
        )

        deleted_channels: list[dict[str, str]] = []
        blocked_channels: list[dict[str, str]] = []

        for channel in all_channels:
            channel_id = _object_id(channel)
            if not channel_id or channel_id not in candidate_ids:
                continue
            if channel_id in protected_channel_ids:
                continue
            channel_name = _name(channel).casefold()
            if (
                channel_name not in MIGRATION_CHANNEL_NAMES
                and channel_name != "shadow-candidates"
                and _category_name(channel).upper() not in INVENTED_CATEGORIES
            ):
                continue
            if not await self._is_bot_only(channel, bot_user_id):
                blocked_channels.append(
                    {
                        "id": channel_id,
                        "name": _name(channel),
                        "category": _category_name(channel),
                        "reason": "human-authored-or-unverifiable-content",
                    }
                )
                continue
            delete = getattr(channel, "delete", None)
            if delete is None:
                blocked_channels.append(
                    {
                        "id": channel_id,
                        "name": _name(channel),
                        "category": _category_name(channel),
                        "reason": "delete-not-supported",
                    }
                )
                continue
            try:
                await delete(
                    reason="Remove duplicate channel created by failed clean-rebuild migration"
                )
                category = _category(channel)
                for attribute in ("channels", "text_channels", "forums"):
                    collection = getattr(category, attribute, None)
                    if isinstance(collection, list) and channel in collection:
                        collection.remove(channel)
                deleted_channels.append(
                    {
                        "id": channel_id,
                        "name": _name(channel),
                        "category": _category_name(channel),
                    }
                )
            except Exception as exc:
                blocked_channels.append(
                    {
                        "id": channel_id,
                        "name": _name(channel),
                        "category": _category_name(channel),
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )

        deleted_categories: list[dict[str, str]] = []
        for category in categories:
            if _name(category).upper() not in INVENTED_CATEGORIES:
                continue
            if _category_channels(category):
                continue
            delete = getattr(category, "delete", None)
            if delete is None:
                continue
            try:
                await delete(
                    reason="Remove empty category created by failed clean-rebuild migration"
                )
                deleted_categories.append(
                    {"id": _object_id(category), "name": _name(category)}
                )
            except Exception:
                continue

        remaining_invented = [
            _name(category)
            for category in list(getattr(guild, "categories", []) or [])
            if _name(category).upper() in INVENTED_CATEGORIES
            and _category_channels(category)
        ]
        status = "PASS" if not blocked_channels and not remaining_invented else "DEGRADED"
        result = {
            "status": status,
            "deleted_channels": deleted_channels,
            "blocked_channels": blocked_channels,
            "deleted_categories": deleted_categories,
            "remaining_invented_categories": remaining_invented,
            "observed_at": _utc_now(),
        }
        self._put_setting(MIGRATION_STATE_KEY, result)
        if self.database is not None:
            self.database.execute(
                "INSERT INTO discord_sync_receipts(id,component,status,details_json,observed_at) "
                "VALUES (?,?,?,?,?)",
                (
                    f"layout-cleanup:{_utc_now()}",
                    "layout-cleanup",
                    status,
                    json.dumps(result, sort_keys=True),
                    _utc_now(),
                ),
            )
        return result
