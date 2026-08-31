"""GROK position sizing — DEGEN MODE.

Hard constraints (never exceed bankroll; one official trade) are absolute.
Within that box: size like you mean it. Prefer more contracts on cheap
premium when confidence is high. Bust → reset is the referee's problem.
"""

from __future__ import annotations

from typing import Any


def decide_contracts(
    ask_price: float,
    bankroll: float,
    confidence: float,
    spread_pct: float,
    params: dict[str, Any] | None = None,
) -> int:
    """Return contracts (0 = skip).

    Hard rules:
    - ask * 100 * contracts <= bankroll
    - caller enforces max 1 open trade

    Soft degen policy:
    - default: push toward a large fraction of bankroll on the idea
    - high confidence + tight-ish spread → lean heavier
    - still leave a tiny cushion so a scratch fill doesn't auto-bust math
    """
    if ask_price <= 0 or bankroll <= 0:
        return 0

    cost_one = ask_price * 100.0
    if cost_one > bankroll + 0.01:
        return 0

    max_affordable = int(bankroll // cost_one)
    if max_affordable < 1:
        return 0

    # Target risk fraction of bankroll by confidence
    if confidence >= 0.85:
        target_frac = 0.92
    elif confidence >= 0.70:
        target_frac = 0.80
    elif confidence >= 0.55:
        target_frac = 0.65
    else:
        target_frac = 0.50

    # Wide spread → slightly less size (still aggressive)
    if spread_pct > 0.25:
        target_frac *= 0.75
    elif spread_pct > 0.18:
        target_frac *= 0.90

    target_dollars = bankroll * target_frac
    contracts = max(1, int(target_dollars // cost_one))
    contracts = min(contracts, max_affordable)

    # Always try at least 1 if affordable; prefer more when cheap tickets
    if cost_one < 80 and confidence >= 0.50 and max_affordable >= 2:
        contracts = max(contracts, min(3, max_affordable))
    if cost_one < 40 and confidence >= 0.55 and max_affordable >= 4:
        contracts = max(contracts, min(5, max_affordable))
    if cost_one < 25 and confidence >= 0.60 and max_affordable >= 6:
        contracts = max(contracts, min(8, max_affordable))

    # Never exceed bankroll
    while contracts > 1 and cost_one * contracts > bankroll + 0.01:
        contracts -= 1

    return contracts if cost_one * contracts <= bankroll + 0.01 else 0
