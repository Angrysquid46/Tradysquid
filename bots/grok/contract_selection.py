"""GROK contract selection — DEGEN MODE.

Strict filters first. If they wipe the book, fall back to any affordable
same-side contract with a real bid/ask so ENTER does not die at selection.
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
    return o == side.upper()


def _pick(
    candidates: list[dict[str, Any]],
    *,
    side: str,
    bankroll: float,
    confidence: float,
    reason_prefix: str,
) -> SelectedContract | None:
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x["quality"], x["cost_one"]))
    best = candidates[0]
    max_contracts = int(bankroll // best["cost_one"])
    if max_contracts < 1:
        return None
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
            f"{reason_prefix} q={best['quality']:.2f} spread={best['spread_pct']:.0%} "
            f"cost/ct=${best['cost_one']:.0f} x{contracts} conf={confidence:.2f}"
        ),
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

    strict: list[dict[str, Any]] = []
    loose: list[dict[str, Any]] = []

    for c in chain:
        otype = str(c.get("option_type", "") or "").upper()
        if not _side_match(otype, side):
            continue
        bid = float(c.get("bid") or 0)
        ask = float(c.get("ask") or 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid > 0 else 999.0
        vol = int(c.get("volume") or 0)
        oi = int(c.get("open_interest") or 0)
        delta_raw = c.get("delta")
        delta = abs(float(delta_raw)) if delta_raw is not None else None
        cost_one = ask * 100.0
        if cost_one > bankroll + 0.01:
            continue

        quality = max(0.0, 0.40 - spread_pct)
        if delta is not None:
            quality += max(0.0, 0.25 - abs(delta - 0.35))
        else:
            quality += 0.05
        if vol >= 50:
            quality += 0.08
        if oi >= 100:
            quality += 0.05
        if confidence >= 0.55 and cost_one < 120:
            quality += 0.12
        if confidence >= 0.70 and cost_one < 60:
            quality += 0.10

        row = {
            "raw": c,
            "bid": bid,
            "ask": ask,
            "spread_pct": spread_pct,
            "delta": delta,
            "volume": vol,
            "open_interest": oi,
            "quality": quality,
            "cost_one": cost_one,
        }

        # Always keep a loose candidate if it has a real market
        loose.append(row)

        if spread_pct > max_spread:
            continue
        if vol < min_vol and oi < min_oi and (min_vol > 0 or min_oi > 0):
            continue
        if delta is not None and not (delta_lo <= delta <= delta_hi):
            continue
        strict.append(row)

    picked = _pick(strict, side=side, bankroll=bankroll, confidence=confidence, reason_prefix="strict")
    if picked is not None:
        return picked
    return _pick(loose, side=side, bankroll=bankroll, confidence=confidence, reason_prefix="fallback")
