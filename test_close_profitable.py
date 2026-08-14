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
    # One safe_discord_call for post_close (journal thread) plus one for
    # sync_closed_result_channels (wins/losses routing + stale held-
    # positions card cleanup) - see the regression test below for why
    # the second call has to happen here, not just on the next automated
    # scan cycle.
    assert safe_discord_call.call_count == 2
    assert "120" in reply
    assert "1 profitable position" in reply


def test_close_profitable_immediately_routes_and_cleans_up_the_stale_card():
    """Regression guard for a real bug: post_close only posts the close
    alert into the trade's own journal thread - it never moves the trade
    to its wins/losses channel or deletes the now-stale entry/held-
    positions cards. That only happened via sync_closed_result_channels,
    called from the automated scan cycle, which could be up to ~15-20
    minutes away. Found from a real screenshot: a position closed via
    /close-profitable as a WIN still showed a stale "HOLD" card with its
    pre-close P&L in #held-positions a minute later. This must run
    inline, immediately, not wait for the next scan cycle."""
    winner = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    rows = [winner]

    def fake_close_row(row, evaluation, timestamp):
        row["outcome"] = "WIN"
        return "WIN"

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "780.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 13, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"signal": "HOLD", "mark": 0.75, "pl_dollars": 120, "pl_pct": 50}),
        mock.patch.object(spy_scanner, "close_row", side_effect=fake_close_row),
        mock.patch.object(spy_scanner, "write_log"),
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={"report": "state"}),
        mock.patch.object(spy_scanner, "write_report_state"),
        mock.patch.object(spy_scanner, "post_close"),
        mock.patch.object(spy_scanner, "sync_closed_result_channels") as sync_closed,
    ):
        bot.close_profitable_reply(_owner_interaction())

    sync_closed.assert_called_once_with(rows, "fake-tracker", {"report": "state"})


def test_signal_is_relabeled_manual_close_not_the_real_exit_reason():
    """Regression guard for a real bug: close_row() does NOT itself write
    row["last_signal"] - that field is only ever set earlier, inside
    evaluate_open_row's own apply_evaluation_to_row side effect, using
    the real rule-based signal (e.g. "HOLD"). The first version of this
    command passed signal="MANUAL CLOSE" into close_row and assumed that
    was enough, but the row's own last_signal silently stayed "HOLD" -
    found from real closed rows in state/spy-plays-log.csv, not from a
    test, because this test originally only checked the dict passed
    INTO close_row, never the row's own field afterward. fake_close_row
    below deliberately mirrors the real function's behavior (does NOT
    touch last_signal) so this test actually exercises the same gap."""
    row = {"outcome": "OPEN", "option_symbol": "SPY260813C00780000", "play_type": "SPY_0DTE_5M"}
    captured_evaluation = {}

    def fake_close_row(r, evaluation, timestamp):
        captured_evaluation.update(evaluation)
        r["outcome"] = "WIN"
        # Deliberately does NOT set r["last_signal"] - matches the real
        # close_row's actual behavior.
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
    assert row["last_signal"] == "MANUAL CLOSE"  # the row itself, not just what was passed to close_row
