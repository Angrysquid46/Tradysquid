"""Install the OpenAI enhancement around TradeBot's existing `/ask` engine."""

from __future__ import annotations

from functools import wraps
from typing import Any

import learning_question_gaps as question_gaps
import openai_discord_assistant as assistant


def _interaction_user_id(interaction: dict[str, Any]) -> str:
    member = interaction.get("member") or {}
    user = member.get("user") or interaction.get("user") or {}
    return str(user.get("id") or "")


def install() -> None:
    """Wrap the existing grounded answer path exactly once."""
    current = question_gaps.answer_with_gap_tracking
    if getattr(current, "_tradysquids_openai_enhanced", False):
        return

    @wraps(current)
    def enhanced_answer(
        interaction: dict[str, Any],
        question: str,
    ) -> str:
        local_answer = current(interaction, question)
        return assistant.answer(
            question,
            local_answer,
            user_id=_interaction_user_id(interaction),
        )

    setattr(enhanced_answer, "_tradysquids_openai_enhanced", True)
    question_gaps.answer_with_gap_tracking = enhanced_answer
