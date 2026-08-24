from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import automation_acceptance as acceptance


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


if __name__ == "__main__":
    unittest.main()
