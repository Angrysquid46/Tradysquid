"""Tests for the Phase 5 option pricing model.

The model decides whether an underlying edge survives as a 0DTE trade, so
the failure mode to guard against is a model that is quietly too kind:
too little decay, mid-price fills, a full trading day of time value on a
contract with six hours left. Each of those would turn a losing strategy
into a winning one on paper.
"""

from __future__ import annotations

import math

import pytest

import spy_option_model as om


# ---------------------------------------------------------------------------
# Black-Scholes basics
# ---------------------------------------------------------------------------

def test_call_and_put_satisfy_put_call_parity():
    spot, strike, t, vol = 400.0, 400.0, 0.01, 0.20
    call = om.black_scholes(spot, strike, t, vol, "call")
    put = om.black_scholes(spot, strike, t, vol, "put")
    expected = spot - strike * math.exp(-om.RISK_FREE_RATE * t)
    assert (call - put) == pytest.approx(expected, abs=0.01)


def test_price_is_never_below_intrinsic():
    deep = om.black_scholes(420.0, 400.0, 0.001, 0.15, "call")
    assert deep >= 20.0 - 0.01
    deep_put = om.black_scholes(380.0, 400.0, 0.001, 0.15, "put")
    assert deep_put >= 20.0 - 0.01


def test_at_expiry_the_option_is_worth_exactly_intrinsic():
    assert om.black_scholes(405.0, 400.0, 0.0, 0.2, "call") == pytest.approx(5.0)
    assert om.black_scholes(395.0, 400.0, 0.0, 0.2, "call") == pytest.approx(0.0)
    assert om.black_scholes(395.0, 400.0, 0.0, 0.2, "put") == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# The decay that decides Phase 5
# ---------------------------------------------------------------------------

def test_time_to_close_uses_the_session_not_a_whole_day():
    """A 0DTE entered at 09:45 has 375 session minutes left, ~0.0060
    years. Treating it as a full calendar day would understate decay by
    orders of magnitude and make every strategy look better than it was."""
    at_0945 = om.time_to_close_years(15)
    assert at_0945 == pytest.approx(375 / (252 * 390), rel=1e-6)
    assert at_0945 < 0.007

    assert om.time_to_close_years(389) < at_0945
    assert om.time_to_close_years(390) > 0          # never exactly zero


def test_an_atm_option_loses_almost_all_its_value_by_the_close():
    """The central fact of 0DTE: an at-the-money contract held to the
    bell with the underlying unchanged goes to nearly nothing. If this
    ever stops being true the model has stopped modelling 0DTE."""
    spot = strike = 400.0
    morning = om.black_scholes(spot, strike, om.time_to_close_years(15), 0.15, "call")
    close = om.black_scholes(spot, strike, om.time_to_close_years(389), 0.15, "call")
    assert morning > 0.5
    assert close < morning * 0.1


def test_holding_to_the_close_destroys_a_flat_trade():
    """Directly the scenario the shortlist is exposed to: 89-97% of the
    winning strategies exit at the session close."""
    entry = om.quote(400.0, 400.0, 15, 0.15, "call")
    exit_quote = om.quote(400.0, 400.0, 389, 0.15, "call")
    assert exit_quote.bid < entry.ask * 0.2


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------

def test_entry_pays_the_ask_and_exit_receives_the_bid():
    q = om.quote(400.0, 400.0, 60, 0.15, "call")
    assert q.ask > q.mid > q.bid
    assert q.ask - q.bid >= om.MIN_SPREAD - 1e-9


def test_a_round_trip_with_no_price_move_loses_the_spread():
    """A mid-to-mid round trip would invent money no real fill produced."""
    entry = om.quote(400.0, 400.0, 60, 0.15, "call")
    exit_quote = om.quote(400.0, 400.0, 60, 0.15, "call")
    assert exit_quote.bid < entry.ask


def test_spread_never_collapses_below_the_floor():
    q = om.quote(400.0, 500.0, 60, 0.15, "call", spread=0.0)
    assert q.ask - q.bid == pytest.approx(om.MIN_SPREAD)


def test_bid_never_goes_negative():
    q = om.quote(400.0, 500.0, 389, 0.15, "call")
    assert q.bid >= 0.0


# ---------------------------------------------------------------------------
# Strike selection
# ---------------------------------------------------------------------------

def test_selected_strike_lands_near_the_requested_delta():
    """The live scanners choose by delta band, so the backtest must too -
    otherwise it is testing a different trade."""
    spot, vol = 400.0, 0.15
    for target in (0.40, 0.50, 0.60):
        strike = om.select_strike(spot, 15, vol, "call", target)
        achieved = abs(om.delta(spot, strike, om.time_to_close_years(15), vol, "call"))
        assert abs(achieved - target) < 0.12, f"target {target} got {achieved:.3f}"


def test_a_higher_delta_call_has_a_lower_strike():
    spot, vol = 400.0, 0.15
    low = om.select_strike(spot, 15, vol, "call", 0.30)
    high = om.select_strike(spot, 15, vol, "call", 0.70)
    assert high < low


def test_atm_delta_is_about_half():
    d = om.delta(400.0, 400.0, om.time_to_close_years(15), 0.15, "call")
    assert 0.45 < d < 0.60
    p = om.delta(400.0, 400.0, om.time_to_close_years(15), 0.15, "put")
    assert -0.60 < p < -0.40


def test_put_and_call_delta_are_consistent():
    t = om.time_to_close_years(60)
    call_d = om.delta(400.0, 398.0, t, 0.15, "call")
    put_d = om.delta(400.0, 398.0, t, 0.15, "put")
    assert (call_d - put_d) == pytest.approx(1.0, abs=0.01)
