"""Phase 13: AXIOM's exit logic - profit target, stop loss, and a firm
time-based force-close before the market close (0DTE settles same day,
but late-day quotes thin out, an operational safety margin distinct from
the two edge-thresholds above it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bots.claude.execution import exit_fill_price
from bots.claude.parameters import Parameters

PROFIT_TARGET = "PROFIT_TARGET"
STOP_LOSS = "STOP_LOSS"
TIME_FORCE_CLOSE = "TIME_FORCE_CLOSE"


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None
    pnl_pct: float | None = None


def should_exit(
    open_trade: dict[str, Any],
    current_contract: dict[str, Any],
    now: datetime,
    parameters: Parameters,
) -> ExitDecision:
    """`open_trade` is scoreboard.current_position_status()'s shape.
    `current_contract` is a chain row for the held contract_symbol
    (backtest_lab.MarketView.options_as_of()'s per-row shape)."""
    force_close_at = now.replace(
        hour=parameters.force_close_hour,
        minute=parameters.force_close_minute,
        second=0,
        microsecond=0,
    )
    if now >= force_close_at:
        return ExitDecision(True, TIME_FORCE_CLOSE)

    entry_price = open_trade["entry_price"]
    exit_price = exit_fill_price(current_contract)
    pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0

    if pnl_pct >= parameters.profit_target_pct:
        return ExitDecision(True, PROFIT_TARGET, pnl_pct)
    if pnl_pct <= parameters.stop_loss_pct:
        return ExitDecision(True, STOP_LOSS, pnl_pct)
    return ExitDecision(False, None, pnl_pct)
