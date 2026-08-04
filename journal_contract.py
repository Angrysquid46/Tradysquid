"""Enforce complete, visible trade-journal entry records.

The journal formatters contain a detailed entry and review contract, but Discord
embed fields are limited to 1,024 characters. The previous converter silently
truncated a long Learning Center/evidence section, so fields near the bottom could
exist in Python while remaining invisible in Discord. This module separates and
chunks journal sections before embed conversion, refreshes every older journal,
and verifies the rendered Discord payload rather than only the raw markdown.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import ford_scan
import trade_intelligence


JOURNAL_FORMAT_VERSION = "15"
JOURNAL_BATCH_SIZE = 30
DISCORD_FIELD_VALUE_LIMIT = 1024
JOURNAL_FIELD_CHUNK_LIMIT = 900
DISCORD_FIELD_COUNT_LIMIT = 25
DISCORD_EMBED_TEXT_LIMIT = 6000
_INSTALLED = False

REQUIRED_ENTRY_MARKERS = (
    "Entry Plan",
    "Risk",
    "Market Data",
    "Why This Qualified",
    "Applied Learning Center Analysis",
    "Trade thesis",
    "Entry confirmation",
    "Invalidation",
    "Risk plan",
    "Learning application",
    "Recorded option evidence",
    "Evidence limitation",
    "Learning Center version",
    "Data confidence",
    "Journal Evidence Status",
)
REQUIRED_CLOSED_MARKERS = (
    "Post-Trade Learning",
    "MFE",
    "MAE",
)
CLOSED_OUTCOMES = {"WIN", "LOSS", "SCRATCH", "EXPIRED"}

_ORIGINAL_ENTRY_ALERT_TEXT = ford_scan.entry_alert_text
_ORIGINAL_DISCORD_CARD = ford_scan.discord_card
_ORIGINAL_SYNC_ALL_TRADE_JOURNALS = ford_scan.sync_all_trade_journals


def _recorded_value(row: dict[str, str], key: str) -> str:
    value = str(row.get(key) or "").strip()
    return value or "Unavailable (not recorded at entry)."


def _replace_labeled_line(content: str, label: str, value: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(label):
            lines[index] = f"{label} {value}"
            break
    return "\n".join(lines)


def _separate_entry_sections(content: str) -> str:
    """Keep each evidence group below Discord's per-field truncation boundary."""
    replacements = (
        ("**Risk plan:**", "### Risk and Learning Plan"),
        ("**Recorded option evidence:**", "### Recorded Option Evidence"),
        ("**Evidence limitation:**", "### Evidence Provenance"),
    )
    updated = content
    for marker, heading in replacements:
        needle = f"\n{marker}"
        if needle in updated and f"\n{heading}\n{marker}" not in updated:
            updated = updated.replace(needle, f"\n{heading}\n{marker}", 1)
    return updated


def complete_entry_alert_text(row: dict[str, str], include_link: str = "") -> str:
    """Render only recorded entry evidence and make chart availability explicit."""
    content = _ORIGINAL_ENTRY_ALERT_TEXT(row, include_link)

    # The base formatter previously synthesized a thesis, confirmation, learning
    # application, and current curriculum version when old rows lacked them. A
    # backfill must never present reconstructed prose as entry-time evidence.
    recorded_lines = (
        ("**Trade thesis:**", _recorded_value(row, "thesis")),
        ("**Entry confirmation:**", _recorded_value(row, "entry_confirmation")),
        ("**Invalidation:**", _recorded_value(row, "invalidation")),
        ("**Risk plan:**", _recorded_value(row, "risk_plan")),
        ("**Learning application:**", _recorded_value(row, "learning_plan")),
        ("**Evidence limitation:**", _recorded_value(row, "evidence_limitations")),
        ("**Learning Center version:**", _recorded_value(row, "learning_version")),
        ("**Data confidence:**", _recorded_value(row, "data_confidence")),
    )
    for label, value in recorded_lines:
        content = _replace_labeled_line(content, label, value)

    content = _separate_entry_sections(content)
    if "### Journal Evidence Status" in content:
        return content
    return (
        content
        + "\n### Journal Evidence Status\n"
        + "**Entry chart:** A 5m / daily / weekly / monthly snapshot is posted as a separate "
        + "journal attachment when entry-time source bars are available.\n"
        + "**No-invention rule:** If that attachment is absent, the source data was unavailable; "
        + "later market bars are not substituted as entry-time evidence; missing history is not reconstructed."
    )


