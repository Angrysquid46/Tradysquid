"""Tests for /force-sell: manually force-closes every currently open call
OR put position (owner picks which side) RIGHT NOW regardless of its live
P&L, using the exact same evaluate_open_row/close_row/post_close functions
the automated scan cycle and /close-profitable both use. Unlike
/close-profitable, this closes losers on purpose - the owner cutting a
trade they've judged bad, not waiting for the rule-based exit to agree."""

from __future__ import annotations

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import discord_command_bot as bot
import spy_scanner

CT = ZoneInfo("America/Chicago")


def _owner_interaction(direction: str = "call"):
    bot.ALLOWED_USER_ID = "owner-1"
    return {
        "member": {"user": {"id": "owner-1"}},
        "data": {"options": [{"name": "direction", "value": direction}]},
    }


def test_non_owner_cannot_force_close_positions():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {
        "member": {"user": {"id": "someone-else"}},
        "data": {"options": [{"name": "direction", "value": "call"}]},
    }
    with mock.patch.object(spy_scanner, "read_log") as read_log:
        try:
            bot.force_sell_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        read_log.assert_not_called()


def test_invalid_direction_raises():
    interaction = {
        "member": {"user": {"id": "owner-1"}},
        "data": {"options": [{"name": "direction", "value": "banana"}]},
    }
    bot.ALLOWED_USER_ID = "owner-1"
    try:
        bot.force_sell_reply(interaction)
        assert False, "should have raised"
    except ValueError:
        pass


def test_no_open_positions_on_that_side_closes_nothing():
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "write_log") as write_log,
    ):
        reply = bot.force_sell_reply(_owner_interaction("call"))
    assert "No open call positions" in reply
    write_log.assert_not_called()


def test_only_closes_positions_on_the_requested_side():
    call_row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M", "call_or_put": "call"}
    put_row = {"outcome": "OPEN", "option_symbol": "SPY260813P00770000", "play_type": "SPY_KEY_LEVELS", "call_or_put": "put"}
    rows = [call_row, put_row]

    def fake_close_row(row, evaluation, timestamp):
        row["outcome"] = "LOSS"
        return "LOSS"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 14, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "mark": 0.30, "pl_dollars": -40, "pl_pct": -20}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row) as close_row,
        mock.patch.object(spy_scanner, "write_log") as write_log,
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "safe_discord_call"),
        mock.patch.object(spy_scanner, "post_close"),
        mock.patch.object(spy_scanner, "sync_closed_result_channels"),
    ):
        reply = bot.force_sell_reply(_owner_interaction("call"))

    close_row.assert_called_once()
    assert close_row.call_args[0][0] is call_row
    assert call_row["outcome"] == "LOSS"
    assert put_row["outcome"] == "OPEN"  # never touched - wrong side
    write_log.assert_called_once_with(rows)
    assert "1 open call position" in reply


def test_force_closes_a_losing_position_unlike_close_profitable():
    """The whole point of this command: /close-profitable would skip a
    losing position entirely. /force-sell closes it anyway."""
    loser = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M", "call_or_put": "call"}

    def fake_close_row(row, evaluation, timestamp):
        row["outcome"] = "LOSS"
        return "LOSS"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[loser]),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 14, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "mark": 0.30, "pl_dollars": -55, "pl_pct": -40}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row) as close_row,
        mock.patch.object(spy_scanner, "write_log"),
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "safe_discord_call"),
        mock.patch.object(spy_scanner, "post_close"),
        mock.patch.object(spy_scanner, "sync_closed_result_channels"),
    ):
        reply = bot.force_sell_reply(_owner_interaction("call"))

    close_row.assert_called_once()
    assert loser["outcome"] == "LOSS"
    assert "-55" in reply


def test_immediately_routes_and_cleans_up_the_stale_card():
    """Same real bug guard as /close-profitable's own regression test:
    post_close alone leaves a stale HOLD card in #held-positions until
    the next automated scan cycle (up to ~15-20 minutes away).
    sync_closed_result_channels must run inline, not be deferred."""
    row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M", "call_or_put": "call"}
    rows = [row]

    def fake_close_row(r, evaluation, timestamp):
        r["outcome"] = "LOSS"
        return "LOSS"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 14, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "mark": 0.30, "pl_dollars": -55, "pl_pct": -40}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row),
        mock.patch.object(spy_scanner, "write_log"),
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={"report": "state"}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "post_close"),
        mock.patch.object(spy_scanner, "sync_closed_result_channels") as sync_closed,
    ):
        bot.force_sell_reply(_owner_interaction("call"))

    sync_closed.assert_called_once_with(rows, "fake-tracker", {"report": "state"})


def test_signal_is_relabeled_manual_close_not_the_real_exit_reason():
    """Same real bug guard as /close-profitable's own regression test:
    close_row() does NOT itself write row["last_signal"] - the command
    must set it explicitly after close_row returns."""
    row = {"outcome": "OPEN", "option_symbol": "SPY260813P00780000", "play_type": "SPY_0DTE_5M", "call_or_put": "put"}
    captured_evaluation = {}

    def fake_close_row(r, evaluation, timestamp):
        captured_evaluation.update(evaluation)
        r["outcome"] = "LOSS"
        return "LOSS"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[row]),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 14, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "pl_dollars": -30, "pl_pct": -15}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row),
        mock.patch.object(spy_scanner, "write_log"),
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "safe_discord_call"),
        mock.patch.object(spy_scanner, "post_close"),
        mock.patch.object(spy_scanner, "sync_closed_result_channels"),
    ):
        bot.force_sell_reply(_owner_interaction("put"))

    assert captured_evaluation["signal"] == "MANUAL CLOSE"
    assert row["last_signal"] == "MANUAL CLOSE"
