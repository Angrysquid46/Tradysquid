"""Tests for /close-profitable: manually closes every currently open
position that's genuinely in profit right now, using the exact same
evaluate_open_row/close_row/post_close functions the automated scan cycle
uses for a real exit - never force-closes a position that isn't actually
profitable, and never touches anything besides the paper-trading log."""

from __future__ import annotations

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import discord_command_bot as bot
import spy_scanner

CT = ZoneInfo("America/Chicago")


def _owner_interaction():
    bot.ALLOWED_USER_ID = "owner-1"
    return {"member": {"user": {"id": "owner-1"}}, "data": {}}


def test_non_owner_cannot_close_positions():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {"member": {"user": {"id": "someone-else"}}, "data": {}}
    with mock.patch.object(spy_scanner, "read_log") as read_log:
        try:
            bot.close_profitable_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        read_log.assert_not_called()


def test_no_open_positions_closes_nothing():
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "write_log") as write_log,
    ):
        reply = bot.close_profitable_reply(_owner_interaction())
    assert "No open positions" in reply
    write_log.assert_not_called()


def test_no_profitable_positions_leaves_everything_open():
    row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    rows = [row]
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 13, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "pl_dollars": -25, "pl_pct": -10}),
        mock.patch.object(spy_scanner, "close_row") as close_row,
        mock.patch.object(spy_scanner, "write_log") as write_log,
    ):
        reply = bot.close_profitable_reply(_owner_interaction())
    assert "none are currently profitable" in reply
    close_row.assert_not_called()
    assert row["outcome"] == "OPEN"  # never mutated
    write_log.assert_called_once_with(rows)


def test_a_position_with_an_unreliable_quote_is_never_force_closed():
    row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[row]),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value=None),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 13, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "pl_dollars": None, "pl_pct": None}),
        mock.patch.object(spy_scanner, "close_row") as close_row,
        mock.patch.object(spy_scanner, "write_log"),
    ):
        reply = bot.close_profitable_reply(_owner_interaction())
    close_row.assert_not_called()
    assert "none are currently profitable" in reply


def test_closes_only_the_profitable_positions_and_leaves_losers_open():
    winner = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    loser = {"outcome": "OPEN", "option_symbol": "SPY260813P00770000", "play_type": "SPY_KEY_LEVELS"}
    rows = [winner, loser]

    def fake_evaluate(row, quotes, timestamp, underlying_spot_price=None):
        if row is winner:
            return {"signal": "HOLD", "mark": 0.75, "pl_dollars": 120, "pl_pct": 50}
        return {"signal": "HOLD", "mark": 0.30, "pl_dollars": -40, "pl_pct": -20}

    def fake_close_row(row, evaluation, timestamp):
        row["outcome"] = "WIN"
        return "WIN"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 13, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", side_effect=fake_evaluate),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row) as close_row,
        mock.patch.object(spy_scanner, "write_log") as write_log,
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state") as write_report_state,
        mock.patch.object(spy_scanner, "safe_discord_call") as safe_discord_call,
        mock.patch.object(spy_scanner, "post_close") as post_close,
    ):
        reply = bot.close_profitable_reply(_owner_interaction())

    close_row.assert_called_once()
    assert close_row.call_args[0][0] is winner  # only the profitable row was closed
    assert winner["outcome"] == "WIN"
    assert loser["outcome"] == "OPEN"  # the loser is never touched
    write_log.assert_called_once_with(rows)
    write_report_state.assert_called_once()
    safe_discord_call.assert_called_once()
    assert "120" in reply
    assert "1 profitable position" in reply


def test_signal_is_relabeled_manual_close_not_the_real_exit_reason():
    row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    captured_evaluation = {}

    def fake_close_row(r, evaluation, timestamp):
        captured_evaluation.update(evaluation)
        r["outcome"] = "WIN"
        return "WIN"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[row]),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 13, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "pl_dollars": 50, "pl_pct": 20}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row),
        mock.patch.object(spy_scanner, "write_log"),
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "safe_discord_call"),
        mock.patch.object(spy_scanner, "post_close"),
    ):
        bot.close_profitable_reply(_owner_interaction())

    assert captured_evaluation["signal"] == "MANUAL CLOSE"
