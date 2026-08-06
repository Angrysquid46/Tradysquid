from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tradysquid.data.database import Database
from tradysquid.discord.layout import (
    CANONICAL_CATEGORY_ORDER,
    INVENTED_CATEGORIES,
    ORIGINAL_CHANNELS,
)
from tradysquid.discord.structure import DiscordStructureService


ROOT = Path(__file__).resolve().parents[1]


class FakeAuthor:
    def __init__(self, author_id: int, *, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class FakeMessage:
    def __init__(self, author: FakeAuthor) -> None:
        self.author = author


class FakeChannel:
    def __init__(
        self,
        channel_id: int,
        name: str,
        category=None,
        *,
        channel_type: str = "text",
        messages: list[FakeMessage] | None = None,
    ) -> None:
        self.id = channel_id
        self.name = name
        self.category = category
        self.type = channel_type
        self.messages = list(messages or [])
        self.threads: list[object] = []
        self.deleted = False

    async def edit(self, *, category, reason: str) -> None:
        if self.category is not None:
            self.category.remove(self)
        self.category = category
        category.add(self)

    async def delete(self, *, reason: str) -> None:
        self.deleted = True
        if self.category is not None:
            self.category.remove(self)


class FakeCategory:
    def __init__(self, category_id: int, name: str) -> None:
        self.id = category_id
        self.name = name
        self.channels: list[FakeChannel] = []
        self.text_channels: list[FakeChannel] = []
        self.forums: list[FakeChannel] = []
        self.guild = None
        self.deleted = False

    def add(self, channel: FakeChannel) -> None:
        if channel not in self.channels:
            self.channels.append(channel)
        target = self.forums if channel.type == "forum" else self.text_channels
        if channel not in target:
            target.append(channel)
        channel.category = self

    def remove(self, channel: FakeChannel) -> None:
        for collection in (self.channels, self.text_channels, self.forums):
            if channel in collection:
                collection.remove(channel)

    async def delete(self, *, reason: str) -> None:
        self.deleted = True
        if self.guild is not None and self in self.guild.categories:
            self.guild.categories.remove(self)


class FakeGuild:
    def __init__(self, categories: list[FakeCategory]) -> None:
        self.id = 77
        self.categories = categories
        self.created_categories = 0
        self.created_channels = 0
        for category in categories:
            category.guild = self

    @property
    def channels(self) -> list[FakeChannel]:
        return [
            channel
            for category in self.categories
            for channel in category.channels
        ]

    @property
    def text_channels(self) -> list[FakeChannel]:
        return [
            channel
            for category in self.categories
            for channel in category.text_channels
        ]

    @property
    def forums(self) -> list[FakeChannel]:
        return [
            channel
            for category in self.categories
            for channel in category.forums
        ]

    async def create_category(self, name: str, reason: str):
        self.created_categories += 1
        raise AssertionError("ordinary startup must not create categories")

    async def create_text_channel(self, name: str, *, category, reason: str):
        self.created_channels += 1
        raise AssertionError("ordinary startup must not create text channels")

    async def create_forum_channel(self, name: str, *, category, reason: str):
        self.created_channels += 1
        raise AssertionError("ordinary startup must not create forum channels")


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "tradysquid.db")
    database.initialize()
    return database


def _schema() -> dict:
    return json.loads(
        (ROOT / "config" / "discord-schema.json").read_text(encoding="utf-8")
    )


def _add(category: FakeCategory, channel_id: int, name: str, *, forum: bool = False):
    channel = FakeChannel(
        channel_id,
        name,
        channel_type="forum" if forum else "text",
    )
    category.add(channel)
    return channel


def _production_guild() -> tuple[FakeGuild, dict[str, FakeChannel]]:
    categories = [
        FakeCategory(index + 1, name)
        for index, name in enumerate(CANONICAL_CATEGORY_ORDER)
    ]
    by_name = {category.name: category for category in categories}
    channels: dict[str, FakeChannel] = {}
    next_id = 100
    for category_name, names in ORIGINAL_CHANNELS.items():
        category = by_name[category_name]
        for name in names:
            channel = _add(
                category,
                next_id,
                name,
                forum=name == "trade-journal",
            )
            next_id += 1
            channels[name] = channel
    return FakeGuild(categories), channels


