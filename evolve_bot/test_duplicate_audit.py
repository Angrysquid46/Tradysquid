"""Tests for duplicate_audit.py - the /evolve-audit-duplicates command's
real logic. Owner: "make a discord bot command to duplicatedelete across
all tabs and shit keeping the proper formatting shit and removing the bad
copies", confirmed necessary from real duplicate/wrong-data cards found
live in #evolve-trades and #evolve-losses."""

from __future__ import annotations

from unittest import mock

import duplicate_audit
import tradelog


def _message(message_id: str, footer_trade_id: str | None) -> dict:
    footer = {"text": f"Tradysquids TradeBot · Card format 13 · {footer_trade_id}"} if footer_trade_id else {}
    return {"id": message_id, "embeds": [{"title": "x", "footer": footer}]}


def _row(trade_id: str, outcome: str = "OPEN") -> dict[str, str]:
    row = tradelog.blank_row()
    row.update({
        "trade_id": trade_id, "outcome": outcome, "call_or_put": "call",
        "strike": "600", "expiration": "2026-08-14", "entry_price": "0.50",
        "contracts": "1", "exit_price": "0.60", "pl_dollars": "10", "pl_pct": "20",
        "last_signal": "TAKE PROFIT", "balance_after": "1010",
    })
    return row


def _channel_messages_side_effect(mapping):
    def _fake(channel_key):
        return mapping.get(channel_key, [])
    return _fake


def test_a_single_correctly_placed_card_needs_no_repair():
    open_row = _row("EVOLVE-20260814-001", outcome="OPEN")
    messages = {"trades": [_message("m1", "EVOLVE-20260814-001")], "wins": [], "losses": []}
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[open_row]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_trade_card") as post_trade_card,
        mock.patch.object(duplicate_audit.engine, "_post_closed_trade_result") as post_closed,
    ):
        result = duplicate_audit.run_audit()

    delete_message.assert_not_called()
    post_trade_card.assert_not_called()
    post_closed.assert_not_called()
    assert result["trade_ids_repaired"] == 0
    assert result["cards_removed"] == 0


def test_duplicate_cards_in_the_same_channel_get_deduped_and_one_fresh_card_reposted():
    open_row = _row("EVOLVE-20260814-002", outcome="OPEN")
    messages = {
        "trades": [_message("dup-a", "EVOLVE-20260814-002"), _message("dup-b", "EVOLVE-20260814-002")],
        "wins": [], "losses": [],
    }
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[open_row]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_trade_card") as post_trade_card,
    ):
        result = duplicate_audit.run_audit()

    assert delete_message.call_count == 2
    deleted_ids = {call.args[1] for call in delete_message.call_args_list}
    assert deleted_ids == {"dup-a", "dup-b"}
    post_trade_card.assert_called_once()
    assert result["trade_ids_repaired"] == 1
    assert result["cards_removed"] == 2
    assert result["cards_reposted"] == 1


def test_stale_open_card_for_an_actually_closed_trade_is_removed_and_reposted_to_losses():
    """The real bug found live: a trade that closed as a LOSS 2 days
    earlier still had an OPEN card sitting in #evolve-trades."""
    closed_row = _row("EVOLVE-20260812-001", outcome="LOSS")
    messages = {
        "trades": [_message("stale-open", "EVOLVE-20260812-001")],
        "wins": [], "losses": [],
    }
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[closed_row]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_closed_trade_result") as post_closed,
    ):
        result = duplicate_audit.run_audit()

    delete_message.assert_called_once_with("trades", "stale-open")
    post_closed.assert_called_once()
    assert post_closed.call_args[0][0] is closed_row
    assert result["misplaced_channel_hits"] == 1


def test_wrong_number_duplicates_across_multiple_channels_all_get_replaced():
    """The other real bug found live: 3 identical WRONG-numbers cards for
    one closed trade sitting in #evolve-losses, none of them correct."""
    closed_row = _row("EVOLVE-20260812-002", outcome="LOSS")
    messages = {
        "trades": [],
        "wins": [],
        "losses": [
            _message("wrong-1", "EVOLVE-20260812-002"),
            _message("wrong-2", "EVOLVE-20260812-002"),
            _message("wrong-3", "EVOLVE-20260812-002"),
        ],
    }
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[closed_row]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_closed_trade_result") as post_closed,
    ):
        result = duplicate_audit.run_audit()

    assert delete_message.call_count == 3
    post_closed.assert_called_once()
    assert result["cards_removed"] == 3
    assert result["cards_reposted"] == 1


def test_orphaned_card_with_no_matching_csv_row_is_removed_without_reposting():
    """Test pollution with nothing real behind it - never guess what an
    orphaned card should say, just remove it."""
    messages = {"trades": [_message("ghost", "EVOLVE-20260101-099")], "wins": [], "losses": []}
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_trade_card") as post_trade_card,
        mock.patch.object(duplicate_audit.engine, "_post_closed_trade_result") as post_closed,
    ):
        result = duplicate_audit.run_audit()

    delete_message.assert_called_once_with("trades", "ghost")
    post_trade_card.assert_not_called()
    post_closed.assert_not_called()
    assert result["orphaned_cards_removed"] == 1
    assert result["trade_ids_repaired"] == 0


def test_dry_run_reports_without_deleting_or_reposting_anything():
    open_row = _row("EVOLVE-20260814-003", outcome="OPEN")
    messages = {
        "trades": [_message("dup-a", "EVOLVE-20260814-003"), _message("dup-b", "EVOLVE-20260814-003")],
        "wins": [], "losses": [],
    }
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[open_row]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
        mock.patch.object(duplicate_audit.engine, "_post_trade_card") as post_trade_card,
    ):
        result = duplicate_audit.run_audit(apply=False)

    delete_message.assert_not_called()
    post_trade_card.assert_not_called()
    assert result["applied"] is False
    assert result["trade_ids_repaired"] == 1
    assert result["cards_removed"] == 2
    assert result["cards_reposted"] == 1


def test_messages_without_a_recognizable_footer_are_ignored():
    messages = {"trades": [{"id": "no-footer", "embeds": [{"title": "unrelated card", "footer": {}}]}], "wins": [], "losses": []}
    with (
        mock.patch.object(duplicate_audit.tradelog, "read_log", return_value=[]),
        mock.patch.object(duplicate_audit, "_channel_messages", side_effect=_channel_messages_side_effect(messages)),
        mock.patch.object(duplicate_audit, "_delete_message") as delete_message,
    ):
        result = duplicate_audit.run_audit()

    delete_message.assert_not_called()
    assert result["trade_ids_checked"] == 0
