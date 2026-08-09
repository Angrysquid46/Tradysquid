from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

import discord_reconciliation_safety as safety
import spy_scanner
import performance_scorecards as scorecards


ROOT = Path(__file__).resolve().parent


class NoDeleteDiscord:
    def __init__(self) -> None:
        self.ready = True
        self.channels = {
            "daily_recap": "daily",
            "weekly_report": "weekly",
            "performance_stats": "monthly",
            "strategy_breakdown": "strategy",
        }
        self.cards: dict[str, str] = {}
        self.deleted: list[str] = []

    def upsert_channel_message(
        self,
        logical_name,
        state,
        state_key,
        content,
        search_token="",
    ):
        self.cards[state_key] = content
        message_id = f"message-{len(self.cards)}"
        state.setdefault("messages", {})[state_key] = message_id
        return message_id

    def _request(self, method, path, payload=None):
        if method == "DELETE":
            self.deleted.append(path)
            raise AssertionError("Discord reconciliation attempted a destructive delete")
        if method == "GET":
            return []
        raise AssertionError((method, path, payload))


class DiscordReconciliationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        scorecards.install()
        safety.install()

    def make_closed_row(self) -> dict[str, str]:
        closed_at = datetime(2026, 8, 1, 14, 30, tzinfo=spy_scanner.MARKET_TZ)
        row = spy_scanner.blank_row()
        row.update(
            {
                "trade_id": "F-SAFETY-001",
                "timestamp": closed_at.isoformat(),
                "closed_at": closed_at.isoformat(),
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": "WIN",
                "play_type": "REGULAR",
                "call_or_put": "call",
                "ticker": "F",
                "strike": "12",
                "entry_price": "0.50",
                "exit_price": "0.60",
                "realized_pl_dollars": "10",
                "pct_gain_loss": "20",
            }
        )
        return row

    def test_legacy_purge_entry_points_are_disabled(self) -> None:
        discord = NoDeleteDiscord()
        self.assertEqual(scorecards._purge_old_report_cards(discord), 0)
        self.assertEqual(scorecards.base._purge_report_channel(discord, "daily_recap"), 0)
        self.assertEqual(discord.deleted, [])

    def test_version_change_rebuild_uses_upserts_without_deletes(self) -> None:
        discord = NoDeleteDiscord()
        state: dict = {}
        scorecards.sync_reports(
            discord,
            state,
            [self.make_closed_row()],
            datetime(2026, 8, 2, 17, 30, tzinfo=spy_scanner.MARKET_TZ),
            market_open=False,
        )
        self.assertEqual(discord.deleted, [])
        self.assertTrue(discord.cards)
        self.assertEqual(state["performance_reconciliation_version"], scorecards.REPORT_VERSION)
        self.assertEqual(state["performance_reconciliation_removed_misplaced_cards"], 0)

    def test_safety_contract_reports_upsert_only(self) -> None:
        result = safety.validate_contract()
        self.assertFalse(result["destructive_purge_enabled"])
        self.assertEqual(result["replacement_mode"], "upsert-only")
        self.assertTrue(result["existing_messages_preserved"])
        self.assertFalse(result["updater_involved"])

    def test_information_engine_installs_safety_before_acceptance(self) -> None:
        text = (ROOT / "local_information_engine_bootstrap.py").read_text(
            encoding="utf-8"
        )
        install_index = text.index("discord_reconciliation_safety.install()")
        acceptance_index = text.index("def run_required_startup_jobs")
        self.assertLess(install_index, acceptance_index)
        self.assertIn("discord_reconciliation_safety.validate_contract()", text)


if __name__ == "__main__":
    unittest.main()
