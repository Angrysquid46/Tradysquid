from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import automation_acceptance as acceptance
from learning_center_catalog import LEARNING_CHANNEL_ORDER


class AutomationAcceptanceTests(unittest.TestCase):
    def test_heartbeat_must_be_fresh(self) -> None:
        fresh = {
            "supervisor_heartbeat_at": datetime.now().astimezone().isoformat(timespec="seconds")
        }
        stale = {
            "supervisor_heartbeat_at": (
                datetime.now().astimezone() - timedelta(minutes=10)
            ).isoformat(timespec="seconds")
        }
        self.assertTrue(acceptance.heartbeat_fresh(fresh))
        self.assertFalse(acceptance.heartbeat_fresh(stale))
        self.assertFalse(acceptance.heartbeat_fresh({}))

    def test_visible_order_requires_ascending_01_through_27(self) -> None:
        tracker = Mock(enabled=True)
        children = [
            {
                "id": f"id-{index}",
                "name": name,
                "position": index,
                "type": 0,
                "parent_id": "category",
            }
            for index, name in enumerate(LEARNING_CHANNEL_ORDER)
        ]
        with (
            patch.object(acceptance.spy_scanner, "DiscordTracker", return_value=tracker),
            patch.object(
                acceptance,
                "category_and_children",
                return_value=({"id": "category"}, children),
            ),
        ):
            result = acceptance.verify_visible_learning_order()
        self.assertEqual(result["numbers"], list(range(1, 28)))

    def test_visible_order_rejects_one_and_seventeen_swapped(self) -> None:
        names = list(LEARNING_CHANNEL_ORDER)
        names[1], names[17] = names[17], names[1]
        children = [
            {
                "id": f"id-{index}",
                "name": name,
                "position": index,
                "type": 0,
                "parent_id": "category",
            }
            for index, name in enumerate(names)
        ]
        tracker = Mock(enabled=True)
        with (
            patch.object(acceptance.spy_scanner, "DiscordTracker", return_value=tracker),
            patch.object(
                acceptance,
                "category_and_children",
                return_value=({"id": "category"}, children),
            ),
        ):
            with self.assertRaisesRegex(
                acceptance.AcceptanceFailure,
                "wrong Learning Center order",
            ):
                acceptance.verify_visible_learning_order()

    def test_status_logic_must_generate_online_response(self) -> None:
        with patch.object(
            acceptance.command_bot,
            "status_reply",
            return_value="🩺 **SPY Tradysquids status**\nCommand service: **ONLINE**",
        ):
            result = acceptance.verify_status_logic()
        self.assertEqual(result["ticker"], "SPY")


if __name__ == "__main__":
    unittest.main()
