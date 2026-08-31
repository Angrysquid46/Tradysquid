"""GROK contract selection — explicit intelligence layer.

Chooses the specific 0DTE option given direction, bankroll, and chain quality.
Optimizes liquidity, spread, delta, and affordability independently.
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


def select_contract(
    side: str,
    chain: list[dict[str, Any]],
    bankroll: float,
    confidence: float,
    params: dict[str, Any] | None = None,
) -> SelectedContract | None:
    """Pick the best affordable contract for the chosen side.

    Rules:
    - Must be same-day expiration (caller filters to 0DTE).
    - Prefer liquid, reasonable-spread, mid-delta contracts.
    - Never spend more than bankroll allows.
    - Size scales mildly with confidence (still one trade max).
    """
    p = params or {}
    max_spread = p.get("max_spread_pct", 0.18)
    min_vol = p.get("min_volume", 50)
    min_oi = p.get("min_open_interest", 100)
    delta_lo, delta_hi = p.get("preferred_delta_range", (0.25, 0.55))

    candidates = []
    for c in chain:
        if str(c.get("option_type", "")).upper() not in (side, side[0]):  # CALL/PUT or C/P
            continue
        bid = float(c.get("bid") or 0)
        ask = float(c.get("ask") or 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid > 0 else 999
        if spread_pct > max_spread:
            continue
        vol = int(c.get("volume") or 0)
        oi = int(c.get("open_interest") or 0)
        if vol < min_vol and oi < min_oi:
            continue
        delta = c.get("delta")
        if delta is not None:
            delta = abs(float(delta))
            if not (delta_lo <= delta <= delta_hi):
                continue
        else:
            delta = None

        # Affordability — at least 1 contract
        cost_one = ask * 100
        if cost_one > bankroll + 0.01:
            continue

        # Simple quality score
        quality = 1.0 - spread_pct
        if delta is not None:
            quality += 0.15  # prefer known Greeks
        if vol > 200:
            quality += 0.1
        if oi > 500:
            quality += 0.05

        candidates.append({
            "raw": c,
            "bid": bid,
            "ask": ask,
            "spread_pct": spread_pct,
            "delta": delta,
            "volume": vol,
            "open_interest": oi,
            "quality": quality,
            "cost_one": cost_one,
        })

    if not candidates:
        return None

    # Best quality first, then cheaper
    candidates.sort(key=lambda x: (-x["quality"], x["cost_one"]))
    best = candidates[0]

    # Sizing: 1 contract by default; mild scale with high confidence if affordable
    max_contracts = int(bankroll // best["cost_one"])
    if max_contracts < 1:
        return None
    contracts = 1
    if confidence >= 0.75 and max_contracts >= 2:
        contracts = min(2, max_contracts)

    cost = best["cost_one"] * contracts
    symbol = str(best["raw"].get("symbol") or best["raw"].get("option_symbol") or "")
    strike = float(best["raw"].get("strike") or 0)

    return SelectedContract(
        symbol=symbol,
        side=side,
        strike=strike,
        bid=best["bid"],
        ask=best["ask"],
        delta=best["delta"],
        volume=best["volume"],
        open_interest=best["open_interest"],
        spread_pct=best["spread_pct"],
        contracts=contracts,
        cost=cost,
        reason=f"best quality {best['quality']:.2f}, spread {best['spread_pct']:.1%}, conf {confidence:.2f}",
    )
