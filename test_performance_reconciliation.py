from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

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
            "monthly_recap": "monthly-dashboard",
            "performance_1m": "strategies-dashboard",
            "results_1m": "strategies-results",
            "performance_5m": "strategies-dashboard",
            "results_5m": "strategies-results",
            "performance_key_levels": "strategies-dashboard",
            "results_key_levels": "strategies-results",
            "performance_expansion": "strategies-dashboard",
            "results_expansion": "strategies-results",
            "strategy_leaderboard": "strategies-dashboard",
        }
        for variant in spy_scanner.SPY_RATCHET_VARIANTS:
            suffix = variant["play_type"].removeprefix("SPY_RATCHET_").lower()
            self.channels[f"performance_ratchet_{suffix}"] = f"monthly-ratchet-{suffix.replace('_', '-')}"
            self.channels[f"results_ratchet_{suffix}"] = f"strategy-ratchet-{suffix.replace('_', '-')}"
        self.channels["ratchet_leaderboard"] = "ratchet-dashboard"
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
                "strategies-dashboard": [self.old_message("old-monthly-1m", "1-Minute Strategy Monthly Trade History · July 2026")],
                "strategies-results": [self.old_message("old-strategy-1m", "1-Minute Strategy Trade History · SPY_0DTE_1M CALL")],
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
        self.assertEqual(spy_scanner.CHANNEL_NAMES["monthly_recap"], "monthly-dashboard")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["performance_1m"], "strategies-dashboard")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["results_1m"], "strategies-results")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["performance_5m"], "strategies-dashboard")
        self.assertEqual(spy_scanner.CHANNEL_NAMES["results_5m"], "strategies-results")

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
        # Combined-across-everything #monthly-dashboard: July (actual trades)
        # + August ("today" placeholder) = 2, same as either SPY_0DTE variant
        # alone since all synthetic trades close within the same July week.
        self.assertEqual(state["performance_reconciliation_monthly_dashboard_reports"], 2)
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
        # One combined results card per variant that actually has trades
        # (1m, 5m) - SPY_KEY_LEVELS/SPY_EXPANSION_LEVEL/ratchets have none
        # in this synthetic ledger, contributing 0 each.
        self.assertEqual(state["performance_reconciliation_strategy_groups"], 2)
        self.assertEqual(state["performance_reconciliation_history_pages"], 0)
        self.assertTrue(state["performance_reconciliation_scorecard_only"])
        self.assertEqual(len(discord.deleted), 0)
        self.assertEqual(
            state["performance_reconciliation_removed_misplaced_cards"], 0
        )

        self.assertEqual(len(discord.channel_cards["daily"]), 5)
        self.assertEqual(len(discord.channel_cards["weekly"]), 1)
        self.assertEqual(len(discord.channel_cards["monthly-dashboard"]), 2)
        # 1-Minute/5-Minute/Key-Levels/Expansion-Level now share one
        # dashboard channel: 1m(2 months) + 5m(2 months) + key-levels(1
        # empty "current month" placeholder) + expansion(1 empty
        # placeholder) + 1 leaderboard card = 7.
        self.assertEqual(len(discord.channel_cards["strategies-dashboard"]), 7)
        # And one shared results channel: one combined card per strategy
        # (even a trade-less one still posts an empty scorecard) - owner
        # ask: the split-by-side cards read as duplicates sitting in the
        # same channel even though they were technically different groups.
        self.assertEqual(len(discord.channel_cards["strategies-results"]), 4)

        rendered = "\n".join(discord.cards.values())
        self.assertNotIn("Trade History", rendered)
        self.assertNotIn("Performance Index", rendered)
        self.assertNotIn("Page 1/", rendered)

        # The two variants must never bleed into each other's results card,
        # even though they now share a channel - checked by state_key
        # (each variant's own tracked card), not by channel, since the
        # channel itself no longer distinguishes them.
        strategy_1m_text = discord.cards["report-v5:results:results_1m:combined"]
        strategy_5m_text = discord.cards["report-v5:results:results_5m:combined"]
        self.assertIn("Strategy Scorecard · 1-Minute Strategy", strategy_1m_text)
        # Combined across both call and put trades for this variant (25 of
        # each in the synthetic ledger).
        self.assertIn("**Closed trades:** **50**", strategy_1m_text)
        self.assertNotIn("SPY_0DTE_5M", strategy_1m_text)
        self.assertIn("Strategy Scorecard · 5-Minute Strategy", strategy_5m_text)
        self.assertIn("**Closed trades:** **50**", strategy_5m_text)
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

    def test_top_strategies_ranks_by_net_pl_and_ignores_side(self) -> None:
        # Owner ask: track which strategies actually perform best over
        # time. Grouped by play_type alone (not call/put side) - matches
        # the "one combined card per strategy" pattern already used for
        # results channels, not a side-by-side split.
        base = scorecards.base
        monday = datetime(2026, 7, 27, 14, 30, tzinfo=spy_scanner.MARKET_TZ)

        def make(trade_id, play_type, side, dollars, pct):
            row = spy_scanner.blank_row()
            row.update(
                {
                    "trade_id": trade_id,
                    "timestamp": (monday - timedelta(hours=1)).isoformat(),
                    "closed_at": monday.isoformat(),
                    "outcome": "WIN" if dollars > 0 else "LOSS",
                    "play_type": play_type,
                    "call_or_put": side,
                    "ticker": "SPY",
                    "realized_pl_dollars": str(dollars),
                    "pct_gain_loss": str(pct),
                }
            )
            return row

        rows = [
            make("T1", "SPY_RATCHET_29_16", "put", 44, 6),
            make("T2", "SPY_KEY_LEVELS", "call", 104, 25),
            make("T2b", "SPY_KEY_LEVELS", "put", -60, -19),
            make("T3", "SPY_RATCHET_26_16", "put", 32, 4),
            make("T4", "SPY_0DTE_5M", "call", 5, 1),
        ]
        lines = base.top_strategies_lines(rows)
        self.assertEqual(lines[0], "### Top Strategies")
        # KEY_LEVELS net = 104-60 = 44, tied with T1's 44 on raw net, but
        # dict ordering/sort stability aside, both call+put sides must be
        # combined under one KEY_LEVELS entry, not split.
        joined = "\n".join(lines)
        self.assertIn("SPY_KEY_LEVELS", joined)
        self.assertIn("SPY_RATCHET_29_16", joined)
        self.assertIn("SPY_RATCHET_26_16", joined)
        self.assertNotIn("SPY_0DTE_5M", joined)  # 4th place, past the top-3 limit
        self.assertEqual(len(lines), 4)  # header + top 3
        self.assertIn("🥇", lines[1])
        self.assertIn("🥈", lines[2])
        self.assertIn("🥉", lines[3])

    def test_top_strategies_empty_when_nothing_closed(self) -> None:
        self.assertEqual(scorecards.base.top_strategies_lines([]), [])

    def test_daily_recap_includes_top_strategies_section(self) -> None:
        rows = self.make_rows()
        report_date = date(2026, 7, 27)
        content = scorecards.base.format_daily_recap(rows, report_date, market_open=False)
        self.assertIn("### Top Strategies", content)

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
