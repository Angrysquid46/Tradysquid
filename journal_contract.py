"""Enforce complete, visible trade-journal entry records.

The journal already had detailed formatters, but synchronization could call a
thread complete after checking only a few broad markers. This module gives every
journal starter a stable evidence-status section, refreshes outdated journals in
bounded batches, and verifies the full entry checklist before acknowledging the
journal consumer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import ford_scan
import trade_intelligence


JOURNAL_FORMAT_VERSION = "14"
JOURNAL_BATCH_SIZE = 30
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
_ORIGINAL_SYNC_ALL_TRADE_JOURNALS = ford_scan.sync_all_trade_journals


def complete_entry_alert_text(row: dict[str, str], include_link: str = "") -> str:
    """Render the canonical entry card and make chart availability explicit."""
    content = _ORIGINAL_ENTRY_ALERT_TEXT(row, include_link)
    if "### Journal Evidence Status" in content:
        return content
    return (
        content
        + "\n### Journal Evidence Status\n"
        + "**Entry chart:** A 5m / daily / weekly / monthly snapshot is posted as a separate "
        + "journal attachment when entry-time source bars are available.\n"
        + "**No-invention rule:** If that attachment is absent, the source data was unavailable; "
        + "later market bars are not substituted as entry-time evidence."
    )


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
            discord.refresh_trade_thread(row)
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
    missing = [marker for marker in REQUIRED_ENTRY_MARKERS if marker not in content]
    if missing:
        raise RuntimeError("Journal contract formatter is missing: " + ", ".join(missing))
    return {
        "format_version": JOURNAL_FORMAT_VERSION,
        "required_entry_markers": len(REQUIRED_ENTRY_MARKERS),
        "required_closed_markers": len(REQUIRED_CLOSED_MARKERS),
        "missing": 0,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ford_scan.DISCORD_FORMAT_VERSION = JOURNAL_FORMAT_VERSION
    ford_scan.entry_alert_text = complete_entry_alert_text
    ford_scan.sync_all_trade_journals = sync_all_trade_journals
    _INSTALLED = True


if __name__ == "__main__":
    install()
    print(validate_contract())
