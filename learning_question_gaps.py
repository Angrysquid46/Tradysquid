"""Record unanswered TradeBot questions and post them for owner review.

Questions are deduplicated, saved under state/, and posted as backed cards in
#upgrade-review by default. Repeated wording updates the existing card instead
of creating a small landfill of identical questions.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import ford_scan
import learning_application
import learning_center_content as learning
from discord_cards import style_message_payload

ROOT = Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "state" / "learning-question-gaps.json"
DEFAULT_REVIEW_CHANNEL = os.environ.get(
    "LEARNING_GAP_CHANNEL", "upgrade-review"
).strip() or "upgrade-review"
MAX_RECORDS = 1000


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def question_key(question: str) -> str:
    normalized = learning.normalize(question)
    return "QG-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10].upper()


def _load_queue() -> dict[str, Any]:
    try:
        payload = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {"version": 1, "records": {}}
    if not isinstance(payload, dict):
        payload = {"version": 1, "records": {}}
    records = payload.get("records")
    if not isinstance(records, dict):
        payload["records"] = {}
    return payload


def _save_queue(payload: dict[str, Any]) -> None:
    records = payload.get("records") or {}
    if len(records) > MAX_RECORDS:
        ordered = sorted(
            records.items(),
            key=lambda item: str((item[1] or {}).get("last_seen_at") or ""),
            reverse=True,
        )[:MAX_RECORDS]
        payload["records"] = dict(ordered)
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = QUEUE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(QUEUE_PATH)


def interaction_user(interaction: dict[str, Any]) -> dict[str, str]:
    member = interaction.get("member") or {}
    user = member.get("user") or interaction.get("user") or {}
    return {
        "id": str(user.get("id") or ""),
        "name": str(
            member.get("nick")
            or user.get("global_name")
            or user.get("username")
            or "Unknown member"
        )[:120],
    }


def closest_matches(question: str, limit: int = 3) -> list[dict[str, Any]]:
    matches = learning.search_library(question, limit=limit)
    return [
        {
            "score": round(float(score), 1),
            "channel": section.channel,
            "heading": section.heading,
        }
        for score, section in matches
    ]


def _record_question(
    interaction: dict[str, Any],
    question: str,
    matches: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _load_queue()
    records = payload.setdefault("records", {})
    key = question_key(question)
    timestamp = now_iso()
    user = interaction_user(interaction)
    record = records.get(key)
    if not isinstance(record, dict):
        record = {
            "id": key,
            "question": question.strip()[:1200],
            "normalized_question": learning.normalize(question),
            "first_seen_at": timestamp,
            "last_seen_at": timestamp,
            "times_asked": 0,
            "users": [],
            "closest_matches": [],
            "status": "OPEN",
            "discord_channel_id": "",
            "discord_message_id": "",
        }
        records[key] = record

    record["last_seen_at"] = timestamp
    record["times_asked"] = int(record.get("times_asked") or 0) + 1
    record["closest_matches"] = matches
    users = record.setdefault("users", [])
    if user.get("id") and not any(item.get("id") == user["id"] for item in users):
        users.append(user)
    elif not user.get("id") and not users:
        users.append(user)
    record["users"] = users[-25:]
    _save_queue(payload)
    return payload, record


def _find_channel(
    tracker: ford_scan.DiscordTracker,
    channel_name: str,
) -> dict[str, Any] | None:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    return next(
        (
            channel
            for channel in channels
            if channel.get("type") == 0
            and str(channel.get("name") or "").casefold() == channel_name.casefold()
        ),
        None,
    )


def _review_card(record: dict[str, Any]) -> str:
    users = record.get("users") or []
    user_text = ", ".join(
        f"{item.get('name') or 'Unknown'} ({item.get('id') or 'no id'})"
        for item in users[-8:]
    ) or "Unknown member"
    match_lines = []
    for item in record.get("closest_matches") or []:
        match_lines.append(
            f"• **#{item.get('channel')}** → {item.get('heading')} "
            f"(score {item.get('score')})"
        )
    if not match_lines:
        match_lines.append("• No useful lesson match was found.")

    return "\n".join(
        [
            f"# Unanswered learning question · {record.get('id')}",
            "## Question",
            str(record.get("question") or "")[:1200],
            "",
            "## Review details",
            f"**Asked:** {record.get('times_asked', 1)} time(s)",
            f"**First seen:** {record.get('first_seen_at')}",
            f"**Last seen:** {record.get('last_seen_at')}",
            f"**Members:** {user_text}",
            "",
            "## Closest existing lessons",
            *match_lines,
            "",
            "## Why it was queued",
            "TradeBot did not have a confident library-grounded answer. It returned no invented financial explanation and saved this gap for curriculum review.",
            "",
            "## Improvement path",
            "Add or expand the correct lesson, include aliases and examples, then add this wording to the answer-engine tests. Repeated questions update this same record.",
            "",
            f"**Status:** {record.get('status') or 'OPEN'}",
        ]
    )[:3900]


def post_or_update_review(record: dict[str, Any]) -> str:
    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        return ""
    channel = _find_channel(tracker, DEFAULT_REVIEW_CHANNEL)
    if not channel:
        return ""

    content = _review_card(record)
    payload = style_message_payload(
        {"content": content, "allowed_mentions": {"parse": []}}
    )
    channel_id = str(channel.get("id") or "")
    message_id = str(record.get("discord_message_id") or "")
    existing_channel_id = str(record.get("discord_channel_id") or "")
    message: dict[str, Any] | None = None

    if message_id and existing_channel_id == channel_id:
        try:
            result = tracker._request(
                "PATCH", f"/channels/{channel_id}/messages/{message_id}", payload
            )
            message = result if isinstance(result, dict) else None
        except ford_scan.DiscordError:
            message = None

    if message is None:
        result = tracker._request(
            "POST", f"/channels/{channel_id}/messages", payload
        )
        message = result if isinstance(result, dict) else {}

    record["discord_channel_id"] = channel_id
    record["discord_message_id"] = str(message.get("id") or message_id)
    queue = _load_queue()
    queue.setdefault("records", {})[str(record.get("id"))] = record
    _save_queue(queue)
    return f"<#{channel_id}>"


def queue_unanswered_question(
    interaction: dict[str, Any],
    question: str,
) -> tuple[dict[str, Any], str]:
    matches = closest_matches(question)
    _, record = _record_question(interaction, question, matches)
    review_reference = ""
    try:
        review_reference = post_or_update_review(record)
    except Exception:
        # The local queue is the durable source. A temporary Discord failure must
        # not turn an educational question into a command failure.
        review_reference = ""
    return record, review_reference


def answer_with_gap_tracking(
    interaction: dict[str, Any],
    question: str,
) -> str:
    cleaned = str(question or "").strip()
    if learning_application.is_application_request(cleaned):
        return learning_application.answer(cleaned)

    matches = learning.confident_matches(cleaned, limit=5)
    if matches:
        return learning.answer_from_matches(cleaned, matches)

    record, review_reference = queue_unanswered_question(interaction, cleaned)
    location = review_reference or f"**#{DEFAULT_REVIEW_CHANNEL}**"
    closest = record.get("closest_matches") or []
    closest_text = (
        ", ".join(
            f"#{item.get('channel')} → {item.get('heading')}"
            for item in closest[:2]
        )
        if closest
        else "none"
    )
    return "\n".join(
        [
            "# I do not have a confident answer yet",
            f"I saved this as **{record.get('id')}** and sent it to {location} for review.",
            "I am not going to invent a financial explanation merely to keep the card occupied.",
            "",
            f"**Closest existing material:** {closest_text}",
            f"**Times this question has been recorded:** {record.get('times_asked', 1)}",
            "",
            "Once the correct lesson is expanded and tested, future questions with this wording can use the improved answer.",
        ]
    )[:3900]
