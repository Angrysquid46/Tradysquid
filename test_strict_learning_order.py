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
        self.payloads: list[list[dict[str, Any]]] = []
        self.category = {
            "id": "category-1",
            "name": "LEARNING CENTER",
            "type": 4,
            "position": 20,
        }
        canonical = list(LEARNING_CHANNEL_ORDER)
        names = [
            canonical[0],
            canonical[17],
            canonical[1],
            "custom-notes",
            *canonical[2:17],
            *canonical[18:],
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
            self.payloads.append(payload)
            for item in payload:
                unexpected = set(item) - {"id", "position"}
                if unexpected:
                    raise AssertionError(
                        f"Discord 40009 risk: unexpected batch fields {unexpected}"
                    )
            if self.ignore_first_patch and self.patch_count == 1:
                return self.channels
            positions = {str(item["id"]): int(item["position"]) for item in payload}
            for channel in self.channels:
                channel_id = str(channel["id"])
                if channel_id in positions:
                    channel["position"] = positions[channel_id]
            return self.channels
        raise AssertionError(f"Unexpected request: {method} {path}")


class StrictLearningOrderTests(unittest.TestCase):
    def test_orders_ascending_01_through_27_and_moves_extras_last(self) -> None:
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
        lesson_numbers = [
            int(name[:2])
            for name in names
            if len(name) > 2 and name[:2].isdigit()
        ]
        self.assertEqual(lesson_numbers, list(range(1, 28)))
        self.assertEqual(names[-1], "custom-notes")
        self.assertEqual(result["canonical"], len(LEARNING_CHANNEL_ORDER))
        self.assertEqual(result["extras"], 1)
        self.assertEqual(result["attempts"], 1)
        self.assertTrue(result["changed"])
        self.assertEqual(min(item["position"] for item in tracker.channels), 40)

    def test_batch_payload_changes_positions_only(self) -> None:
        tracker = FakeTracker()
        enforce_learning_channel_order(tracker, attempts=1, retry_delay_seconds=0)
        self.assertEqual(len(tracker.payloads), 1)
        self.assertTrue(tracker.payloads[0])
        self.assertTrue(all(set(item) == {"id", "position"} for item in tracker.payloads[0]))

    def test_refetches_and_retries_when_discord_ignores_first_patch(self) -> None:
        tracker = FakeTracker(ignore_first_patch=True)
        result = enforce_learning_channel_order(tracker, attempts=3, retry_delay_seconds=0)
        self.assertEqual(tracker.patch_count, 2)
        self.assertEqual(result["attempts"], 2)
        self.assertTrue(result["changed"])

    def test_already_correct_order_is_verified_without_rewriting_discord(self) -> None:
        tracker = FakeTracker()
        first = enforce_learning_channel_order(tracker, attempts=1, retry_delay_seconds=0)
        second = enforce_learning_channel_order(tracker, attempts=1, retry_delay_seconds=0)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(tracker.patch_count, 1)


if __name__ == "__main__":
    unittest.main()
