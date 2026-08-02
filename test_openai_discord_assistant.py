from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import openai_discord_assistant as assistant


class OpenAIDiscordAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        assistant._CLIENT = None
        assistant._LAST_REQUEST_BY_USER.clear()

    def test_missing_key_preserves_local_answer(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            result = assistant.answer(
                "What is theta?",
                "Theta is daily time-decay sensitivity.",
                user_id="123",
            )
        self.assertIn("Theta is daily time-decay sensitivity.", result)
        self.assertIn("not configured", result)

    def test_openai_response_replaces_local_card_but_keeps_safety_footer(self) -> None:
        fake_client = Mock()
        fake_client.responses.create.return_value.output_text = (
            "Theta estimates time decay; IV changes can still dominate the trade."
        )
        env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-5-mini",
            "OPENAI_USER_COOLDOWN_SECONDS": "0",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(assistant, "_get_client", return_value=fake_client),
        ):
            result = assistant.answer(
                "What is theta?",
                "Local theta answer.",
                user_id="123",
            )

        self.assertIn("Theta estimates time decay", result)
        self.assertIn("AI-assisted educational response", result)
        call = fake_client.responses.create.call_args.kwargs
        self.assertEqual(call["model"], "gpt-5-mini")
        self.assertFalse(call["store"])
        self.assertIn("Local theta answer.", call["input"])

    def test_invalid_key_returns_local_answer_without_raw_exception(self) -> None:
        class UnauthorizedError(Exception):
            status_code = 401

        fake_client = Mock()
        fake_client.responses.create.side_effect = UnauthorizedError(
            "secret-bearing raw provider error"
        )
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_USER_COOLDOWN_SECONDS": "0",
                },
                clear=False,
            ),
            patch.object(assistant, "_get_client", return_value=fake_client),
        ):
            result = assistant.answer(
                "Explain IV.",
                "Local IV answer.",
                user_id="123",
            )

        self.assertIn("Local IV answer.", result)
        self.assertIn("rejected the configured key", result)
        self.assertNotIn("secret-bearing", result)


if __name__ == "__main__":
    unittest.main()
