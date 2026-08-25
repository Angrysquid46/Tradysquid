"""Phase 13: AXIOM's fill / execution-assumption model.

No shared execution simulator exists anywhere in this repo (confirmed
absent by direct search before writing this) despite Section 3 listing
"execution simulator" as an approved shared resource - it simply hasn't
been built yet. This module is AXIOM's own, used identically by both
backtest_runner.py and the live runtime so they can never silently
diverge on what a "realistic paper fill" means.

Matches Section 4's execution rule verbatim: "realistic paper execution
only - no hindsight fills, fake liquidity, or future-aware pricing."
"""

from __future__ import annotations

from typing import Any

from bots.claude.parameters import Parameters


def entry_fill_price(contract: dict[str, Any]) -> float:
    """Buy-to-open never fills better than the real captured ask."""
    return float(contract["ask"])


def exit_fill_price(contract: dict[str, Any]) -> float:
    """Sell-to-close never fills better than the real captured bid."""
    return float(contract["bid"])


def spread_ok(contract: dict[str, Any], parameters: Parameters) -> bool:
    """Liquidity/data-quality sanity bound, not an edge parameter."""
    bid = contract.get("bid")
    ask = contract.get("ask")
    if bid is None or ask is None or bid <= 0 or ask <= bid:
        return False
    mid = (bid + ask) / 2
    if mid <= 0:
        return False
    return (ask - bid) / mid <= parameters.max_spread_pct


def build_execution_assumptions(parameters: Parameters) -> dict[str, Any]:
    """The exact dict passed to backtest_lab.record_backtest(
    execution_assumptions=...) - an honest, inspectable disclosure of the
    fill rule used, not a black box."""
    return {
        "entry_fill": "real captured ask (VERIFIED_REAL only)",
        "exit_fill": "real captured bid (VERIFIED_REAL only)",
        "mid_price_fills": False,
        "hindsight_fills": False,
        "fake_liquidity": False,
        "max_spread_pct": parameters.max_spread_pct,
        "rejects_on": "bid<=0, ask<=bid, spread>max_spread_pct, or non-VERIFIED_REAL data_class",
    }
