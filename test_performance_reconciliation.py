from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

import ford_scan
import performance_reconciliation as reconciliation


class FakeDiscord:
    def __init__(self) -> None:
        self.ready = True
        self.cards: dict[str, str] = {}

    def upsert_channel_message(
        self,
        logical_name,
        state,
        state_key,
        content,
        search_token="",
    ):
        self.cards[state_key] = content
        state.setdefault("messages", {})[state_key] = f"message-{len(self.cards)}"
        return state["messages"][state_key]


class PerformanceReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reconciliation.install()

    def make_row(
        self,
        sequence: int,
        closed_at: datetime,
        *,
        outcome: str,
        play_type: str = "REGULAR",
        side: str = "call",
        omit_closed_at: bool = False,
    ) -> dict[str, str]:
        row = ford_scan.blank_row()
        row.update(
            {
                "trade_id": f"F-TEST-{sequence:03d}",
                "timestamp": (closed_at - timedelta(hours=2)).isoformat(),
                "closed_at": "" if omit_closed_at else closed_at.isoformat(),
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": outcome,
                "play_type": play_type,
                "call_or_put": side,
                "ticker": "F",
                "strike": "12",
                "entry_price": "0.50",
                "exit_price": "0.60" if outcome == "WIN" else "0.40",
                "cost_or_credit": "0.50 debit",
                "realized_pl_dollars": "10" if outcome == "WIN" else "-10",
                "pct_gain_loss": "20" if outcome == "WIN" else "-20",
            }
        )
        return row

    def test_sync_backfills_each_weekday_and_reconciles_week_and_strategy(self) -> None:
        rows = []
        monday = date(2026, 7, 27)
        for index in range(5):
            rows.append(
                self.make_row(
                    index + 1,
                    datetime(
                        2026,
                        7,
                        27 + index,
                        14,
                        30,
                        tzinfo=ford_scan.MARKET_TZ,
                    ),
                    outcome="WIN" if index in {0, 2, 4} else "LOSS",
                    play_type="REGULAR" if index < 3 else "SWING",
                    side="call" if index % 2 == 0 else "put",
                    omit_closed_at=index == 2,
                )
            )

        discord = FakeDiscord()
        state: dict = {}
        reconciliation.sync_reports(
            discord,
            state,
            rows,
            datetime(2026, 8, 1, 20, 0, tzinfo=ford_scan.MARKET_TZ),
            market_open=False,
        )

        for offset in range(5):
            key = f"daily-recap:{(monday + timedelta(days=offset)).isoformat()}"
            self.assertIn(key, discord.cards)
            self.assertIn("Canonical ledger coverage", discord.cards[key])
            self.assertIn("1/1", discord.cards[key])

        weekly_key = "weekly-report:2026-W31"
        self.assertIn(weekly_key, discord.cards)
        self.assertIn("5/5", discord.cards[weekly_key])
        self.assertIn("Mon 1", discord.cards[weekly_key])
        self.assertIn("Fri 1", discord.cards[weekly_key])

        strategy = discord.cards["strategy-breakdown"]
        self.assertIn("5/5", strategy)
        self.assertIn("Current week", strategy)
        self.assertIn("5 trades", strategy)

        performance = discord.cards["performance-stats"]
        self.assertIn("5/5", performance)
        self.assertIn("Current week", performance)

        self.assertEqual(state["performance_reconciliation_closed_trades"], 5)
        self.assertEqual(state["performance_reconciliation_week_trades"], 5)
        self.assertEqual(
            state["performance_reconciliation_version"],
            reconciliation.REPORT_VERSION,
        )

    def test_ledger_signature_forces_rebuild_when_trade_result_changes(self) -> None:
        closed_at = datetime(2026, 7, 31, 14, 30, tzinfo=ford_scan.MARKET_TZ)
        row = self.make_row(1, closed_at, outcome="WIN")
        first = reconciliation.ledger_signature([row])
        row["realized_pl_dollars"] = "25"
        second = reconciliation.ledger_signature([row])
        self.assertNotEqual(first, second)

    def test_missing_closed_at_uses_last_evaluated_timestamp(self) -> None:
        closed_at = datetime(2026, 7, 29, 14, 30, tzinfo=ford_scan.MARKET_TZ)
        row = self.make_row(1, closed_at, outcome="WIN", omit_closed_at=True)
        self.assertEqual(
            reconciliation.effective_closed_at(row).date(),
            closed_at.date(),
        )
        self.assertEqual(
            len(reconciliation.rows_closed_on([row], closed_at.date())),
            1,
        )


if __name__ == "__main__":
    unittest.main()