def test_original_layout_resolves_without_creating_or_moving(tmp_path: Path) -> None:
    guild, original = _production_guild()
    before = {
        name: (channel.id, channel.category.name)
        for name, channel in original.items()
    }
    service = DiscordStructureService(_schema(), database=_database(tmp_path))

    receipts = asyncio.run(service.sync(guild))

    after = {
        name: (
            service.resolved_channels[name].id,
            service.resolved_channels[name].category.name,
        )
        for name in original
    }
    assert before == after
    assert not service.missing_channels
    assert guild.created_categories == 0
    assert guild.created_channels == 0
    assert all(item["action"].startswith("channel-reused") for item in receipts)


def test_strategy_control_and_exact_six_channels_are_preserved(tmp_path: Path) -> None:
    guild, original = _production_guild()
    service = DiscordStructureService(_schema(), database=_database(tmp_path))

    asyncio.run(service.sync(guild))

    strategy_category = next(
        category for category in guild.categories if category.name == "STRATEGY CONTROL"
    )
    expected = {
        "strategy-control",
        "strategy-settings",
        "strategy-versions",
        "trade-overrides",
        "strategy-change-log",
        "strategy-recommendations",
    }
    assert {channel.name for channel in strategy_category.channels} == expected
    assert all(original[name].deleted is False for name in expected)
    assert "STRATEGY CONTROL" not in INVENTED_CATEGORIES


def test_moved_original_channel_is_restored_once(tmp_path: Path) -> None:
    guild, original = _production_guild()
    scanning = FakeCategory(99, "SCANNING")
    scanning.guild = guild
    guild.categories.append(scanning)
    scanner_feed = original["scanner-feed"]
    scanner_feed.category.remove(scanner_feed)
    scanning.add(scanner_feed)

    service = DiscordStructureService(_schema(), database=_database(tmp_path))
    first = asyncio.run(service.sync(guild))

    assert scanner_feed.category.name == "LIVE TRADING DESK"
    scanner_receipt = next(item for item in first if item["channel"] == "scanner-feed")
    assert scanner_receipt["action"] == "channel-restored-to-original-category"

    cleanup = asyncio.run(
        service.cleanup(
            guild,
            protected_channel_ids={
                str(channel.id) for channel in service.resolved_channels.values()
            },
            bot_user_id="999",
        )
    )
    assert cleanup["status"] == "PASS"
    assert "SCANNING" not in {category.name for category in guild.categories}

    second = asyncio.run(service.sync(guild))
    second_receipt = next(item for item in second if item["channel"] == "scanner-feed")
    assert second_receipt["action"] == "channel-reused-original"
    assert guild.created_categories == 0
    assert guild.created_channels == 0


def test_alias_channel_is_reused_but_never_moved(tmp_path: Path) -> None:
    guild, original = _production_guild()
    live = next(
        category for category in guild.categories if category.name == "LIVE TRADING DESK"
    )
    original["scanner-feed"].category.remove(original["scanner-feed"])
    scanning = FakeCategory(99, "SCANNING")
    scanning.guild = guild
    alias = _add(scanning, 9001, "scan-results")
    guild.categories.append(scanning)

    service = DiscordStructureService(_schema(), database=_database(tmp_path))
    receipts = asyncio.run(service.sync(guild))
    receipt = next(item for item in receipts if item["channel"] == "scanner-feed")

    assert receipt["action"] == "channel-reused-alias-other-category"
    assert service.resolved_channels["scanner-feed"].id == alias.id
    assert alias.category.name == "SCANNING"
    assert not any(channel.name == "scanner-feed" for channel in live.channels)
    assert guild.created_channels == 0


