from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import learning_application
import learning_center_content
import learning_question_gaps
import learning_search_router
import sync_learning_center
from discord_cards import style_message_payload
from learning_center_catalog import LESSONS, ORDERED_CHANNELS


SAMPLE_SNAPSHOT = {
    "symbol": "F",
    "observed_at": "2026-08-01T01:00:00-05:00",
    "price": 12.00,
    "previous_close": 11.80,
    "change_pct": 1.69,
    "bid": 11.99,
    "ask": 12.01,
    "spread_pct": 0.001667,
    "volume": 20_000_000,
    "relative_volume": 1.6,
    "regime": "BULLISH / CONTROLLED",
    "qualified": True,
    "reason": "Price and momentum are constructive.",
    "failures": [],
    "sma20": 11.50,
    "sma50": 11.00,
    "sma200": 10.50,
    "rsi14": 61.0,
    "intraday_change_pct": 1.0,
    "intraday_vwap": 11.85,
    "intraday_rsi": 58.0,
    "intraday_slope_pct": 0.2,
    "evidence_score": 75,
    "ema12": 11.70,
    "ema26": 11.40,
    "macd": 0.30,
    "atr14": 0.40,
    "bollinger_upper": 12.30,
    "bollinger_lower": 10.70,
    "support20": 10.90,
    "resistance20": 12.50,
    "day_high": 12.10,
    "day_low": 11.75,
    "history": [],
}

SAMPLE_OPTION = {
    "symbol": "F260918C00012000",
    "underlying": "F",
    "type": "call",
    "strike": 12.0,
    "expiration": "2026-09-18",
    "bid": 0.60,
    "ask": 0.65,
    "mid": 0.625,
    "width": 0.05,
    "width_pct": 0.08,
    "open_interest": 1500,
    "volume": 250,
    "delta": 0.52,
    "theta": -0.02,
    "iv": 0.42,
    "intrinsic": 0.0,
    "extrinsic": 0.625,
    "liquidity_pass": True,
    "quality_score": 88.0,
}

SAMPLE_INTERACTION = {
    "guild_id": "guild-1",
    "member": {
        "nick": "Test Learner",
        "user": {"id": "user-1", "username": "tester"},
    },
}


