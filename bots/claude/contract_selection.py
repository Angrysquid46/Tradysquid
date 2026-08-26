"""AXIOM's contract selection - 0DTE long calls/puts only, per Section 4's
immutable scope ("long 0DTE CALLS and PUTS, buy to open and sell to
close" - no spreads, no shorts, no multi-leg).

Operates over the exact shape backtest_lab.MarketView.options_as_of()
returns: a list of chain rows for one point-in-time snapshot.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import market_data_store as store

from bots.claude.execution import spread_ok

_SIDE_MAP = {"CALL": "call", "PUT": "put"}


def select_contract(
    contracts: list[dict[str, Any]],
    side: str,
    today: date,
    params: dict[str, float],
    confidence: float = 0.5,
) -> dict[str, Any] | None:
    """Returns the eligible contract closest to a confidence-biased target
    delta within the configured band, or None if nothing qualifies.
    Filters, in order: 0DTE only, Tier-A data only, matching side, delta
    band, premium cap, spread sanity. `params` is the FIRING hypothesis's
    own parameter dict (bots/claude/parameters.py's HYPOTHESIS_DEFAULTS
    shape) - delta band and premium cap are no longer one global
    constant, they belong to whichever hypothesis produced the signal.

    Owner directive 2026-08-26 ("build anything with its own signals and
    aggression"): `confidence` (0.0-1.0, from the firing hypothesis's own
    EntryDecision.signals - see hypotheses.py's `_confidence`) biases the
    target delta toward delta_min (cheaper, further OTM, more leveraged)
    as conviction rises, and toward delta_max (pricier, more ITM-like,
    safer) as it falls. At confidence=0.5 this is exactly the old
    band-midpoint behavior - a neutral read isn't punished or rewarded,
    only a genuinely strong or genuinely weak signal shifts where in the
    band AXIOM buys. sizing.position_size still commits the full
    available bankroll regardless (no fractional-risk throttle), so this
    is where conviction actually expresses itself."""
    contract_side = _SIDE_MAP.get(side)
    if contract_side is None:
        return None

    today_iso = today.isoformat()
    delta_min, delta_max = params["delta_min"], params["delta_max"]
    confidence = max(0.0, min(1.0, confidence))
    target_delta = delta_max - confidence * (delta_max - delta_min)
    eligible: list[dict[str, Any]] = []

    for contract in contracts:
        if str(contract.get("expiration")) != today_iso:
            continue
        if contract.get("data_class") != store.VERIFIED_REAL:
            continue
        if str(contract.get("side", "")).lower() != contract_side:
            continue
        delta = contract.get("delta")
        if delta is None:
            continue
        abs_delta = abs(delta)
        if not (delta_min <= abs_delta <= delta_max):
            continue
        ask = contract.get("ask")
        if ask is None or ask <= 0 or ask > params["premium_cap_usd"]:
            continue
        if not spread_ok(contract):
            continue
        eligible.append(contract)

    if not eligible:
        return None

    return min(eligible, key=lambda c: abs(abs(c["delta"]) - target_delta))
