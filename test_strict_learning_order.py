from __future__ import annotations

import unittest
from typing import Any

from learning_center_catalog import LEARNING_CHANNEL_ORDER
from strict_learning_order import enforce_learning_channel_order, normalized


class FakeTracker:
    guild_id = "guild-1"

    def __init__(self, *, ignore_first_patch: bool = False) -> None:
        self.ignore_first_patch = ignore_first_patch
        self.patch_count = 0
        self.category = {
            "id": "category-1",
            "name": "LEARNING CENTER",
            "type": 4,
            "position": 20,
        }
        names = [
            "learning-index",
            "17-directional-options",
            "01-stock-market-foundations",
            "custom-notes",
            *LEARNING_CHANNEL_ORDER[2:],
        ]
        self.channels: list[dict[str, Any]] = []
        for index, name in enumerate(names):
            self.channels.append(
                {
                    "id": f"channel-{index:02d}",
                    "name": name,
                    "type": 0,
                    "position": 40 + index,
                    "parent_id": self.category["id"],
                }
            )

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        if method == "GET" and path == f"/guilds/{self.guild_id}/channels":
            return [self.category, *self.channels]
        if method == "PATCH" and path == f"/guilds/{self.guild_id}/channels":
            self.patch_count += 1
            if self.ignore_first_patch and self.patch_count == 1:
                return self.channels
            positions = {
                str(item["id"]): int(item["position"])
                for item in payload
            }
            for channel in self.channels:
                channel_id = str(channel["id"])
                if channel_id in positions:
                    channel["position"] = positions[channel_id]
                    channel["parent_id"] = self.category["id"]
            return self.channels
        raise AssertionError(f"Unexpected request: {method} {path}")


class StrictLearningOrderTests(unittest.TestCase):
    def test_orders_all_canonical_channels_and_moves_extras_last(self) -> None:
        tracker = FakeTracker()
        result = enforce_learning_channel_order(
            tracker,
            attempts=1,
            retry_delay_seconds=0,
        )
        ordered = sorted(
            tracker.channels,
            key=lambda item: (int(item["position"]), str(item["id"])),
        )
        names = [normalized(item["name"]) for item in ordered]
        self.assertEqual(names[: len(LEARNING_CHANNEL_ORDER)], list(LEARNING_CHANNEL_ORDER))
        self.assertEqual(names[-1], "custom-notes")
        self.assertEqual(result["canonical"], len(LEARNING_CHANNEL_ORDER))
        self.assertEqual(result["extras"], 1)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(min(item["position"] for item in tracker.channels), 40)

    def test_refetches_and_retries_when_discord_ignores_first_patch(self) -> None:
        tracker = FakeTracker(ignore_first_patch=True)
        result = enforce_learning_channel_order(
            tracker,
            attempts=3,
            retry_delay_seconds=0,
        )
        self.assertEqual(tracker.patch_count, 2)
        self.assertEqual(result["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
