from __future__ import annotations

import asyncio
from pathlib import Path

from tradysquid.data.database import Database
from tradysquid.discord.structure import DiscordStructureService, MAX_CHANNELS_PER_CATEGORY


class FakeChannel:
    def __init__(self, channel_id: int, name: str, category=None) -> None:
        self.id = channel_id
        self.name = name
        self.category = category

    async def edit(self, *, category, reason: str) -> None:
        if self.category is not None and self in self.category.text_channels:
            self.category.text_channels.remove(self)
        self.category = category
        if self not in category.text_channels:
            category.text_channels.append(self)


class FakeCategory:
    def __init__(self, category_id: int, name: str) -> None:
        self.id = category_id
        self.name = name
        self.text_channels: list[FakeChannel] = []


class FakeGuild:
    def __init__(self, categories: list[FakeCategory]) -> None:
        self.categories = categories
        self.created_categories = 0
        self.created_channels = 0
        ids = [category.id for category in categories]
        self._next_category_id = max(ids, default=0) + 1
        channel_ids = [
            channel.id
            for category in categories
            for channel in category.text_channels
        ]
        self._next_channel_id = max(channel_ids, default=0) + 1

    @property
    def text_channels(self) -> list[FakeChannel]:
        return [
            channel
            for category in self.categories
            for channel in category.text_channels
        ]

    async def create_category(self, name: str, reason: str) -> FakeCategory:
        category = FakeCategory(self._next_category_id, name)
        self._next_category_id += 1
        self.created_categories += 1
        self.categories.append(category)
        return category

    async def create_text_channel(
        self, name: str, *, category: FakeCategory, reason: str
    ) -> FakeChannel:
        if len(category.text_channels) >= MAX_CHANNELS_PER_CATEGORY:
            raise RuntimeError("Maximum number of channels in category reached (50)")
        channel = FakeChannel(self._next_channel_id, name, category)
        self._next_channel_id += 1
        self.created_channels += 1
        category.text_channels.append(channel)
        return channel


def _fill(category: FakeCategory, count: int, *, start_id: int = 1000) -> None:
    for index in range(count):
        category.text_channels.append(
            FakeChannel(start_id + index, f"unrelated-{index}", category)
        )


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "tradysquid.db")
    database.initialize()
    return database


def test_full_category_reuses_matching_channel_elsewhere(tmp_path: Path) -> None:
    intended = FakeCategory(1, "LEARNING CENTER")
    _fill(intended, MAX_CHANNELS_PER_CATEGORY)
    other = FakeCategory(2, "OLD BOT CHANNELS")
    existing = FakeChannel(9001, "learning-search", other)
    other.text_channels.append(existing)
    guild = FakeGuild([intended, other])
    schema = {
        "categories": [
            {"name": "LEARNING CENTER", "channels": ["learning-search"]}
        ]
    }

    service = DiscordStructureService(schema, database=_database(tmp_path))
    receipt = asyncio.run(service.sync(guild))

    assert receipt[0]["action"] == "channel-reused-other-category"
    assert receipt[0]["id"] == "9001"
    assert receipt[0]["actual_category"] == "OLD BOT CHANNELS"
    assert guild.created_channels == 0
    assert guild.created_categories == 0


def test_full_category_uses_deterministic_overflow_and_second_run_is_idempotent(
    tmp_path: Path,
) -> None:
    intended = FakeCategory(1, "LEARNING CENTER")
    _fill(intended, MAX_CHANNELS_PER_CATEGORY)
    guild = FakeGuild([intended])
    lessons = [f"{index:02d}-lesson" for index in range(1, 28)] + [
        "examples-and-reviews",
        "learning-search",
    ]
    schema = {"categories": [{"name": "LEARNING CENTER", "channels": lessons}]}
    service = DiscordStructureService(schema, database=_database(tmp_path))

    first = asyncio.run(service.sync(guild))
    first_category_count = len(guild.categories)
    first_channel_count = len(guild.text_channels)
    second = asyncio.run(service.sync(guild))

    overflow = next(category for category in guild.categories if category.name == "LEARNING CENTER 2")
    assert len(overflow.text_channels) == len(lessons)
    assert {channel.name for channel in overflow.text_channels} == set(lessons)
    assert sum(item["action"] == "channel-created" for item in first) == len(lessons)
    assert sum(item["action"] == "channel-created" for item in second) == 0
    assert len(guild.categories) == first_category_count
    assert len(guild.text_channels) == first_channel_count
    assert guild.created_categories == 1
    assert guild.created_channels == len(lessons)


def test_duplicate_historical_channels_are_reported_not_recreated(tmp_path: Path) -> None:
    intended = FakeCategory(1, "SYSTEM")
    other = FakeCategory(2, "OLD SYSTEM")
    intended.text_channels.append(FakeChannel(10, "system-health", intended))
    other.text_channels.append(FakeChannel(11, "system-health", other))
    guild = FakeGuild([intended, other])
    schema = {"categories": [{"name": "SYSTEM", "channels": ["system-health"]}]}

    receipt = asyncio.run(
        DiscordStructureService(schema, database=_database(tmp_path)).sync(guild)
    )

    assert receipt[0]["id"] == "10"
    assert receipt[0]["duplicate_count"] == 1
    assert receipt[0]["duplicate_channel_ids"] == ["11"]
    assert guild.created_channels == 0
    assert len([channel for channel in guild.text_channels if channel.name == "system-health"]) == 2


def test_saved_sqlite_mapping_wins_deterministically(tmp_path: Path) -> None:
    database = _database(tmp_path)
    intended = FakeCategory(1, "SYSTEM")
    other = FakeCategory(2, "OLD SYSTEM")
    first = FakeChannel(10, "diagnostics", intended)
    second = FakeChannel(11, "diagnostics", other)
    intended.text_channels.append(first)
    other.text_channels.append(second)
    guild = FakeGuild([intended, other])
    schema = {"categories": [{"name": "SYSTEM", "channels": ["diagnostics"]}]}
    service = DiscordStructureService(schema, database=database)

    asyncio.run(service.sync(guild))
    database.execute(
        "UPDATE settings SET value_json=? WHERE key=?",
        (
            '{"channel_id":"11","channel_name":"diagnostics"}',
            "discord.channel.diagnostics",
        ),
    )
    receipt = asyncio.run(service.sync(guild))

    assert receipt[0]["id"] == "11"
    rows = database.query(
        "SELECT key,value_json FROM settings WHERE key=?",
        ("discord.channel.diagnostics",),
    )
    assert len(rows) == 1
