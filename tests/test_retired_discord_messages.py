from __future__ import annotations

import asyncio

from tradysquid.discord.retired import retire_stable_messages


class FakeDatabase:
    def __init__(self, rows):
        self.rows = list(rows)
        self.deleted: list[str] = []

    def query(self, sql: str, parameters=()):
        assert "discord_message_state" in sql
        assert parameters == ("shadow-candidates",)
        return list(self.rows)

    def execute(self, sql: str, parameters=()):
        assert sql.startswith("DELETE FROM discord_message_state")
        self.deleted.append(str(parameters[0]))


class FakeAuthor:
    def __init__(self, author_id: str):
        self.id = author_id


class FakeMessage:
    def __init__(self, author_id: str):
        self.author = FakeAuthor(author_id)
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeChannel:
    def __init__(self, channel_id: int, message: FakeMessage):
        self.id = channel_id
        self.message = message

    async def fetch_message(self, message_id: int):
        assert message_id == 200
        return self.message


class FakeGuild:
    def __init__(self, channel=None):
        self.channel = channel

    def get_channel(self, channel_id: int):
        if self.channel is not None and self.channel.id == channel_id:
            return self.channel
        return None

    async def fetch_channel(self, channel_id: int):
        raise RuntimeError("channel not found")


def _row():
    return {
        "stable_id": "shadow-candidates",
        "channel_name": "100",
        "message_id": "200",
    }


def test_retired_bot_card_is_deleted_and_state_is_removed() -> None:
    message = FakeMessage("999")
    database = FakeDatabase([_row()])
    result = asyncio.run(
        retire_stable_messages(
            database,
            FakeGuild(FakeChannel(100, message)),
            bot_user_id="999",
        )
    )

    assert result["status"] == "PASS"
    assert result["deleted"][0]["stable_id"] == "shadow-candidates"
    assert message.deleted is True
    assert database.deleted == ["shadow-candidates"]


def test_retired_card_does_not_delete_human_message() -> None:
    message = FakeMessage("123")
    database = FakeDatabase([_row()])
    result = asyncio.run(
        retire_stable_messages(
            database,
            FakeGuild(FakeChannel(100, message)),
            bot_user_id="999",
        )
    )

    assert result["status"] == "DEGRADED"
    assert result["blocked"][0]["reason"] == "message-is-not-authored-by-this-bot"
    assert message.deleted is False
    assert database.deleted == []


def test_retired_state_is_removed_when_channel_is_already_absent() -> None:
    database = FakeDatabase([_row()])
    result = asyncio.run(
        retire_stable_messages(
            database,
            FakeGuild(),
            bot_user_id="999",
        )
    )

    assert result["status"] == "PASS"
    assert result["already_absent"][0]["stable_id"] == "shadow-candidates"
    assert database.deleted == ["shadow-candidates"]
