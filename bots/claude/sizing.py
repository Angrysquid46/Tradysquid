"""Phase 13: AXIOM's position sizing.

Per the owner's direct instruction: "it's got a cap of 1k what's so hard
to understand" - the $1,000 bankroll cap (Section 4) combined with
max_open_trades_per_bot=1 already bounds AXIOM's exposure. There is no
separate fractional-risk-per-trade policy: AXIOM sizes each trade using
whatever of the current bankroll is available, bounded only by the
per-contract premium ceiling that already filters contract selection.
"""

from __future__ import annotations

def position_size(available_bankroll: float, ask: float, params: dict[str, float]) -> int:
    """Number of contracts affordable at `ask`, using the full available
    bankroll, still bounded by the firing hypothesis's own premium_cap_usd
    (enforced upstream in contract_selection.select_contract, re-checked
    here defensively)."""
    if ask <= 0 or ask > params["premium_cap_usd"] or available_bankroll <= 0:
        return 0
    cost_per_contract = ask * 100
    return int(available_bankroll // cost_per_contract)
