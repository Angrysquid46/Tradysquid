from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import spy_scanner
import journal_contract


class JournalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        journal_contract.install()

    def make_row(self, trade_id: str = "TEST-JOURNAL-001", outcome: str = "OPEN") -> dict[str, str]:
        opened = datetime(2026, 8, 1, 10, 0, tzinfo=spy_scanner.MARKET_TZ)
        row = spy_scanner.blank_row()
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

    @staticmethod
    def rendered_text(content: str) -> tuple[str, dict]:
        card = spy_scanner.discord_card(content)
        message = {"content": "", "embeds": [card]}
        return spy_scanner.message_search_text(message), card

    def test_entry_card_contains_complete_contract(self) -> None:
        row = self.make_row()
        content = spy_scanner.entry_alert_text(row)
        rendered, card = self.rendered_text(content)
        for marker in journal_contract.REQUIRED_ENTRY_MARKERS:
            self.assertIn(marker, rendered)
        self.assertIn("5m / daily / weekly / monthly", rendered)
        self.assertIn("not substituted as entry-time evidence", rendered)
        self.assertLessEqual(len(card.get("fields") or []), 25)
        self.assertTrue(
            all(len(str(field.get("value") or "")) <= 1024 for field in card.get("fields") or [])
        )
        self.assertEqual(spy_scanner.DISCORD_FORMAT_VERSION, "15")

    def test_rendered_card_does_not_truncate_long_learning_evidence(self) -> None:
        row = self.make_row()
        fields = {
            "thesis": "THESIS START " + ("trend evidence " * 24) + "THESIS END",
            "entry_confirmation": "CONFIRM START " + ("confirmation evidence " * 24) + "CONFIRM END",
            "invalidation": "INVALIDATION START " + ("risk boundary " * 24) + "INVALIDATION END",
            "risk_plan": "RISK START " + ("position control " * 24) + "RISK END",
            "learning_plan": "LEARNING START " + ("lesson application " * 24) + "LEARNING END",
            "evidence_limitations": "LIMIT START " + ("recorded limitation " * 24) + "LIMIT END",
        }
        row.update(fields)
        content = spy_scanner.entry_alert_text(row)
        rendered, card = self.rendered_text(content)
        for sentinel in (
            "THESIS END",
            "CONFIRM END",
            "INVALIDATION END",
            "RISK END",
            "LEARNING END",
            "LIMIT END",
            "Learning Center version",
            "Data confidence",
            "Journal Evidence Status",
        ):
            self.assertIn(sentinel, rendered)
        self.assertGreater(len(card.get("fields") or []), 7)
        self.assertTrue(
            all(len(str(field.get("value") or "")) <= 1024 for field in card.get("fields") or [])
        )

    def test_missing_historical_fields_are_marked_unavailable_not_reconstructed(self) -> None:
        row = self.make_row()
        for key in (
            "thesis",
            "entry_confirmation",
            "invalidation",
            "risk_plan",
            "learning_plan",
            "evidence_limitations",
            "learning_version",
            "data_confidence",
        ):
            row[key] = ""
        content = spy_scanner.entry_alert_text(row)
        rendered, _ = self.rendered_text(content)
        self.assertGreaterEqual(rendered.count("Unavailable (not recorded at entry)."), 8)
        self.assertNotIn("This regular call expresses a bullish paper thesis", rendered)
        self.assertNotIn("Apply 17-directional-options", rendered)

    def test_closed_journal_requires_post_trade_review(self) -> None:
        row = self.make_row(outcome="WIN")
        entry = spy_scanner.entry_alert_text(row)
        close = spy_scanner.close_alert_text(row, spy_scanner.stored_close_evaluation(row))
        entry_card = spy_scanner.discord_card(entry)
        close_card = spy_scanner.discord_card(close)
        messages = [{"embeds": [entry_card]}, {"embeds": [close_card]}]
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
            row["discord_format_version"] = "14"
            rows.append(row)
        selected, pending = journal_contract._pending_rows(rows)
        self.assertEqual(pending, len(rows))
        self.assertEqual(len(selected), journal_contract.JOURNAL_BATCH_SIZE)
        self.assertEqual([row["outcome"] for row in selected[:2]], ["OPEN", "OPEN"])

    def test_contract_self_validation(self) -> None:
        result = journal_contract.validate_contract()
        self.assertEqual(result["format_version"], "15")
        self.assertGreater(result["rendered_fields"], 0)
        self.assertEqual(result["missing"], 0)

    def test_entry_card_title_names_which_strategy_opened_it(self) -> None:
        # Owner ask: every position card must show which strategy/trader
        # opened it, not just "LONG CALL" with no indication of which of
        # the several live strategies is responsible for the position.
        row = self.make_row()
        row["play_type"] = "SPY_KEY_LEVELS"
        content = spy_scanner.entry_alert_text(row)
        self.assertIn("SPY_KEY_LEVELS LONG CALL", content)

    def test_held_position_card_title_names_which_strategy_opened_it(self) -> None:
        row = self.make_row()
        row["play_type"] = "SPY_0DTE_1M"
        content = spy_scanner.position_update_text(row, spy_scanner.stored_open_evaluation(row))
        self.assertIn("SPY_0DTE_1M LONG CALL", content)

    def test_closed_position_card_title_names_which_strategy_opened_it(self) -> None:
        row = self.make_row(outcome="WIN")
        row["play_type"] = "SPY_EXPANSION_LEVEL"
        content = spy_scanner.close_alert_text(row, spy_scanner.stored_close_evaluation(row))
        self.assertIn("SPY_EXPANSION_LEVEL LONG CALL", content)

    def test_summary_card_title_still_names_the_strategy(self) -> None:
        # The trimmed summary_only card (now the only card posted at open,
        # in both the shared channel and the trade's own journal thread)
        # must still name which strategy opened it.
        row = self.make_row()
        row["play_type"] = "SPY_0DTE_5M"
        content = spy_scanner.entry_alert_text(row, summary_only=True)
        self.assertIn("SPY_0DTE_5M LONG CALL", content)

    def test_summary_entry_card_stops_at_break_even(self) -> None:
        # Owner ask: the shared new-positions channel card only needs to
        # show from the top down through break-even - everything past that
        # (Market Data, Why This Qualified, the learning-center analysis)
        # belongs in the trade's own journal thread instead.
        row = self.make_row()
        content = spy_scanner.entry_alert_text(row, summary_only=True)
        self.assertIn("### Risk", content)
        self.assertIn("Break-even", content)
        self.assertNotIn("### Market Data", content)
        self.assertNotIn("### Why This Qualified", content)
        self.assertNotIn("Applied Learning Center Analysis", content)

    def test_full_entry_card_still_has_everything_for_the_journal_thread(self) -> None:
        # The trimmed summary_only path must not have quietly become the
        # only path - the trade's own journal thread still needs the full
        # detail, which is what the default (summary_only=False) returns.
        row = self.make_row()
        content = spy_scanner.entry_alert_text(row)
        self.assertIn("### Market Data", content)
        self.assertIn("### Why This Qualified", content)
        self.assertIn("Applied Learning Center Analysis", content)


if __name__ == "__main__":
    unittest.main()
