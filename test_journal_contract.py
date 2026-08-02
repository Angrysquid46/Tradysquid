from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import ford_scan
import journal_contract


class JournalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        journal_contract.install()

    def make_row(self, trade_id: str = "TEST-JOURNAL-001", outcome: str = "OPEN") -> dict[str, str]:
        opened = datetime(2026, 8, 1, 10, 0, tzinfo=ford_scan.MARKET_TZ)
        row = ford_scan.blank_row()
        row.update(
            {
                "trade_id": trade_id,
                "timestamp": opened.isoformat(),
                "action": "BUY open",
                "play_type": "REGULAR",
                "ticker": "F",
                "call_or_put": "call",
                "strike": "12",
                "expiration": "2026-08-21",
                "entry_price": "0.50",
                "cost_or_credit": "0.50",
                "max_profit": "UNLIMITED",
                "max_risk": "50",
                "breakeven": "12.50",
                "delta_at_entry": "0.40",
                "theta_at_entry": "-0.02",
                "iv_at_entry": "0.45",
                "open_interest_at_entry": "1000",
                "option_volume_at_entry": "250",
                "bid_ask_width_at_entry": "0.05",
                "setup_score": "75",
                "setup_reason": "Price, trend, and liquidity confirmed",
                "market_regime": "BULLISH",
                "thesis": "Bullish continuation with liquid option exposure",
                "entry_confirmation": "Underlying held support and the contract remained liquid",
                "invalidation": "Underlying loses support or the stored stop is reached",
                "risk_plan": "One contract, fixed stop, no averaging down",
                "learning_plan": "Apply price action, Greeks, volatility, risk, and journaling lessons",
                "evidence_limitations": "Only evidence captured at entry is treated as factual",
                "learning_version": "test-learning-version",
                "data_confidence": "CAPTURED",
                "outcome": outcome,
                "last_signal": "HOLD" if outcome == "OPEN" else "TAKE PROFIT",
                "max_favorable_pct": "30",
                "max_adverse_pct": "-8",
            }
        )
        if outcome != "OPEN":
            row.update(
                {
                    "closed_at": (opened + timedelta(hours=2)).isoformat(),
                    "exit_price": "0.65",
                    "realized_pl_dollars": "15",
                    "pct_gain_loss": "30",
                }
            )
        return row

    def test_entry_card_contains_complete_contract(self) -> None:
        row = self.make_row()
        content = ford_scan.entry_alert_text(row)
        for marker in journal_contract.REQUIRED_ENTRY_MARKERS:
            self.assertIn(marker, content)
        self.assertIn("5m / daily / weekly / monthly", content)
        self.assertIn("not substituted as entry-time evidence", content)
        self.assertEqual(ford_scan.DISCORD_FORMAT_VERSION, "14")

    def test_closed_journal_requires_post_trade_review(self) -> None:
        row = self.make_row(outcome="WIN")
        entry = ford_scan.entry_alert_text(row)
        close = ford_scan.close_alert_text(row, ford_scan.stored_close_evaluation(row))
        messages = [{"content": entry}, {"content": close}]
        self.assertEqual(journal_contract.missing_markers(row, messages), [])

    def test_partial_journal_is_rejected(self) -> None:
        row = self.make_row()
        missing = journal_contract.missing_markers(
            row,
            [{"content": "## Entry\nApplied Learning Center Analysis\nLearning Center version"}],
        )
        self.assertIn("Trade thesis", missing)
        self.assertIn("Entry confirmation", missing)
        self.assertIn("Invalidation", missing)
        self.assertIn("Risk plan", missing)
        self.assertIn("Data confidence", missing)

    def test_pending_batch_prioritizes_open_trades(self) -> None:
        rows = []
        for index in range(journal_contract.JOURNAL_BATCH_SIZE + 5):
            outcome = "OPEN" if index < 2 else "LOSS"
            row = self.make_row(f"TEST-{index:03d}", outcome=outcome)
            row["discord_thread_id"] = f"thread-{index}"
            row["discord_format_version"] = "13"
            rows.append(row)
        selected, pending = journal_contract._pending_rows(rows)
        self.assertEqual(pending, len(rows))
        self.assertEqual(len(selected), journal_contract.JOURNAL_BATCH_SIZE)
        self.assertEqual([row["outcome"] for row in selected[:2]], ["OPEN", "OPEN"])

    def test_contract_self_validation(self) -> None:
        result = journal_contract.validate_contract()
        self.assertEqual(result["format_version"], "14")
        self.assertEqual(result["missing"], 0)


if __name__ == "__main__":
    unittest.main()
