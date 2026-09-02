"""GROK contract selection — DEGEN / MUST FILL.

Primary path: liquidity + spread + delta preferences.
Fallback path: any matching side with valid bid/ask that fits bankroll.
Hard ceiling remains bankroll affordability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SelectedContract:
    symbol: str
    side: str
    strike: float
    bid: float
    ask: float
    delta: float | None
    volume: int
    open_interest: int
    spread_pct: float
    contracts: int
    cost: float
    reason: str


def _side_match(otype: str, side: str) -> bool:
    o = otype.upper()
    if side == "CALL":
        return o in ("CALL", "C")
    if side == "PUT":
        return o in ("PUT", "P")
    return False


def _build(
    c: dict[str, Any],
    *,
    side: str,
    bid: float,
    ask: float,
    spread_pct: float,
    delta: float | None,
    volume: int,
    open_interest: int,
    contracts: int,
    reason: str,
) -> SelectedContract:
    cost_one = ask * 100
    symbol = str(c.get("symbol") or c.get("option_symbol") or "")
    strike = float(c.get("strike") or 0)
    return SelectedContract(
        symbol=symbol,
        side=side,
        strike=strike,
        bid=bid,
        ask=ask,
        delta=delta,
        volume=volume,
        open_interest=open_interest,
        spread_pct=spread_pct,
        contracts=contracts,
        cost=cost_one * contracts,
        reason=reason,
    )


def select_contract(
    side: str,
    chain: list[dict[str, Any]],
    bankroll: float,
    confidence: float,
    params: dict[str, Any] | None = None,
) -> SelectedContract | None:
    p = params or {}
    max_spread = p.get("max_spread_pct", 0.50)
    min_vol = p.get("min_volume", 0)
    min_oi = p.get("min_open_interest", 0)
    delta_lo, delta_hi = p.get("preferred_delta_range", (0.05, 0.85))

    primary: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []

    for c in chain:
        if not _side_match(str(c.get("option_type") or c.get("side") or ""), side):
            continue
        bid = float(c.get("bid") or 0)
        ask = float(c.get("ask") or 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid > 0 else 999
        cost_one = ask * 100
        if cost_one > bankroll + 0.01:
            continue

        vol = int(c.get("volume") or 0)
        oi = int(c.get("open_interest") or 0)
        delta_raw = c.get("delta")
        delta = abs(float(delta_raw)) if delta_raw is not None else None

        row = {
            "raw": c,
            "bid": bid,
            "ask": ask,
            "spread_pct": spread_pct,
            "delta": delta,
            "volume": vol,
            "open_interest": oi,
            "cost_one": cost_one,
        }

        # Always keep a fallback candidate if it can be filled
        fallback.append(row)

        if spread_pct > max_spread:
            continue
        if min_vol and min_oi and vol < min_vol and oi < min_oi:
            continue
        if delta is not None and not (delta_lo <= delta <= delta_hi):
            continue

        quality = max(0.0, 0.50 - spread_pct)
        if delta is not None:
            quality += max(0.0, 0.20 - abs(delta - 0.35))
        if vol >= 20:
            quality += 0.05
        if cost_one < 150:
            quality += 0.08
        row["quality"] = quality
        primary.append(row)

    chosen = None
    mode = "primary"
    if primary:
        primary.sort(key=lambda x: (-x.get("quality", 0), x["cost_one"]))
        chosen = primary[0]
    elif fallback:
        # Closest to ATM-ish by cheapest mid-priced ticket under bankroll
        fallback.sort(key=lambda x: (x["spread_pct"], x["cost_one"]))
        chosen = fallback[0]
        mode = "fallback"
    else:
        return None

    max_contracts = int(bankroll // chosen["cost_one"])
    if max_contracts < 1:
        return None

    if confidence >= 0.70:
        frac = 0.85
    elif confidence >= 0.45:
        frac = 0.65
    else:
        frac = 0.50
    contracts = max(1, min(max_contracts, int((bankroll * frac) // chosen["cost_one"])))

    return _build(
        chosen["raw"],
        side=side,
        bid=chosen["bid"],
        ask=chosen["ask"],
        spread_pct=chosen["spread_pct"],
        delta=chosen["delta"],
        volume=chosen["volume"],
        open_interest=chosen["open_interest"],
        contracts=contracts,
        reason=(
            f"{mode} spread={chosen['spread_pct']:.0%} "
            f"cost/ct=${chosen['cost_one']:.0f} x{contracts} conf={confidence:.2f}"
        ),
    )
