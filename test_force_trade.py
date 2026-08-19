"""Tests for /force-trade: owner-forced manual SPY 0DTE entry that finds
the best real contract matching the requested direction using the same
contract-selection standards SPY_0DTE already uses, then hands it off to
the exact same live exit rule every SPY_0DTE trade uses - "the traders
open the best position they can find and then proceeds to go based off
the traders rules." evolve_bot is untouched by this command entirely."""

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


def _candidate(strike: float = 600.0, kind: str = "call", score: float = 42.0) -> dict:
    return {
        "play_type": spy_scanner.SPY_MANUAL_PLAY_TYPE,
        "call_or_put": kind,
        "strike": str(strike),
        "expiration": "2026-08-12",
        "entry_price": 0.75,
        "cost_or_credit": "0.75",
        "delta": 0.42,
        "theta": -0.3,
        "iv": 0.3,
        "pop": 42.0,
        "max_profit": "UNLIMITED",
        "max_risk": 75.0,
        "breakeven": strike + 0.75,
        "open_interest": 500,
        "bid_ask_width": 0.05,
        "option_volume": 200,
        "option_symbol": f"SPY260812C00{int(strike)}000",
        "score": score,
        "setup_reason": "Manually forced via /force-trade.",
        "market_regime": "BULLISH / CONTROLLED",
    }


def test_non_owner_cannot_force_a_trade():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {
        "member": {"user": {"id": "someone-else"}},
        "data": {"options": [{"name": "direction", "value": "call"}]},
    }
    with mock.patch.object(spy_scanner, "read_log") as read_log:
        try:
            bot.force_trade_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        read_log.assert_not_called()


def test_rejects_an_invalid_direction():
    try:
        bot.force_trade_reply(_owner_interaction("straddle"))
        assert False, "should have raised"
    except ValueError as exc:
        assert "direction" in str(exc)


def test_returns_early_with_no_spot_quote():
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "get_quote", return_value=None),
    ):
        reply = bot.force_trade_reply(_owner_interaction())
    assert "current SPY quote" in reply


def test_returns_early_with_no_same_day_expiration():
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "600.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 12, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "get_expirations", return_value=["2026-08-19"]),
    ):
        reply = bot.force_trade_reply(_owner_interaction())
    assert "No same-day SPY expiration" in reply


def test_returns_early_when_no_candidate_clears_the_filters():
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "600.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 12, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(spy_scanner, "filter_strikes", return_value=[600.0]),
        mock.patch.object(spy_scanner, "get_strikes", return_value=[600.0]),
        mock.patch.object(spy_scanner, "get_chain", return_value=[{"strike": 600.0, "option_type": "call"}]),
        mock.patch.object(spy_scanner, "scan_spy_contract_candidates", return_value=[]),
    ):
        reply = bot.force_trade_reply(_owner_interaction())
    assert "nothing forced" in reply


def test_returns_early_when_exposure_cap_leaves_nothing_selected():
    candidate = _candidate()
    with (
        mock.patch.object(spy_scanner, "read_log", return_value=[]),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "600.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 12, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(spy_scanner, "filter_strikes", return_value=[600.0]),
        mock.patch.object(spy_scanner, "get_strikes", return_value=[600.0]),
        mock.patch.object(spy_scanner, "get_chain", return_value=[{"strike": 600.0, "option_type": "call"}]),
        mock.patch.object(spy_scanner, "scan_spy_contract_candidates", return_value=[candidate]),
        mock.patch.object(spy_scanner, "recently_tracked", return_value=False),
        mock.patch.object(spy_scanner, "apply_ticker_exposure_cap", return_value=[]),
    ):
        reply = bot.force_trade_reply(_owner_interaction())
    assert "exposure cap" in reply.lower() or "cooldown" in reply.lower()


def test_opens_the_best_candidate_tagged_as_spy_manual_and_posts_it():
    candidate = _candidate(strike=600.0, score=42.0)
    weaker_candidate = _candidate(strike=605.0, score=10.0)
    rows: list[dict[str, str]] = []

    def fake_candidate_to_row(cand, rows_arg, timestamp, *, market_condition=""):
        row = spy_scanner.blank_row()
        row.update({
            "trade_id": "SPY-20260812-099",
            "play_type": cand["play_type"],
            "call_or_put": cand["call_or_put"],
            "strike": cand["strike"],
            "expiration": cand["expiration"],
            "entry_price": str(cand["entry_price"]),
            "delta_at_entry": str(cand["delta"]),
            "max_risk": str(cand["max_risk"]),
            "option_symbol": cand["option_symbol"],
            "outcome": "OPEN",
        })
        return row

    with (
        mock.patch.object(spy_scanner, "read_log", return_value=rows),
        mock.patch.object(spy_scanner, "get_quote", return_value={"last": "600.0"}),
        mock.patch.object(spy_scanner, "now_ct", return_value=datetime(2026, 8, 12, 10, 0, tzinfo=CT)),
        mock.patch.object(spy_scanner, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(spy_scanner, "filter_strikes", return_value=[600.0, 605.0]),
        mock.patch.object(spy_scanner, "get_strikes", return_value=[600.0, 605.0]),
        mock.patch.object(spy_scanner, "get_chain", return_value=[
            {"strike": 600.0, "option_type": "call"}, {"strike": 605.0, "option_type": "call"},
        ]),
        mock.patch.object(spy_scanner, "scan_spy_contract_candidates", return_value=[weaker_candidate, candidate]),
        mock.patch.object(spy_scanner, "recently_tracked", return_value=False),
        mock.patch.object(spy_scanner, "apply_ticker_exposure_cap", side_effect=lambda eligible, r, t: eligible),
        mock.patch.object(spy_scanner, "candidate_to_row", side_effect=fake_candidate_to_row) as fake_to_row,
        mock.patch.object(spy_scanner, "write_log") as fake_write_log,
        mock.patch.object(spy_scanner, "initialize_discord", return_value="fake-tracker"),
        mock.patch.object(spy_scanner, "read_report_state", return_value={}),
        mock.patch.object(spy_scanner, "write_report_state") as fake_write_report_state,
        mock.patch.object(spy_scanner, "safe_discord_call") as fake_safe_discord_call,
        mock.patch.object(spy_scanner, "post_new_trade") as fake_post_new_trade,
        mock.patch.object(spy_scanner, "get_quotes", return_value={}),
        mock.patch.object(spy_scanner, "evaluate_open_row", return_value={"pl_pct": 0, "mark": 0.75}),
        mock.patch.object(spy_scanner, "sync_open_trade_cards") as fake_sync_cards,
    ):
        reply = bot.force_trade_reply(_owner_interaction("call"))

    # The higher-scored candidate (600 strike) was selected, not the
    # first one found in the raw candidate list.
    assert fake_to_row.call_args[0][0] is candidate
    assert fake_to_row.call_args[0][0]["play_type"] == spy_scanner.SPY_MANUAL_PLAY_TYPE
    fake_write_log.assert_called_once()
    fake_write_report_state.assert_called_once()
    assert fake_safe_discord_call.call_count == 2  # post_new_trade + sync_open_trade_cards
    assert "SPY-20260812-099" in reply
    assert "CALL" in reply
