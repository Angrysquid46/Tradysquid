"""Synthetic option candidate builder for historical backtest days.

Tradier doesn't serve a chain for an expired expiration (confirmed live -
see synthetic_pricing.py's module docstring), so there is no real chain to
run spy_scanner.scan_spy_contract_candidates against for a historical day. This
builds an equivalent candidate list directly: for each nearby $1-wide
strike, price and delta come from synthetic_pricing's Black-Scholes model,
then a real Robinhood price (if this exact contract/day was cached by
robinhood_cache.py) overrides the synthetic ask/bid - real data wins
whenever it's actually available, synthetic only fills the gap.

Deliberately does NOT apply spy_scanner.option_has_liquidity - that gate
reads real open_interest/volume off a real chain row, and there's no real
per-strike OI/volume for an expired 0DTE contract from either Tradier or
Robinhood (Robinhood's option historicals bars carry no volume field,
confirmed live). Every candidate this module returns is unfiltered on
liquidity - a known, documented gap between this backtest and live
trading, not an oversight.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import robinhood_cache
import synthetic_pricing as pricing

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

SPY_DELTA_MIN = s.SPY_DELTA_MIN
SPY_DELTA_MAX = s.SPY_DELTA_MAX
SPY_MAX_CONTRACT_ASK = s.SPY_MAX_CONTRACT_ASK
SPY_MAX_RISK_PER_TRADE = s.SPY_MAX_RISK_PER_TRADE


def strikes_near_spot(spot_price: float, band_pct: float = 0.03, width: float = 1.0) -> list[float]:
    """$1-wide SPY strikes within band_pct of spot - a tighter band than
    spy_scanner's own STRIKE_BAND_PCT (0.12) since a 0DTE delta-0.40-0.60
    candidate is always close to the money; no point pricing strikes miles
    away that would never pass the delta filter anyway."""
    low = spot_price * (1 - band_pct)
    high = spot_price * (1 + band_pct)
    start = int(low // width) * width
    strikes = []
    strike = start
    while strike <= high:
        if strike >= low:
            strikes.append(round(strike, 2))
        strike += width
    return strikes


def _real_price_at(option_symbol: str, moment_iso: str) -> tuple[float, float] | None:
    """Nearest cached real Robinhood bar at or before moment_iso, as
    (bid, ask) - Robinhood bars only carry a single OHLC series, not a
    separate bid/ask, so both sides use the bar's close as the best
    available real print."""
    bars = robinhood_cache.load_option_bars(option_symbol)
    if not bars:
        return None
    usable = [bar for bar in bars if bar["timestamp"] <= moment_iso]
    if not usable:
        return None
    close = usable[-1]["close"]
    return close, close


def build_candidates(
    spot_price: float,
    call_or_put: str,
    expiration: str,
    years_to_expiry: float,
    volatility: float,
    moment_iso: str,
    play_type: str = "SPY_EVOLVE_BACKTEST",
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for strike in strikes_near_spot(spot_price):
        delta = pricing.black_scholes_delta(spot_price, strike, years_to_expiry, volatility, call_or_put)
        if not SPY_DELTA_MIN <= abs(delta) <= SPY_DELTA_MAX:
            continue
        synthetic_price = pricing.black_scholes_price(spot_price, strike, years_to_expiry, volatility, call_or_put)
        symbol = s.option_symbol(s.SPY_CONTRACT_TICKER, expiration, call_or_put, strike)
        real = _real_price_at(symbol, moment_iso)
        if real is not None:
            bid, ask = real
            price_source = "real"
        else:
            bid, ask = synthetic_price, synthetic_price
            price_source = "synthetic"
        if ask <= 0:
            continue
        if ask > SPY_MAX_CONTRACT_ASK or ask * 100 > SPY_MAX_RISK_PER_TRADE:
            continue
        candidates.append(
            {
                "play_type": play_type,
                "call_or_put": call_or_put,
                "strike": s.fmt_strike(strike),
                "expiration": expiration,
                "entry_price": round(ask, 2),
                "delta": round(delta, 4),
                "iv": round(volatility, 4),
                "option_symbol": symbol,
                "spot_at_entry": spot_price,
                "price_source": price_source,
            }
        )
    candidates.sort(key=lambda c: c["entry_price"])
    return candidates
