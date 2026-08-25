"""Phase 13: AXIOM's contract selection - 0DTE long calls/puts only, per
Section 4's immutable scope ("long 0DTE CALLS and PUTS, buy to open and
sell to close" - no spreads, no shorts, no multi-leg).

Operates over the exact shape backtest_lab.MarketView.options_as_of()
returns: a list of chain rows for one point-in-time snapshot.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import market_data_store as store

from bots.claude.execution import spread_ok
from bots.claude.parameters import Parameters

_SIDE_MAP = {"CALL": "call", "PUT": "put"}


def select_contract(
    contracts: list[dict[str, Any]],
    side: str,
    today: date,
    parameters: Parameters,
) -> dict[str, Any] | None:
    """Returns the eligible contract whose delta is closest to the middle
    of the configured band, or None if nothing qualifies. Filters, in
    order: 0DTE only, Tier-A data only, matching side, delta band,
    premium cap, spread sanity."""
    contract_side = _SIDE_MAP.get(side)
    if contract_side is None:
        return None

    today_iso = today.isoformat()
    band_mid = (parameters.delta_min + parameters.delta_max) / 2
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
        if not (parameters.delta_min <= abs_delta <= parameters.delta_max):
            continue
        ask = contract.get("ask")
        if ask is None or ask <= 0 or ask > parameters.premium_cap_usd:
            continue
        if not spread_ok(contract, parameters):
            continue
        eligible.append(contract)

    if not eligible:
        return None

    return min(eligible, key=lambda c: abs(abs(c["delta"]) - band_mid))
