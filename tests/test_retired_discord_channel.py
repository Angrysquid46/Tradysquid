from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tradysquid.discord.structure import DiscordStructureService


ROOT = Path(__file__).resolve().parents[1]


class Author:
    id = 999
    bot = True


class Message:
    author = Author()


class Channel:
    def __init__(self, category):
        self.id = 9001
        self.name = "shadow-candidates"
        self.category = category
        self.type = "text"
        self.messages = [Message()]
        self.threads = []
        self.deleted = False

    async def delete(self, *, reason: str):
        self.deleted = True
        self.category.channels.remove(self)
        self.category.text_channels.remove(self)


class Category:
    def __init__(self):
        self.id = 10
        self.name = "LIVE TRADING DESK"
        self.channels = []
        self.text_channels = []
        self.forums = []


class Guild:
    def __init__(self, category):
        self.categories = [category]
        self.channels = category.channels
        self.text_channels = category.text_channels
        self.forums = []


def test_retired_shadow_channel_is_deleted_even_outside_invented_category() -> None:
    schema = json.loads(
        (ROOT / "config" / "discord-schema.json").read_text(encoding="utf-8")
    )
    category = Category()
    channel = Channel(category)
    category.channels.append(channel)
    category.text_channels.append(channel)
    service = DiscordStructureService(schema)

    result = asyncio.run(
        service.cleanup(
            Guild(category),
            protected_channel_ids=set(),
            bot_user_id="999",
        )
    )

    assert result["status"] == "PASS"
    assert channel.deleted is True
    assert result["deleted_channels"][0]["name"] == "shadow-candidates"
