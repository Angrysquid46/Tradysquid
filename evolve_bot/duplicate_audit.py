"""Finds and repairs duplicate/incorrect trade cards across evolve_bot's
own Discord channels (#evolve-trades/#evolve-wins/#evolve-losses), using
state/trades.csv as the single source of truth for what a trade's card
should actually say. Owner: "make a discord bot command to
duplicatedelete across all tabs and shit keeping the proper formatting
shit and removing the bad copies" - built after finding, by hand, that
fabricated test data left behind during earlier development had left a
stale OPEN card for a trade that had actually closed 2 days earlier, plus
6 duplicate/wrong-numbers cards for two real trades sitting in
#evolve-losses (3 identical fakes for one trade, 3 identical WRONG-number
duplicates for the other - none of which had the real figures).

Never guesses which of several existing cards is "the right one" - for
any trade_id with more than one card, or a card in the wrong channel for
its real current outcome, every instance found is deleted and exactly one
fresh card is regenerated straight from the CSV row, through the same
_trade_card_text/_post_trade_card/_post_closed_trade_result functions a
real open/close event uses. A trade_id with cards but no matching CSV row
at all (test pollution with nothing behind it) has all of its cards
removed with nothing reposted."""

from __future__ import annotations

import re
from typing import Any

import discord_post
import engine
import spy_scanner as s
import tradelog

TRADE_ID_PATTERN = re.compile(r"EVOLVE-\d{8}-\d{3}")
AUDITED_CHANNELS = ("trades", "wins", "losses")


def _extract_trade_id(embed: dict[str, Any]) -> str | None:
    footer = (embed.get("footer") or {}).get("text", "")
    match = TRADE_ID_PATTERN.search(footer)
    return match.group(0) if match else None


def _channel_messages(channel_key: str) -> list[dict[str, Any]]:
    channels = discord_post.ensure_channels()
    channel_id = channels[channel_key]
    messages = discord_post._request("GET", f"/channels/{channel_id}/messages?limit=100")
    return messages if isinstance(messages, list) else []


def _delete_message(channel_key: str, message_id: str) -> None:
    channels = discord_post.ensure_channels()
    channel_id = channels[channel_key]
    discord_post._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")


def find_trade_cards(channel_keys: tuple[str, ...] = AUDITED_CHANNELS) -> dict[str, list[tuple[str, str]]]:
    """Every (channel_key, message_id) pair currently carrying a
    recognizable EVOLVE-YYYYMMDD-NNN footer marker, grouped by trade_id -
    across ALL of channel_keys combined, so a card sitting in the wrong
    channel (e.g. a closed trade still in #evolve-trades) shows up
    alongside its correctly-placed siblings instead of being invisible to
    the sweep."""
    found: dict[str, list[tuple[str, str]]] = {}
    for channel_key in channel_keys:
        for message in _channel_messages(channel_key):
            for embed in message.get("embeds", []):
                trade_id = _extract_trade_id(embed)
                if not trade_id:
                    continue
                found.setdefault(trade_id, []).append((channel_key, str(message["id"])))
    return found


def _correct_channel_for(row: dict[str, str]) -> str:
    outcome = row.get("outcome", "")
    if outcome == "OPEN":
        return "trades"
    return "wins" if outcome == "WIN" else "losses"


def _rebuild_card_content(row: dict[str, str]) -> str:
    outcome = row.get("outcome", "")
    if outcome == "OPEN":
        return engine._trade_card_text(row, "OPEN")
    return engine._trade_card_text(
        row, outcome,
        mark=s.as_float(row.get("exit_price"), 0.0),
        pl_pct=s.as_float(row.get("pl_pct"), 0.0),
        pl_dollars=s.as_float(row.get("pl_dollars"), 0.0),
        signal=row.get("last_signal", ""),
        balance=s.as_float(row.get("balance_after"), 0.0),
    )


def _repost(row: dict[str, str]) -> None:
    trade_id = row.get("trade_id", "")
    content = _rebuild_card_content(row)
    if row.get("outcome") == "OPEN":
        engine._post_trade_card(trade_id, content)
    else:
        engine._post_closed_trade_result(row, content)


def run_audit(*, apply: bool = True) -> dict[str, Any]:
    """Dry-run (apply=False) reports what's wrong without touching
    Discord; apply=True (the default, and what the /force-... style owner
    commands use) actually deletes the bad cards and reposts the correct
    one for anything found broken."""
    rows = tradelog.read_log(engine.TRADELOG_PATH)
    by_trade_id = {row["trade_id"]: row for row in rows if row.get("trade_id")}
    found = find_trade_cards()

    removed = 0
    reposted = 0
    misplaced_channel_hits = 0
    orphaned_cards_removed = 0
    repaired_trade_ids: list[str] = []

    for trade_id, locations in found.items():
        row = by_trade_id.get(trade_id)
        if row is None:
            # No matching row in the canonical ledger at all - never
            # guess what it should say, just remove it.
            for channel_key, message_id in locations:
                if apply:
                    _delete_message(channel_key, message_id)
                removed += 1
                orphaned_cards_removed += 1
            continue

        correct_channel = _correct_channel_for(row)
        right_channel_hits = [loc for loc in locations if loc[0] == correct_channel]
        wrong_channel_hits = [loc for loc in locations if loc[0] != correct_channel]

        if not wrong_channel_hits and len(right_channel_hits) == 1:
            continue  # already exactly right - nothing to do

        repaired_trade_ids.append(trade_id)
        for channel_key, message_id in locations:
            if apply:
                _delete_message(channel_key, message_id)
            removed += 1
        misplaced_channel_hits += len(wrong_channel_hits)

        if apply:
            _repost(row)
        reposted += 1

    return {
        "applied": apply,
        "trade_ids_checked": len(found),
        "trade_ids_repaired": len(repaired_trade_ids),
        "repaired": repaired_trade_ids,
        "cards_removed": removed,
        "cards_reposted": reposted,
        "misplaced_channel_hits": misplaced_channel_hits,
        "orphaned_cards_removed": orphaned_cards_removed,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_audit(), indent=2))
