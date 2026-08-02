from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

import ford_scan
import performance_channel_structure
import performance_reconciliation as reconciliation
import sync_discord_structure as structure


class FakeDiscord:
    def __init__(self) -> None:
        self.ready = True
        self.channels = {
            "daily_recap": "daily",
            "weekly_report": "weekly",
            "performance_stats": "monthly",
            "strategy_breakdown": "strategy",
        }
        self.cards: dict[str, str] = {}
        self.channel_cards: dict[str, list[str]] = {
            channel_id: [] for channel_id in self.channels.values()
        }
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
        self.channel_cards[self.channels[logical_name]].append(content)
        state.setdefault("messages", {})[state_key] = f"message-{len(self.cards)}"
        return state["messages"][state_key]

    def _request(self, method, path, payload=None):
        if method == "GET":
            return []
        if method == "DELETE":
            self.deleted.append(path)
            return None
        raise AssertionError((method, path, payload))


class PerformanceReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reconciliation.install()

    def make_rows(self, count: int = 100) -> list[dict[str, str]]:
        rows = []
        monday = datetime(2026, 7, 27, 14, 30, tzinfo=ford_scan.MARKET_TZ)
        strategies = (
            ("REGULAR", "call"),
            ("REGULAR", "put"),
            ("SWING", "call"),
            ("SWING", "put"),
            ("SPREAD", "call"),
        )
        for index in range(count):
            closed_at = monday + timedelta(days=index % 5, minutes=index)
            play_type, side = strategies[index % len(strategies)]
            outcome = "WIN" if index % 3 else "LOSS"
            row = ford_scan.blank_row()
            row.update(
                {
                    "trade_id": f"F-TEST-{index + 1:03d}",
                    "timestamp": (closed_at - timedelta(hours=2)).isoformat(),
                    "closed_at": "" if index == 49 else closed_at.isoformat(),
                    "last_evaluated_at": closed_at.isoformat(),
                    "outcome": outcome,
                    "play_type": play_type,
                    "call_or_put": side,
                    "ticker": "F",
                    "strike": "12/11" if play_type == "SPREAD" else "12",
                    "entry_price": "0.50",
                    "exit_price": "0.60" if outcome == "WIN" else "0.40",
                    "cost_or_credit": "0.50 debit",
                    "realized_pl_dollars": "10" if outcome == "WIN" else "-10",
                    "pct_gain_loss": "20" if outcome == "WIN" else "-20",
                }
            )
            rows.append(row)
        return rows

    def test_four_distinct_discord_routes_are_installed(self) -> None:
        self.assertEqual(ford_scan.CHANNEL_NAMES["daily_recap"], "daily-recap")
        self.assertEqual(ford_scan.CHANNEL_NAMES["weekly_report"], "weekly-report")
        self.assertEqual(
            ford_scan.CHANNEL_NAMES["performance_stats"], "performance-dashboard"
        )
        self.assertEqual(
            ford_scan.CHANNEL_NAMES["strategy_breakdown"], "strategy-breakdown"
        )

    def test_structure_contains_each_report_channel_once(self) -> None:
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

    def test_one_hundred_trades_appear_in_every_reporting_view(self) -> None:
        rows = self.make_rows()
        discord = FakeDiscord()
        state: dict = {}
        reconciliation.sync_reports(
            discord,
            state,
            rows,
            datetime(2026, 8, 1, 21, 0, tzinfo=ford_scan.MARKET_TZ),
            market_open=False,
        )

        self.assertEqual(state["performance_reconciliation_closed_trades"], 100)
        self.assertEqual(state["performance_reconciliation_daily_reports"], 5)
        self.assertEqual(state["performance_reconciliation_weekly_reports"], 1)
        self.assertEqual(state["performance_reconciliation_strategy_groups"], 5)
        self.assertEqual(state["performance_reconciliation_monthly_reports"], 1)
        self.assertEqual(
            state["performance_reconciliation_version"], reconciliation.REPORT_VERSION
        )

        for channel_id in ("daily", "weekly", "monthly", "strategy"):
            rendered = "\n".join(discord.channel_cards[channel_id])
            self.assertIn("100/100", rendered)
            for sequence in (1, 25, 50, 75, 100):
                self.assertIn(f"F-TEST-{sequence:03d}", rendered)

        monthly = "\n".join(discord.channel_cards["monthly"])
        self.assertIn("Monthly Performance · July 2026", monthly)
        self.assertNotIn("Weekly Report ·", monthly)

    def test_daily_and_weekly_totals_reconcile_exactly(self) -> None:
        rows = self.make_rows()
        monday = date(2026, 7, 27)
        daily = sum(
            len(reconciliation.rows_closed_on(rows, monday + timedelta(days=index)))
            for index in range(5)
        )
        weekly = len(
            reconciliation.rows_closed_between(rows, monday, monday + timedelta(days=4))
        )
        self.assertEqual(daily, 100)
        self.assertEqual(weekly, 100)

    def test_missing_closed_at_uses_last_evaluated_timestamp(self) -> None:
        rows = self.make_rows()
        row = rows[49]
        self.assertFalse(row["closed_at"])
        self.assertEqual(
            reconciliation.effective_closed_at(row),
            ford_scan.parse_iso(row["last_evaluated_at"]),
        )

    def test_ledger_signature_changes_with_trade_result(self) -> None:
        rows = self.make_rows(1)
        first = reconciliation.ledger_signature(rows)
        rows[0]["realized_pl_dollars"] = "25"
        second = reconciliation.ledger_signature(rows)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
