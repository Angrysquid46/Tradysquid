"""Phase 5 step 2 - model what a 0DTE contract was worth intraday.

The archive is EOD-only, so no real intraday option quote exists anywhere
in it. Every price this module returns is **modelled**, and every caller
is expected to label it as such. What is real is the implied-volatility
level, taken from the actual chain on the actual day; what is modelled is
the price that IV implies at a given minute.

Why this matters more here than for most instruments: a 0DTE option's
value is almost entirely time value at 09:45 and almost entirely
intrinsic by 15:59. That decay is the single biggest determinant of
whether an underlying edge survives, and it is exactly what the EOD
snapshot cannot show. So it is computed explicitly rather than assumed
away.

Deliberately conservative choices, because every one of them decides
whether a marginal strategy reads as profitable:

- Entry pays the **ask**, exit receives the **bid**. Never mid.
- The spread is taken from the real chain where available, and floored at
  a minimum, because a modelled mid-price round-trip would invent money
  that no real fill ever produced.
- Time to expiry is measured to 16:00 ET on the expiry date, in
  years, and never allowed to reach exactly zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Trading-day fractions. A 0DTE option expires at the close, so a trade
# entered at 09:45 has 6.25 hours of life, not a full day.
SESSION_OPEN_MINUTES = 9 * 60 + 30
SESSION_CLOSE_MINUTES = 16 * 60
MINUTES_PER_SESSION = SESSION_CLOSE_MINUTES - SESSION_OPEN_MINUTES   # 390
MINUTES_PER_YEAR = 252 * MINUTES_PER_SESSION

RISK_FREE_RATE = 0.02          # flat; 0DTE is far too short for this to matter
MIN_SPREAD = 0.02              # floor on the bid/ask spread, in dollars
MIN_TIME_YEARS = 1e-6          # never divide by a zero clock


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(
    spot: float, strike: float, time_years: float, vol: float,
    kind: str, rate: float = RISK_FREE_RATE,
) -> float:
    """Standard Black-Scholes, floored at intrinsic.

    At the very end of a 0DTE's life the formula degenerates, so the
    result is clamped to intrinsic value - which is what the contract is
    actually worth at expiry, and stops the model returning a negative or
    absurd price in the final minutes."""
    intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
    if time_years <= MIN_TIME_YEARS or vol <= 0 or spot <= 0 or strike <= 0:
        return intrinsic

    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    discount = math.exp(-rate * time_years)

    if kind == "call":
        price = spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    else:
        price = strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return max(price, intrinsic)


def delta(spot: float, strike: float, time_years: float, vol: float,
          kind: str, rate: float = RISK_FREE_RATE) -> float:
    if time_years <= MIN_TIME_YEARS or vol <= 0 or spot <= 0 or strike <= 0:
        if kind == "call":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_years) / (vol * sqrt_t)
    return _norm_cdf(d1) if kind == "call" else _norm_cdf(d1) - 1.0


def time_to_close_years(minutes_since_open: int) -> float:
    """Years remaining until this session's 16:00 close.

    A 0DTE entered at 09:45 has 375 of 390 session minutes left - about
    0.0060 years. Using a full day instead would understate decay by
    roughly two orders of magnitude and make every strategy look better
    than it was."""
    remaining = max(MINUTES_PER_SESSION - minutes_since_open, 0)
    return max(remaining / MINUTES_PER_YEAR, MIN_TIME_YEARS)


@dataclass
class ModelledQuote:
    """A modelled option price. `modelled` is always True - it exists so
    the flag travels with the number into every report."""
    strike: float
    kind: str
    mid: float
    bid: float
    ask: float
    delta: float
    vol: float
    minutes_since_open: int
    modelled: bool = True


def quote(
    spot: float, strike: float, minutes_since_open: int, vol: float, kind: str,
    *, spread: float | None = None,
) -> ModelledQuote:
    """Model one contract at one minute.

    `spread` should come from the real chain for that day when available;
    when it does not, a proportional estimate is used with a hard floor.
    Either way the caller pays the ask and receives the bid, never mid."""
    time_years = time_to_close_years(minutes_since_open)
    mid = black_scholes(spot, strike, time_years, vol, kind)
    if spread is None:
        # Thin 0DTE contracts are proportionally wider; 2% of price with a
        # floor is deliberately pessimistic rather than optimistic.
        spread = max(mid * 0.02, MIN_SPREAD)
    width = max(spread, MIN_SPREAD)
    # The bid cannot go negative, but clamping it must not quietly halve
    # the spread on a near-worthless contract - that is exactly where
    # 0DTE round-trip costs bite hardest. Anchor the bid, then place the
    # ask a full width above it so the crossing cost is always paid.
    bid = max(mid - width / 2.0, 0.0)
    return ModelledQuote(
        strike=strike, kind=kind, mid=mid,
        bid=bid, ask=bid + width,
        delta=delta(spot, strike, time_years, vol, kind),
        vol=vol, minutes_since_open=minutes_since_open,
    )


def select_strike(
    spot: float, minutes_since_open: int, vol: float, kind: str,
    target_delta: float, *, step: float = 1.0, search: int = 25,
) -> float:
    """The strike whose modelled delta is closest to `target_delta`.

    The live scanners pick contracts by delta band, not by strike, so the
    backtest has to do the same or it is testing a different trade."""
    time_years = time_to_close_years(minutes_since_open)
    base = round(spot / step) * step
    best_strike, best_gap = base, float("inf")
    for offset in range(-search, search + 1):
        candidate = base + offset * step
        if candidate <= 0:
            continue
        candidate_delta = abs(delta(spot, candidate, time_years, vol, kind))
        gap = abs(candidate_delta - abs(target_delta))
        if gap < best_gap:
            best_strike, best_gap = candidate, gap
    return best_strike


def implied_vol_for_session(conn, session: str, *, max_dte: int = 3) -> float | None:
    """A real IV level for a session, from the actual chain that day.

    Prefers a same-day (0DTE) near-the-money quote. Falls back to the
    nearest short-dated one, then to the prior session, because a 0DTE
    listing did not exist on most days before 2023. Returns None when the
    day has no usable chain at all - the honest answer, since a strategy
    could not have bought a 0DTE that never existed."""
    row = conn.execute(
        """
        SELECT call_iv, put_iv FROM eod_chain
        WHERE quote_date = ? AND dte <= ?
          AND (call_iv IS NOT NULL OR put_iv IS NOT NULL)
        ORDER BY dte ASC, abs(strike_distance_pct) ASC
        LIMIT 1
        """,
        (session, max_dte),
    ).fetchone()
    if row is None:
        row = conn.execute(
            """
            SELECT call_iv, put_iv FROM eod_chain
            WHERE quote_date < ? AND dte <= ?
              AND (call_iv IS NOT NULL OR put_iv IS NOT NULL)
            ORDER BY quote_date DESC, dte ASC, abs(strike_distance_pct) ASC
            LIMIT 1
            """,
            (session, max_dte),
        ).fetchone()
    if row is None:
        return None

    values = [v for v in (row["call_iv"], row["put_iv"]) if v is not None and 0 < v < 5]
    return (sum(values) / len(values)) if values else None


def sessions_with_zero_dte(conn) -> set[str]:
    """Sessions where a same-day expiry actually existed.

    Before 2023 most days had none. Scoring a 0DTE strategy on a day when
    no 0DTE was listed would be measuring a contract nobody could buy."""
    return {
        row["quote_date"]
        for row in conn.execute("SELECT DISTINCT quote_date FROM eod_chain WHERE dte = 0")
    }
