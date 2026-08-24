from __future__ import annotations

import unittest
from pathlib import Path

import discord_reconciliation_safety as safety


ROOT = Path(__file__).resolve().parent


class DiscordReconciliationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        safety.install()

    def test_safety_contract_reports_upsert_only(self) -> None:
        result = safety.validate_contract()
        self.assertFalse(result["destructive_purge_enabled"])
        self.assertEqual(result["replacement_mode"], "upsert-only")
        self.assertTrue(result["existing_messages_preserved"])
        self.assertFalse(result["updater_involved"])

if __name__ == "__main__":
    unittest.main()