def test_bot_only_duplicate_dashboard_is_removed_after_rebinding(tmp_path: Path) -> None:
    guild, original = _production_guild()
    bot = FakeAuthor(999, bot=True)
    invented: list[FakeCategory] = []
    duplicates = [
        ("SCANNING", "scan-results"),
        ("PAPER TRADING", "open-positions"),
        ("LEARNING CENTER 2", "01-market-foundations"),
    ]
    next_id = 9000
    for category_name, channel_name in duplicates:
        category = FakeCategory(next_id, category_name)
        next_id += 1
        category.guild = guild
        channel = FakeChannel(
            next_id,
            channel_name,
            category,
            messages=[FakeMessage(bot)],
        )
        next_id += 1
        category.add(channel)
        invented.append(category)
    guild.categories.extend(invented)

    service = DiscordStructureService(_schema(), database=_database(tmp_path))
    asyncio.run(service.sync(guild))
    cleanup = asyncio.run(
        service.cleanup(
            guild,
            protected_channel_ids={
                str(channel.id) for channel in service.resolved_channels.values()
            },
            bot_user_id="999",
        )
    )

    assert cleanup["status"] == "PASS"
    assert len(cleanup["deleted_channels"]) == 3
    assert len(cleanup["deleted_categories"]) == 3
    assert not ({category.name for category in guild.categories} & INVENTED_CATEGORIES)
    assert "STRATEGY CONTROL" in {category.name for category in guild.categories}
    assert all(not channel.deleted for channel in original.values())


def test_human_authored_duplicate_is_not_deleted(tmp_path: Path) -> None:
    guild, _ = _production_guild()
    invented = FakeCategory(99, "SCANNING")
    invented.guild = guild
    human_channel = FakeChannel(
        9001,
        "scan-results",
        invented,
        messages=[FakeMessage(FakeAuthor(123, bot=False))],
    )
    invented.add(human_channel)
    guild.categories.append(invented)

    service = DiscordStructureService(_schema(), database=_database(tmp_path))
    asyncio.run(service.sync(guild))
    cleanup = asyncio.run(
        service.cleanup(
            guild,
            protected_channel_ids={
                str(channel.id) for channel in service.resolved_channels.values()
            },
            bot_user_id="999",
        )
    )

    assert cleanup["status"] == "DEGRADED"
    assert human_channel.deleted is False
    assert cleanup["blocked_channels"][0]["reason"] == (
        "human-authored-or-unverifiable-content"
    )
    assert "SCANNING" in cleanup["remaining_invented_categories"]


def test_single_learning_center_contains_original_lessons_1_through_27(
    tmp_path: Path,
) -> None:
    guild, original = _production_guild()
    service = DiscordStructureService(_schema(), database=_database(tmp_path))

    asyncio.run(service.sync(guild))

    learning_categories = [
        category
        for category in guild.categories
        if category.name.startswith("LEARNING CENTER")
    ]
    assert [category.name for category in learning_categories] == ["LEARNING CENTER"]
    for index in range(1, 28):
        prefix = f"{index:02d}-"
        matches = [name for name in original if name.startswith(prefix)]
        assert len(matches) == 1
        assert matches[0] in service.resolved_channels


def test_persisted_original_mapping_survives_restart(tmp_path: Path) -> None:
    database = _database(tmp_path)
    guild, original = _production_guild()
    first = DiscordStructureService(_schema(), database=database)
    asyncio.run(first.sync(guild))

    second = DiscordStructureService(_schema(), database=database)
    asyncio.run(second.sync(guild))

    assert second.resolved_channels["scanner-feed"].id == original["scanner-feed"].id
    rows = database.query(
        "SELECT value_json FROM settings WHERE key=?",
        ("discord.channel.scanner-feed",),
    )
    assert len(rows) == 1
    mapping = json.loads(rows[0]["value_json"])
    assert mapping["channel_id"] == str(original["scanner-feed"].id)
    assert mapping["requested_category"] == "LIVE TRADING DESK"