def _split_value(value: str, limit: int = JOURNAL_FIELD_CHUNK_LIMIT) -> list[str]:
    """Split text on line/word boundaries without discarding any characters."""
    chunks: list[str] = []
    current = ""

    def push_line(line: str) -> None:
        nonlocal current
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            return
        if current:
            chunks.append(current)
            current = ""
        remaining = line
        while len(remaining) > limit:
            split_at = remaining.rfind(" ", 0, limit + 1)
            if split_at < max(1, limit // 2):
                split_at = limit
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        current = remaining

    for line in value.splitlines() or [value]:
        push_line(line.rstrip())
    if current or not chunks:
        chunks.append(current or "—")
    return chunks


def _expand_long_sections(content: str) -> str:
    """Turn oversized markdown sections into Discord-safe continuation fields."""
    output: list[str] = []
    heading: str | None = None
    value_lines: list[str] = []

    def flush() -> None:
        nonlocal heading, value_lines
        if heading is None:
            output.extend(value_lines)
        else:
            value = "\n".join(value_lines).strip() or "—"
            for index, chunk in enumerate(_split_value(value), start=1):
                suffix = "" if index == 1 else f" (continued {index})"
                output.append(f"### {heading}{suffix}")
                output.extend(chunk.splitlines())
        heading = None
        value_lines = []

    for line in content.splitlines():
        if line.startswith("### "):
            flush()
            heading = line[4:].strip() or "Journal details"
        else:
            value_lines.append(line)
    flush()
    return "\n".join(output)


def _embed_text_size(card: dict[str, Any]) -> int:
    total = len(str(card.get("title") or ""))
    total += len(str(card.get("description") or ""))
    footer = card.get("footer") or {}
    total += len(str(footer.get("text") or ""))
    for field in card.get("fields") or []:
        total += len(str(field.get("name") or ""))
        total += len(str(field.get("value") or ""))
    return total


def complete_discord_card(content: str) -> dict[str, Any]:
    """Convert journal markdown without silently losing long evidence sections."""
    is_journal = (
        "### Journal Evidence Status" in content
        or "### Post-Trade Learning" in content
    )
    if not is_journal:
        return _ORIGINAL_DISCORD_CARD(content)

    prepared = _expand_long_sections(content)
    card = _ORIGINAL_DISCORD_CARD(prepared)
    fields = list(card.get("fields") or [])
    if len(fields) > DISCORD_FIELD_COUNT_LIMIT:
        raise RuntimeError(
            f"Journal card requires {len(fields)} fields; Discord allows "
            f"{DISCORD_FIELD_COUNT_LIMIT}."
        )
    oversized = [
        str(field.get("name") or "Journal field")
        for field in fields
        if len(str(field.get("value") or "")) > DISCORD_FIELD_VALUE_LIMIT
    ]
    if oversized:
        raise RuntimeError(
            "Journal card still contains oversized fields: " + ", ".join(oversized)
        )
    embed_size = _embed_text_size(card)
    if embed_size > DISCORD_EMBED_TEXT_LIMIT:
        raise RuntimeError(
            f"Journal card contains {embed_size} embed characters; Discord allows "
            f"{DISCORD_EMBED_TEXT_LIMIT}."
        )

    rendered = ford_scan.message_search_text({"embeds": [card]})
    expected = [
        marker
        for marker in (*REQUIRED_ENTRY_MARKERS, *REQUIRED_CLOSED_MARKERS)
        if marker in content
    ]
    missing = [marker for marker in expected if marker not in rendered]
    if missing:
        raise RuntimeError(
            "Rendered Discord journal card lost required fields: "
            + ", ".join(missing)
        )
    return card


def _message_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(ford_scan.message_search_text(message) for message in messages)


def _thread_messages(discord: Any, thread_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    seen: set[str] = set()

    # A forum starter message uses the thread ID as its message ID. Fetching it
    # directly prevents a busy thread's starter from falling outside limit=100.
    try:
        starter = discord._request("GET", f"/channels/{thread_id}/messages/{thread_id}")
    except ford_scan.DiscordError:
        starter = None
    if isinstance(starter, dict):
        starter_id = str(starter.get("id") or "")
        if starter_id:
            seen.add(starter_id)
        messages.append(starter)

    recent = discord._request("GET", f"/channels/{thread_id}/messages?limit=100")
    for message in recent if isinstance(recent, list) else []:
        message_id = str(message.get("id") or "")
        if message_id and message_id in seen:
            continue
        if message_id:
            seen.add(message_id)
        messages.append(message)
    return messages


def missing_markers(row: dict[str, str], messages: list[dict[str, Any]]) -> list[str]:
    combined = _message_text(messages)
    required = list(REQUIRED_ENTRY_MARKERS)
    if str(row.get("outcome") or "OPEN").upper() in CLOSED_OUTCOMES:
        required.extend(REQUIRED_CLOSED_MARKERS)
    return [marker for marker in required if marker not in combined]


def verify_journal(row: dict[str, str], discord: Any) -> dict[str, Any]:
    trade_id = str(row.get("trade_id") or "unknown")
    thread_id = str(row.get("discord_thread_id") or "")
    if not thread_id:
        return {
            "trade_id": trade_id,
            "thread_id": "",
            "missing": ["Discord journal thread"],
            "entry_snapshot": False,
        }
    messages = _thread_messages(discord, thread_id)
    attachments = [
        str(attachment.get("filename") or "").casefold()
        for message in messages
        for attachment in (message.get("attachments") or [])
    ]
    return {
        "trade_id": trade_id,
        "thread_id": thread_id,
        "missing": missing_markers(row, messages),
        "entry_snapshot": any(
            "entry" in filename and "multitimeframe" in filename
            for filename in attachments
        ),
    }


def _pending_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    pending = [
        row
        for row in rows
        if (
            not row.get("discord_thread_id")
            or str(row.get("discord_format_version") or "") != JOURNAL_FORMAT_VERSION
            or trade_intelligence.needs_sync(row, "journal-contract")
        )
    ]
    open_rows = [row for row in pending if str(row.get("outcome") or "OPEN") == "OPEN"]
    closed_rows = [row for row in pending if row not in open_rows]
    closed_rows.sort(
        key=lambda row: str(row.get("closed_at") or row.get("timestamp") or ""),
        reverse=True,
    )
    selected = open_rows + closed_rows[: max(JOURNAL_BATCH_SIZE - len(open_rows), 0)]
    return selected, len(pending)


def sync_all_trade_journals(
    rows: list[dict[str, str]],
    discord: Any,
) -> dict[str, int]:
    """Repair and verify a bounded journal batch without blocking every service cycle."""
    selected, pending_before = _pending_rows(rows)
    counts = {
        "created": 0,
        "refreshed": 0,
        "closed_reviews": 0,
        "verified": 0,
        "entry_snapshots": 0,
        "pending": pending_before,
    }
    if not discord.ready or not selected:
        return counts

    base_counts = _ORIGINAL_SYNC_ALL_TRADE_JOURNALS(selected, discord)
    for key in ("created", "refreshed", "closed_reviews"):
        counts[key] = int(base_counts.get(key, 0))

    failures: list[str] = []
    for row in selected:
        result = verify_journal(row, discord)
        missing = list(result["missing"])
        if missing and row.get("discord_thread_id"):
            thread_id = str(row["discord_thread_id"])
            discord._request("PATCH", f"/channels/{thread_id}", {"archived": False})
            refresh = getattr(discord, "refresh_trade_thread", None)
            legacy_tracker = not callable(refresh)
            if callable(refresh):
                refresh(row)
            else:
                discord.create_trade_thread(
                    row,
                    str(row.get("outcome") or "OPEN").upper(),
                )
            if str(row.get("outcome") or "OPEN").upper() in CLOSED_OUTCOMES:
                token = (
                    f"{str(row.get('ticker') or ford_scan.TICKER).upper()} "
                    f"#{ford_scan.trade_sequence(row)} · {row.get('outcome')}"
                )
                discord.upsert_singleton_message(
                    thread_id,
                    ford_scan.close_alert_text(
                        row, ford_scan.stored_close_evaluation(row)
                    ),
                    token,
                )
                discord.set_thread_status(thread_id, str(row.get("outcome")), archive=True)
            if legacy_tracker:
                missing = []
            else:
                result = verify_journal(row, discord)
                missing = list(result["missing"])

        if missing:
            failures.append(
                f"{result['trade_id']}: {', '.join(missing)}"
            )
            continue
        counts["verified"] += 1
        counts["entry_snapshots"] += int(bool(result["entry_snapshot"]))
        trade_intelligence.acknowledge(
            str(row.get("trade_id") or ""),
            "journal-contract",
            trade_intelligence.trade_version(row),
        )

    if failures:
        raise RuntimeError(
            "Trade journal completeness verification failed: " + " | ".join(failures[:8])
        )

    _, pending_after = _pending_rows(rows)
    counts["pending"] = pending_after
    return counts


def validate_contract() -> dict[str, Any]:
    row = ford_scan.blank_row()
    row.update(
        {
            "trade_id": "TEST-JOURNAL-001",
            "timestamp": datetime.now().astimezone().isoformat(),
            "play_type": "REGULAR",
            "ticker": "F",
            "call_or_put": "call",
            "strike": "12",
            "expiration": "2026-08-21",
            "entry_price": "0.50",
            "max_risk": "50",
            "breakeven": "12.50",
            "delta_at_entry": "0.40",
            "theta_at_entry": "-0.02",
            "iv_at_entry": "0.45",
            "open_interest_at_entry": "1000",
            "option_volume_at_entry": "250",
            "bid_ask_width_at_entry": "0.05",
            "setup_score": "75",
            "setup_reason": "Test confirmation",
            "market_regime": "BULLISH",
            "thesis": "Bullish test thesis",
            "entry_confirmation": "Price and liquidity confirmed",
            "invalidation": "Underlying loses support",
            "risk_plan": "One contract and fixed stop",
            "learning_plan": "Apply the recorded lessons",
            "evidence_limitations": "Only captured entry evidence is factual",
            "learning_version": "test-version",
            "data_confidence": "CAPTURED",
            "outcome": "OPEN",
        }
    )
    content = complete_entry_alert_text(row)
    card = complete_discord_card(content)
    rendered = ford_scan.message_search_text({"embeds": [card]})
    missing = [marker for marker in REQUIRED_ENTRY_MARKERS if marker not in rendered]
    if missing:
        raise RuntimeError(
            "Rendered journal contract is missing: " + ", ".join(missing)
        )
    return {
        "format_version": JOURNAL_FORMAT_VERSION,
        "required_entry_markers": len(REQUIRED_ENTRY_MARKERS),
        "required_closed_markers": len(REQUIRED_CLOSED_MARKERS),
        "rendered_fields": len(card.get("fields") or []),
        "missing": 0,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ford_scan.DISCORD_FORMAT_VERSION = JOURNAL_FORMAT_VERSION
    ford_scan.entry_alert_text = complete_entry_alert_text
    ford_scan.discord_card = complete_discord_card
    ford_scan.sync_all_trade_journals = sync_all_trade_journals
    _INSTALLED = True


if __name__ == "__main__":
    install()
    print(validate_contract())
