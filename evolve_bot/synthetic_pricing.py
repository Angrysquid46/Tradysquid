"""Synthetic 0DTE option pricing for the backtest engine - real historical
option prices don't exist for expired 0DTE contracts (confirmed live:
even a symbol that traded yesterday returns "symbol not found" today, and
Tradier only retains ~29 days of 1-minute underlying bars anyway), so the
backtest prices a Black-Scholes premium against real historical
*underlying* price data instead of looking up real option prices. Same
conceptual approach as the theta-approximated synthetic premium already
used - and validated - for the 10 live ratchet-floor strategies' original
backtest; that sandbox script never lived in this repo, so this is a
fresh implementation of the same idea.

American vs. European: SPY 0DTE options are American-style, but the
early-exercise premium on an index-tracking ETF option this close to
expiration is negligible - a standard, well-documented simplification for
same-day options modeling, not a shortcut invented for this being "just a
backtest."
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

TRADING_HOURS_PER_DAY = 6.5
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.05  # annualized; small impact over a few hours, not zero


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def intrinsic_value(spot: float, strike: float, call_or_put: str) -> float:
    if call_or_put == "call":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def black_scholes_price(
    spot: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
    call_or_put: str,
    rate: float = RISK_FREE_RATE,
) -> float:
    """European Black-Scholes premium. Falls back to intrinsic value at or
    past expiration (years_to_expiry <= 0) rather than dividing by zero,
    and for a degenerate/zero volatility input - a synthetic price should
    never come back negative or undefined just because the day is over."""
    if years_to_expiry <= 0 or volatility <= 0 or spot <= 0 or strike <= 0:
        return intrinsic_value(spot, strike, call_or_put)
    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility**2) * years_to_expiry) / (
        volatility * sqrt_t
    )
    d2 = d1 - volatility * sqrt_t
    if call_or_put == "call":
        price = spot * _norm_cdf(d1) - strike * math.exp(-rate * years_to_expiry) * _norm_cdf(d2)
    else:
        price = strike * math.exp(-rate * years_to_expiry) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return max(price, 0.0)


def years_remaining_in_trading_day(moment: datetime, close_time: datetime) -> float:
    """Fraction of a trading YEAR remaining until close, for a 0DTE option
    expiring at today's close. Clamped to zero rather than going negative
    for a moment past the close."""
    seconds_remaining = max((close_time - moment).total_seconds(), 0.0)
    hours_remaining = seconds_remaining / 3600
    trading_days_remaining = hours_remaining / TRADING_HOURS_PER_DAY
    return trading_days_remaining / TRADING_DAYS_PER_YEAR


def estimate_implied_volatility(
    daily_bars: list[dict[str, Any]],
    lookback_days: int = 20,
    risk_premium_multiplier: float = 1.3,
) -> float:
    """0DTE implied vol isn't directly observable without real option
    data, so this approximates it from the underlying's own trailing
    realized volatility, scaled up by a fixed multiplier - real options
    typically trade at an IV premium above realized vol (the volatility
    risk premium), a well-documented market phenomenon, not a number
    invented for this project. This is an approximation, not a
    measurement - worth revisiting once enough real live trade data
    accumulates to calibrate the multiplier against actual fills instead
    of assuming it."""
    closes = [
        float(bar["close"])
        for bar in daily_bars[-(lookback_days + 1):]
        if bar.get("close") is not None
    ]
    if len(closes) < 2:
        return 0.20  # a reasonable fallback if there's not enough history yet
    returns = [
        math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0
    ]
    if not returns:
        return 0.20
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    daily_vol = math.sqrt(variance)
    annualized_vol = daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)
    return annualized_vol * risk_premium_multiplier
