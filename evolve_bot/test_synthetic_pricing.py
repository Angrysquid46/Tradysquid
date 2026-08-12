from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

import synthetic_pricing as pricing

CT = ZoneInfo("America/Chicago")


def test_intrinsic_value_for_a_call_is_spot_minus_strike_when_positive():
    assert pricing.intrinsic_value(610.0, 600.0, "call") == 10.0


def test_intrinsic_value_for_a_call_is_zero_when_out_of_the_money():
    assert pricing.intrinsic_value(590.0, 600.0, "call") == 0.0


def test_intrinsic_value_for_a_put_is_strike_minus_spot_when_positive():
    assert pricing.intrinsic_value(590.0, 600.0, "put") == 10.0


def test_black_scholes_falls_back_to_intrinsic_at_zero_time_to_expiry():
    price = pricing.black_scholes_price(610.0, 600.0, 0.0, 0.20, "call")
    assert price == 10.0


def test_black_scholes_falls_back_to_intrinsic_for_zero_volatility():
    price = pricing.black_scholes_price(610.0, 600.0, 0.01, 0.0, "call")
    assert price == 10.0


def test_black_scholes_price_is_never_negative():
    price = pricing.black_scholes_price(500.0, 700.0, 0.001, 0.10, "call")
    assert price >= 0.0


def test_black_scholes_call_price_increases_with_spot():
    low = pricing.black_scholes_price(600.0, 605.0, 0.002, 0.20, "call")
    high = pricing.black_scholes_price(610.0, 605.0, 0.002, 0.20, "call")
    assert high > low


def test_black_scholes_put_price_decreases_with_spot():
    low_spot = pricing.black_scholes_price(595.0, 605.0, 0.002, 0.20, "put")
    high_spot = pricing.black_scholes_price(610.0, 605.0, 0.002, 0.20, "put")
    assert low_spot > high_spot


def test_black_scholes_price_decays_toward_expiration_theta_decay():
    # Same spot/strike/vol, less time left -> a lower premium for an
    # out-of-the-money option (time value shrinking, no intrinsic value
    # to offset it).
    more_time = pricing.black_scholes_price(600.0, 605.0, 0.01, 0.20, "call")
    less_time = pricing.black_scholes_price(600.0, 605.0, 0.001, 0.20, "call")
    assert less_time < more_time


def test_black_scholes_price_increases_with_volatility():
    low_vol = pricing.black_scholes_price(600.0, 605.0, 0.005, 0.10, "call")
    high_vol = pricing.black_scholes_price(600.0, 605.0, 0.005, 0.40, "call")
    assert high_vol > low_vol


def test_black_scholes_call_and_put_at_the_money_are_close_with_small_rate():
    # Put-call parity roughly holds ATM when the risk-free rate's effect
    # over a few hours is tiny - not an exact equality (parity involves
    # the discount factor), just a sanity bound this shouldn't wildly miss.
    call = pricing.black_scholes_price(600.0, 600.0, 0.002, 0.20, "call")
    put = pricing.black_scholes_price(600.0, 600.0, 0.002, 0.20, "put")
    assert abs(call - put) < 1.0


def test_years_remaining_in_trading_day_is_zero_past_close():
    close_time = datetime(2026, 8, 12, 15, 0, tzinfo=CT)
    moment = datetime(2026, 8, 12, 15, 30, tzinfo=CT)
    assert pricing.years_remaining_in_trading_day(moment, close_time) == 0.0


def test_years_remaining_in_trading_day_is_positive_before_close():
    close_time = datetime(2026, 8, 12, 15, 0, tzinfo=CT)
    moment = datetime(2026, 8, 12, 9, 0, tzinfo=CT)
    remaining = pricing.years_remaining_in_trading_day(moment, close_time)
    assert remaining > 0.0
    # 6 hours out of a 6.5-hour session, out of 252 trading days/year.
    expected = (6.0 / pricing.TRADING_HOURS_PER_DAY) / pricing.TRADING_DAYS_PER_YEAR
    assert abs(remaining - expected) < 1e-9


def test_years_remaining_shrinks_as_the_day_progresses():
    close_time = datetime(2026, 8, 12, 15, 0, tzinfo=CT)
    early = pricing.years_remaining_in_trading_day(datetime(2026, 8, 12, 9, 0, tzinfo=CT), close_time)
    late = pricing.years_remaining_in_trading_day(datetime(2026, 8, 12, 14, 0, tzinfo=CT), close_time)
    assert late < early


def test_estimate_implied_volatility_returns_a_reasonable_fallback_with_no_history():
    assert pricing.estimate_implied_volatility([]) == 0.20


def test_estimate_implied_volatility_is_positive_for_real_looking_bars():
    bars = [{"close": 600.0 + i * 0.5} for i in range(25)]
    vol = pricing.estimate_implied_volatility(bars)
    assert vol > 0.0


def test_black_scholes_delta_call_is_between_zero_and_one():
    delta = pricing.black_scholes_delta(600.0, 605.0, 0.002, 0.20, "call")
    assert 0.0 < delta < 1.0


def test_black_scholes_delta_put_is_between_negative_one_and_zero():
    delta = pricing.black_scholes_delta(600.0, 605.0, 0.002, 0.20, "put")
    assert -1.0 < delta < 0.0


def test_black_scholes_delta_call_increases_with_spot():
    low = pricing.black_scholes_delta(590.0, 605.0, 0.002, 0.20, "call")
    high = pricing.black_scholes_delta(615.0, 605.0, 0.002, 0.20, "call")
    assert high > low


def test_black_scholes_delta_falls_back_to_fully_itm_at_zero_time_to_expiry():
    assert pricing.black_scholes_delta(610.0, 600.0, 0.0, 0.20, "call") == 1.0
    assert pricing.black_scholes_delta(590.0, 600.0, 0.0, 0.20, "call") == 0.0


def test_black_scholes_delta_put_falls_back_to_fully_itm_at_zero_time_to_expiry():
    assert pricing.black_scholes_delta(590.0, 600.0, 0.0, 0.20, "put") == -1.0
    assert pricing.black_scholes_delta(610.0, 600.0, 0.0, 0.20, "put") == 0.0


def test_estimate_implied_volatility_scales_up_with_the_risk_premium_multiplier():
    bars = [{"close": 600.0 + (i % 3) * 2.0} for i in range(25)]  # some real variance
    low_premium = pricing.estimate_implied_volatility(bars, risk_premium_multiplier=1.0)
    high_premium = pricing.estimate_implied_volatility(bars, risk_premium_multiplier=1.5)
    assert high_premium > low_premium
