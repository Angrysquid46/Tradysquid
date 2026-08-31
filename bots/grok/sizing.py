"""GROK position sizing — private model within competition constraints.

Never exceeds bankroll. Never opens a second official trade.
Scales mildly with confidence and opportunity quality.
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
    """Return number of contracts (0 means unaffordable / skip).

    Constraints:
    - cost = ask * 100 * contracts <= bankroll
    - max 1 official trade (caller enforces)
    - prefer 1 contract; allow 2 only under high confidence + ample room
    """
    if ask_price <= 0 or bankroll <= 0:
        return 0

    cost_one = ask_price * 100.0
    if cost_one > bankroll + 0.01:
        return 0

    max_affordable = int(bankroll // cost_one)
    if max_affordable < 1:
        return 0

    # Default conservative
    contracts = 1

    # Mild scale-up only when very confident and spread is tight
    if confidence >= 0.78 and spread_pct <= 0.10 and max_affordable >= 2:
        contracts = 2
    if confidence >= 0.88 and spread_pct <= 0.08 and max_affordable >= 3:
        contracts = min(3, max_affordable)

    # Never risk more than ~40% of current bankroll on one trade
    while contracts > 1 and (cost_one * contracts) > bankroll * 0.40:
        contracts -= 1

    return max(1, contracts) if cost_one <= bankroll else 0