class LearningCenterTests(unittest.TestCase):
    def test_catalog_is_complete_and_ordered(self) -> None:
        self.assertEqual(len(LESSONS), 32)
        numbers = [item.number for item in LESSONS]
        self.assertEqual(numbers, sorted(set(numbers)))
        self.assertTrue(all(item.channel in ORDERED_CHANNELS for item in LESSONS))
        self.assertEqual(tuple(item.channel for item in LESSONS), ORDERED_CHANNELS)

    def test_curriculum_cards_validate(self) -> None:
        counts = sync_learning_center.validate_curriculum()
        self.assertEqual(tuple(counts), ORDERED_CHANNELS)
        self.assertGreater(sum(counts.values()), 27)

    def test_duplicate_curriculum_markers_inside_embeds_are_deleted(self) -> None:
        channel_name = ORDERED_CHANNELS[0]
        content = sync_learning_center.lesson_marker(channel_name, 1, 1) + "\n# Test"
        styled = style_message_payload(
            {"content": content, "allowed_mentions": {"parse": []}}
        )
        messages = [
            {
                "id": "100",
                "content": styled.get("content", ""),
                "embeds": styled.get("embeds", []),
                "author": {"bot": True},
            },
            {
                "id": "101",
                "content": styled.get("content", ""),
                "embeds": styled.get("embeds", []),
                "author": {"bot": True},
            },
        ]

        class Tracker:
            def __init__(self):
                self.messages = list(messages)
                self.deleted: list[str] = []

            def _request(self, method, path, payload=None):
                if method == "GET":
                    return list(self.messages)
                if method == "DELETE":
                    message_id = path.rsplit("/", 1)[-1]
                    self.deleted.append(message_id)
                    self.messages = [
                        item for item in self.messages if item["id"] != message_id
                    ]
                    return {}
                if method == "PUT":
                    return {}
                if method == "PATCH":
                    return {}
                raise AssertionError(f"Unexpected request: {method} {path}")

        tracker = Tracker()
        with patch.object(
            sync_learning_center, "expected_messages", return_value=[content]
        ):
            with self.assertRaisesRegex(RuntimeError, "Duplicates"):
                sync_learning_center.verify_channel_uniqueness(
                    tracker, {"id": "channel-1"}, channel_name, "lesson"
                )
            created, updated, deleted = sync_learning_center.synchronize_channel(
                tracker, {"id": "channel-1"}, channel_name, "lesson"
            )
            verified = sync_learning_center.verify_channel_uniqueness(
                tracker, {"id": "channel-1"}, channel_name, "lesson"
            )

        self.assertEqual((created, updated, deleted), (0, 0, 1))
        self.assertEqual(verified, 1)
        self.assertEqual(len(tracker.deleted), 1)
        self.assertEqual(len(tracker.messages), 1)
        self.assertIn(tracker.deleted[0], {"100", "101"})

    def test_search_routes_representative_questions(self) -> None:
        result = learning_search_router.validate_search()
        self.assertGreater(result["sections"], 100)
        self.assertEqual(result["probes"], 9)

    def test_static_answer_cites_learning_center(self) -> None:
        answer = learning_search_router.answer("What is gamma risk near expiration?")
        self.assertIn("Learning Center reference", answer)
        self.assertIn(learning_center_content.channel_reference("15-option-pricing-greeks"), answer)

    def test_application_parser(self) -> None:
        result = learning_application.validate_parser(lambda symbol: True)
        self.assertEqual(result["probes"], 4)

    @patch.object(learning_application.info_engine, "fetch_ticker_news", return_value=[])
    @patch.object(learning_application.info_engine, "ranked_option_chain")
    @patch.object(learning_application.info_engine, "market_snapshot", return_value=SAMPLE_SNAPSHOT)
    def test_live_application_uses_observations_and_lessons(
        self,
        snapshot_mock,
        chain_mock,
        news_mock,
    ) -> None:
        chain_mock.return_value = [SAMPLE_OPTION]
        request = learning_application.ApplicationRequest(
            ticker="F",
            question="Apply RSI, support, and the option chain to $F calls",
            explicit_ticker=True,
            option_side="call",
        )
        answer = learning_application.apply_to_ticker(request)
        self.assertIn("Educational application · F", answer)
        self.assertIn("What the system can observe", answer)
        self.assertIn("Applying the lesson", answer)
        self.assertIn("Option-chain application", answer)
        self.assertIn("Learning Center references", answer)
        self.assertIn("RSI", answer)
        self.assertLessEqual(len(answer), 3900)
        snapshot_mock.assert_called_once_with("F")
        chain_mock.assert_called_once()

    @patch.object(learning_application, "_verify_symbol", return_value=True)
    def test_application_does_not_require_scanner_membership(self, verify_mock) -> None:
        request = learning_application.parse_application_request(
            "Walk me through support and resistance on $AAPL"
        )
        self.assertIsNotNone(request)
        self.assertEqual(request.ticker, "AAPL")
        verify_mock.assert_called()

    def test_unanswered_questions_are_saved_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "question-gaps.json"
            with (
                patch.object(learning_question_gaps, "QUEUE_PATH", queue_path),
                patch.object(
                    learning_question_gaps,
                    "post_or_update_review",
                    return_value="<#review-1>",
                ) as post_mock,
            ):
                question = "What is the lunar sandwich coefficient?"
                first = learning_question_gaps.answer_with_gap_tracking(
                    SAMPLE_INTERACTION, question
                )
                second = learning_question_gaps.answer_with_gap_tracking(
                    SAMPLE_INTERACTION, question
                )

            payload = json.loads(queue_path.read_text(encoding="utf-8"))
            records = payload["records"]
            self.assertEqual(len(records), 1)
            record = next(iter(records.values()))
            self.assertEqual(record["times_asked"], 2)
            self.assertEqual(record["users"][0]["id"], "user-1")
            self.assertIn("sent it to <#review-1>", first)
            self.assertIn("**Times this question has been recorded:** 2", second)
            self.assertEqual(post_mock.call_count, 2)

    def test_confident_question_does_not_enter_gap_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "question-gaps.json"
            with (
                patch.object(learning_question_gaps, "QUEUE_PATH", queue_path),
                patch.object(
                    learning_question_gaps, "post_or_update_review"
                ) as post_mock,
            ):
                answer = learning_question_gaps.answer_with_gap_tracking(
                    SAMPLE_INTERACTION,
                    "What does gamma do near expiration?",
                )
            self.assertIn(
                learning_center_content.channel_reference("15-option-pricing-greeks"),
                answer,
            )
            self.assertFalse(queue_path.exists())
            post_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
