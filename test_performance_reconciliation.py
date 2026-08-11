from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import discord_reconciliation_safety as safety
import spy_scanner
import performance_channel_structure
import performance_scorecards as scorecards
import sync_discord_structure as structure


class FakeDiscord:
    def __init__(self, *, include_old_cards: bool = False) -> None:
        self.ready = True
        self.channels = {
            "daily_recap": "daily",
            "weekly_report": "weekly",
            "performance_1m": "monthly-1m",
            "results_1m": "strategy-1m",
            "performance_5m": "monthly-5m",
            "results_5m": "strategy-5m",
            "performance_key_levels": "monthly-key-levels",
            "results_key_levels": "strategy-key-levels",
            "performance_expansion": "monthly-expansion",
            "results_expansion": "strategy-expansion",
        }
        for variant in spy_scanner.SPY_RATCHET_VARIANTS:
            suffix = variant["play_type"].removeprefix("SPY_RATCHET_").lower()
            self.channels[f"performance_ratchet_{suffix}"] = f"monthly-ratchet-{suffix.replace('_', '-')}"
            self.channels[f"results_ratchet_{suffix}"] = f"strategy-ratchet-{suffix.replace('_', '-')}"
        self.cards: dict[str, str] = {}
        self.channel_cards: dict[str, list[str]] = {
            channel_id: [] for channel_id in self.channels.values()
        }
        self.deleted: list[str] = []
        self.old_pages: dict[str, list[dict]] = {
            channel_id: [] for channel_id in self.channels.values()
        }
        if include_old_cards:
            self.old_pages = {
                "daily": [self.old_message("old-daily", "Daily Trade History · 07/29/26")],
                "weekly": [self.old_message("old-weekly", "Weekly Trade History · 07/27/26")],
                "monthly-1m": [self.old_message("old-monthly-1m", "1-Minute Strategy Monthly Trade History · July 2026")],
                "strategy-1m": [self.old_message("old-strategy-1m", "1-Minute Strategy Trade History · SPY_0DTE_1M CALL")],
                "monthly-5m": [],
                "strategy-5m": [],
            }

    @staticmethod
    def old_message(message_id: str, marker: str) -> dict:
        return {
            "id": message_id,
            "author": {"bot": True},
            "embeds": [{"description": marker}],
            "content": "",
        }

    def upsert_channel_message(
        self,
        logical_name,
        state,
        state_key,
        content,
        search_token="",
    ):
        self.cards[state_key] = content
        self.channel_cards[self.channels[logical_name]].append(content)
        state.setdefault("messages", {})[state_key] = f"message-{len(self.cards)}"
        return state["messages"][state_key]

    def _request(self, method, path, payload=None):
        if method == "GET":
            channel_id = path.split("/")[2]
            page = self.old_pages[channel_id]
            self.old_pages[channel_id] = []
            return page
        if method == "DELETE":
            self.deleted.append(path)
            return None
        raise AssertionError((method, path, payload))


class PerformanceScorecardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        scorecards.install()
        safety.install()

    def make_rows(self, count: int = 100) -> list[dict[str, str]]:
        rows = []
        monday = datetime(2026, 7, 27, 14, 30, tzinfo=spy_scanner.MARKET_TZ)
        strategies = (
            ("SPY_0DTE_1M", "call"),
            ("SPY_0DTE_1M", "put"),
            ("SPY_0DTE_5M", "call"),
            ("SPY_0DTE_5M", "put"),
        )
        for index in range(count):
            closed_at = monday + timedelta(days=index % 5, minutes=index)
            play_type, side = strategies[index % len(strategies)]
            outcome = "WIN" if index % 3 else "LOSS"
            row = spy_scanner.blank_row()
            row.update(
                {
                    "trade_id": f"SPY-TEST-{index + 1:03d}",
                    "timestamp": (closed_at - timedelta(hours=2)).isoformat(),
                    "closed_at": "" if index == 49 else closed_at.isoformat(),
                    "last_evaluated_at": closed_at.isoformat(),
                    "outcome": outcome,
                    "play_type": play_type,
                    "call_or_put": side,
                    "ticker": "SPY",
                    "strike": "600",
                    "entry_price": "0.50",
                    "exit_price": "0.60" if outcome == "WIN" else "0.40",
                    "cost_or_credit": "0.50 debit",
                    "realized_pl_dollars": "10" if outcome == "WIN" else "-10",
                    "pct_gain_loss": "20" if outcome == "WIN" else "-20",
                }
            )
            rows.append(row)
        return rows

    def test_six_distinct_discord_routes_are_installed(self) -> None:
        self.assertEqual(spy_scanner.CHANNEL_NAMES["daily_recap"], "daily-recap")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["weekly_report"], "weekly-report")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["performance_1m"], "1m-performance")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["results_1m"], "1m-results")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["performance_5m"], "5m-performance")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["results_5m"], "5m-results")

    def test_structure_contains_each_scorecard_channel_once(self) -> None:
        original = list(structure.CHANNELS)
        try:
            performance_channel_structure.install(structure)
            performance_channel_structure.validate(structure)
            names = [
                spec.name
                for spec in structure.CHANNELS
                if spec.category == "PERFORMANCE"
            ]
            for name, _ in performance_channel_structure.PERFORMANCE_CHANNELS:
                self.assertEqual(names.count(name), 1)
        finally:
            structure.CHANNELS = original

    def test_scoreboards_use_summary_cards_only(self) -> None:
        rows = self.make_rows()
        discord = FakeDiscord(include_old_cards=True)
        state: dict = {}
        scorecards.sync_reports(
            discord,
            state,
            rows,
            datetime(2026, 8, 1, 21, 30, tzinfo=spy_scanner.MARKET_TZ),
            market_open=False,
        )

        self.assertEqual(state["performance_reconciliation_closed_trades"], 100)
        self.assertEqual(state["performance_reconciliation_daily_reports"], 5)
        self.assertEqual(state["performance_reconciliation_weekly_reports"], 1)
        # 2 months (July from actual trades + August from "today") for EACH
        # of the two SPY_0DTE variants, plus 1 each for SPY_KEY_LEVELS and
        # SPY_EXPANSION_LEVEL - both have zero rows in make_rows()'s
        # synthetic ledger, but period_months() always includes the current
        # month as a placeholder even with no trades, so each trade-less
        # variant still contributes exactly one empty "current month"
        # scorecard: 2 + 2 + 1 + 1 = 6, plus 1 each for the 10 trade-less
        # ratchet-floor variants (same "current month" placeholder rule) =
        # 6 + 10 = 16.
        self.assertEqual(state["performance_reconciliation_monthly_reports"], 16)
        # CALL and PUT groups for EACH variant that actually has trades -
        # SPY_KEY_LEVELS has none in this synthetic ledger, so it
        # contributes 0 groups and this count is unaffected by its addition.
        self.assertEqual(state["performance_reconciliation_strategy_groups"], 4)
        self.assertEqual(state["performance_reconciliation_history_pages"], 0)
        self.assertTrue(state["performance_reconciliation_scorecard_only"])
        self.assertEqual(len(discord.deleted), 0)
        self.assertEqual(
            state["performance_reconciliation_removed_misplaced_cards"], 0
        )

        self.assertEqual(len(discord.channel_cards["daily"]), 5)
        self.assertEqual(len(discord.channel_cards["weekly"]), 1)
        self.assertEqual(len(discord.channel_cards["monthly-1m"]), 2)
        self.assertEqual(len(discord.channel_cards["monthly-5m"]), 2)
        self.assertEqual(len(discord.channel_cards["strategy-1m"]), 2)
        self.assertEqual(len(discord.channel_cards["strategy-5m"]), 2)

        rendered = "\n".join(discord.cards.values())
        self.assertNotIn("Trade History", rendered)
        self.assertNotIn("Performance Index", rendered)
        self.assertNotIn("Page 1/", rendered)

        # The two variants must never bleed into each other's results channel.
        strategy_1m_text = "\n".join(discord.channel_cards["strategy-1m"])
        strategy_5m_text = "\n".join(discord.channel_cards["strategy-5m"])
        self.assertIn("1-Minute Strategy · SPY_0DTE_1M CALL", strategy_1m_text)
        self.assertIn("1-Minute Strategy · SPY_0DTE_1M PUT", strategy_1m_text)
        self.assertNotIn("SPY_0DTE_5M", strategy_1m_text)
        self.assertIn("5-Minute Strategy · SPY_0DTE_5M CALL", strategy_5m_text)
        self.assertIn("5-Minute Strategy · SPY_0DTE_5M PUT", strategy_5m_text)
        self.assertNotIn("SPY_0DTE_1M", strategy_5m_text)

    def test_new_trading_week_starts_a_new_weekly_scorecard(self) -> None:
        rows = self.make_rows()
        discord = FakeDiscord()
        state = {"performance_reconciliation_version": scorecards.REPORT_VERSION}
        scorecards.sync_reports(
            discord,
            state,
            rows,
            datetime(2026, 8, 3, 7, 0, tzinfo=spy_scanner.MARKET_TZ),
            market_open=False,
        )
        self.assertEqual(len(discord.channel_cards["weekly"]), 2)
        latest = discord.channel_cards["weekly"][-1]
        self.assertIn("08/03", latest)
        self.assertIn("0W", latest)
        self.assertIn("0L", latest)
        self.assertNotIn("Trade History", latest)

    def test_play_type_normalization_handles_credit_names(self) -> None:
        row = {"play_type": "CALL CREDIT", "call_or_put": ""}
        self.assertEqual(scorecards.normalize_play_type(row), "SPREAD CALL")
        row = {"play_type": "PUT CREDIT", "call_or_put": ""}
        self.assertEqual(scorecards.normalize_play_type(row), "SPREAD PUT")

    def test_missing_closed_at_uses_last_evaluated_timestamp(self) -> None:
        rows = self.make_rows()
        row = rows[49]
        self.assertFalse(row["closed_at"])
        self.assertEqual(
            scorecards.base.effective_closed_at(row),
            spy_scanner.parse_iso(row["last_evaluated_at"]),
        )


if __name__ == "__main__":
    unittest.main()
