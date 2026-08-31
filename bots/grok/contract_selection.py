"""GROK contract selection — DEGEN MODE.

Prefer asymmetric SPY 0DTE tickets that still fill. Wider delta band,
looser liquidity floors, favor contracts that let sizing buy more shares
of the idea without breaking the $1k hard ceiling.
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
    p = params or {}
    max_spread = p.get("max_spread_pct", 0.35)
    min_vol = p.get("min_volume", 10)
    min_oi = p.get("min_open_interest", 25)
    delta_lo, delta_hi = p.get("preferred_delta_range", (0.12, 0.70))

    candidates = []
    for c in chain:
        otype = str(c.get("option_type", "")).upper()
        if otype not in (side, side[:1], "CALL" if side == "CALL" else "PUT"):
            if side == "CALL" and otype not in ("CALL", "C"):
                continue
            if side == "PUT" and otype not in ("PUT", "P"):
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

        cost_one = ask * 100
        if cost_one > bankroll + 0.01:
            continue

        # Degen quality: favor affordable tickets that still have some flow,
        # slight preference for mid-delta when known, but do NOT require ATM.
        quality = 0.0
        quality += max(0.0, 0.40 - spread_pct)  # tighter better
        if delta is not None:
            # sweet spot ~0.25-0.45 for leverage + still real delta
            quality += max(0.0, 0.25 - abs(delta - 0.35))
        else:
            quality += 0.05
        if vol >= 50:
            quality += 0.08
        if oi >= 100:
            quality += 0.05
        # Prefer cheaper contracts when confidence is high (more contracts)
        if confidence >= 0.55 and cost_one < 120:
            quality += 0.12
        if confidence >= 0.70 and cost_one < 60:
            quality += 0.10

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

    candidates.sort(key=lambda x: (-x["quality"], x["cost_one"]))
    best = candidates[0]

    max_contracts = int(bankroll // best["cost_one"])
    if max_contracts < 1:
        return None

    # Aggressive default size — still hard-capped by bankroll
    if confidence >= 0.75:
        frac = 0.90
    elif confidence >= 0.55:
        frac = 0.70
    else:
        frac = 0.55
    contracts = max(1, min(max_contracts, int((bankroll * frac) // best["cost_one"])))

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
        reason=(
            f"degen pick q={best['quality']:.2f} spread={best['spread_pct']:.0%} "
            f"cost/ct=${best['cost_one']:.0f} x{contracts} conf={confidence:.2f}"
        ),
    )
