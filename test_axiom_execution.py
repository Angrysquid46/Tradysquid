"""Real tests for execution.py's fill model - no mid-price fills, ever."""

from __future__ import annotations

from bots.claude.execution import build_execution_assumptions, entry_fill_price, exit_fill_price, spread_ok


def test_entry_fill_is_real_ask_not_mid():
    contract = {"bid": 3.8, "ask": 4.0}
    assert entry_fill_price(contract) == 4.0


def test_exit_fill_is_real_bid_not_mid():
    contract = {"bid": 3.8, "ask": 4.0}
    assert exit_fill_price(contract) == 3.8


def test_spread_ok_accepts_tight_spread():
    assert spread_ok({"bid": 3.95, "ask": 4.0}) is True


def test_spread_ok_rejects_wide_spread():
    assert spread_ok({"bid": 1.0, "ask": 4.0}) is False


def test_spread_ok_rejects_bad_quotes():
    assert spread_ok({"bid": 0, "ask": 4.0}) is False
    assert spread_ok({"bid": 4.0, "ask": 3.9}) is False
    assert spread_ok({"bid": None, "ask": 4.0}) is False


def test_execution_assumptions_disclose_no_hindsight_or_mid_fills():
    assumptions = build_execution_assumptions()
    assert assumptions["mid_price_fills"] is False
    assert assumptions["hindsight_fills"] is False
    assert assumptions["fake_liquidity"] is False
