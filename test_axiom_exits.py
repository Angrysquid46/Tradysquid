"""Real tests for exits.py - profit target, stop, and time-force-close
each fire at the right boundary."""

from __future__ import annotations

from datetime import datetime

from bots.claude.exits import PROFIT_TARGET, STOP_LOSS, TIME_FORCE_CLOSE, should_exit
from bots.claude.parameters import Parameters

PARAMS = Parameters()
MID_DAY = datetime(2026, 8, 25, 12, 0, 0)


def _trade(entry_price=4.0):
    return {"entry_price": entry_price}


def test_profit_target_fires_at_or_above_threshold():
    contract = {"bid": 5.61, "ask": 5.62}  # pnl_pct = 0.4025, just past +40%
    decision = should_exit(_trade(), contract, MID_DAY, PARAMS)
    assert decision.should_exit is True
    assert decision.reason == PROFIT_TARGET


def test_no_exit_just_below_profit_target():
    contract = {"bid": 5.59, "ask": 5.60}  # pnl_pct = 0.3975, just short of +40%
    decision = should_exit(_trade(), contract, MID_DAY, PARAMS)
    assert decision.should_exit is False


def test_stop_loss_fires_at_or_below_threshold():
    contract = {"bid": 2.59, "ask": 2.60}  # pnl_pct = -0.3525, past -35%
    decision = should_exit(_trade(), contract, MID_DAY, PARAMS)
    assert decision.should_exit is True
    assert decision.reason == STOP_LOSS


def test_no_exit_just_above_stop_loss():
    contract = {"bid": 2.61, "ask": 2.62}  # pnl_pct = -0.3475, just short of -35%
    decision = should_exit(_trade(), contract, MID_DAY, PARAMS)
    assert decision.should_exit is False


def test_time_force_close_fires_at_boundary():
    at_boundary = datetime(2026, 8, 25, 14, 45, 0)
    contract = {"bid": 4.0, "ask": 4.01}  # flat pnl, would otherwise hold
    decision = should_exit(_trade(), contract, at_boundary, PARAMS)
    assert decision.should_exit is True
    assert decision.reason == TIME_FORCE_CLOSE


def test_no_force_close_just_before_boundary():
    before_boundary = datetime(2026, 8, 25, 14, 44, 59)
    contract = {"bid": 4.0, "ask": 4.01}
    decision = should_exit(_trade(), contract, before_boundary, PARAMS)
    assert decision.should_exit is False


def test_force_close_overrides_a_still_open_profit_window():
    at_boundary = datetime(2026, 8, 25, 14, 45, 0)
    contract = {"bid": 4.05, "ask": 4.06}  # small unrealized gain, not at target
    decision = should_exit(_trade(), contract, at_boundary, PARAMS)
    assert decision.should_exit is True
    assert decision.reason == TIME_FORCE_CLOSE
