from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import strategy_control_cards
import strategy_control_sync
import strategy_profiles


class FakeTracker:
    def __init__(self) -> None:
        self.ready = True
        self.guild_id = "guild"
        self.channels: list[dict] = []
        self.messages: dict[str, list[dict]] = {}
        self.requests: list[tuple[str, str, object]] = []
        self.next_id = 100

    def _id(self) -> str:
        self.next_id += 1
        return str(self.next_id)

    def _request(self, method: str, path: str, payload=None):
        self.requests.append((method, path, payload))
        if method == "GET" and path == "/guilds/guild/channels":
            return list(self.channels)
        if method == "GET" and path == "/users/@me":
            return {"id": "bot", "bot": True}
        if method == "POST" and path == "/guilds/guild/channels":
            item = dict(payload or {})
            item["id"] = self._id()
            self.channels.append(item)
            return item
        if method == "PATCH" and path.startswith("/channels/") and "/messages/" not in path:
            channel_id = path.split("/")[2]
            item = next(channel for channel in self.channels if channel["id"] == channel_id)
            item.update(payload or {})
            return item
        if method == "PUT" and "/permissions/" in path:
            return {}
        if method == "GET" and path.endswith("/messages?limit=100"):
            channel_id = path.split("/")[2]
            return list(self.messages.get(channel_id, []))
        if method == "POST" and path.endswith("/messages"):
            channel_id = path.split("/")[2]
            message = dict(payload or {})
            message.update({"id": self._id(), "author": {"id": "bot", "bot": True}})
            self.messages.setdefault(channel_id, []).insert(0, message)
            return message
        if method == "PATCH" and "/messages/" in path:
            parts = path.split("/")
            channel_id, message_id = parts[2], parts[4]
            message = next(
                item for item in self.messages[channel_id] if item["id"] == message_id
            )
            message.update(payload or {})
            return message
        if method == "DELETE" and "/messages/" in path:
            parts = path.split("/")
            channel_id, message_id = parts[2], parts[4]
            self.messages[channel_id] = [
                item for item in self.messages[channel_id] if item["id"] != message_id
            ]
            return None
        raise AssertionError(f"Unhandled fake Discord request: {method} {path}")


class StrategyControlSyncTests(unittest.TestCase):
    def test_private_overwrites_deny_members_and_allow_bot(self) -> None:
        overwrites = strategy_control_sync.permission_overwrites("guild", "bot")
        self.assertEqual(overwrites[0]["id"], "guild")
        self.assertEqual(
            overwrites[0]["deny"], str(strategy_control_sync.VIEW_CHANNEL)
        )
        self.assertEqual(overwrites[1]["id"], "bot")
        self.assertTrue(
            int(str(overwrites[1]["allow"])) & strategy_control_sync.VIEW_CHANNEL
        )
        self.assertTrue(
            int(str(overwrites[1]["allow"])) & strategy_control_sync.SEND_MESSAGES
        )

    def test_sync_creates_private_channels_and_six_singleton_cards(self) -> None:
        tracker = FakeTracker()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            strategy_control_sync,
            "STATE_PATH",
            Path(directory) / "strategy-control-sync.json",
        ):
            result = strategy_control_sync.sync_once(tracker)
            self.assertEqual(result["status"], "OK")
            self.assertTrue(result["read_only"])
            self.assertFalse(result["updater_involved"])
            self.assertEqual(
                set(result["channels"]), set(strategy_control_sync.CHANNEL_SPECS)
            )
            self.assertEqual(
                set(result["cards"]), set(strategy_profiles.PROFILE_IDENTITIES)
            )
            control_id = result["channels"]["strategy-control"]
            self.assertEqual(len(tracker.messages[control_id]), 6)
            self.assertTrue(strategy_control_sync.STATE_PATH.exists())
            category = next(
                item
                for item in tracker.channels
                if item.get("name") == strategy_control_sync.CATEGORY_NAME
            )
            self.assertEqual(category["type"], 4)
            for name in strategy_control_sync.CHANNEL_SPECS:
                channel = next(item for item in tracker.channels if item.get("name") == name)
                self.assertEqual(channel.get("parent_id"), category["id"])

    def test_second_sync_updates_cards_without_duplicates(self) -> None:
        tracker = FakeTracker()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            strategy_control_sync,
            "STATE_PATH",
            Path(directory) / "strategy-control-sync.json",
        ):
            first = strategy_control_sync.sync_once(tracker)
            second = strategy_control_sync.sync_once(tracker)
            control_id = second["channels"]["strategy-control"]
            self.assertEqual(len(tracker.messages[control_id]), 6)
            self.assertEqual(set(first["cards"]), set(second["cards"]))
            patch_calls = [
                item
                for item in tracker.requests
                if item[0] == "PATCH" and "/messages/" in item[1]
            ]
            self.assertEqual(len(patch_calls), 6)

    def test_pr_one_cards_have_no_write_components(self) -> None:
        cards = strategy_control_cards.all_profile_cards()
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(not card.get("components") for card in cards))
        self.assertTrue(
            all("Read-only" in str(card.get("description")) for card in cards)
        )

    def test_contract_validation_is_read_only(self) -> None:
        result = strategy_control_sync.validate_contract()
        self.assertTrue(result["read_only"])
        self.assertEqual(result["profiles"], 6)
        self.assertEqual(
            set(result["channels"]), set(strategy_control_sync.CHANNEL_SPECS)
        )


if __name__ == "__main__":
    unittest.main()
