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
from bots.claude.parameters import FORCE_CLOSE_HOUR, FORCE_CLOSE_MINUTE

PROFIT_TARGET = "PROFIT_TARGET"
STOP_LOSS = "STOP_LOSS"
TIME_FORCE_CLOSE = "TIME_FORCE_CLOSE"


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None
    pnl_pct: float | None = None


def force_close_at(now: datetime) -> datetime:
    return now.replace(hour=FORCE_CLOSE_HOUR, minute=FORCE_CLOSE_MINUTE, second=0, microsecond=0)


def past_entry_cutoff(now: datetime) -> bool:
    """A brand-new 0DTE entry made at/after the force-close time has no
    real chance to develop before should_exit() force-closes it anyway -
    it just pays the bid/ask spread for a near-guaranteed small loss.
    Found live in the real backtest 2026-08-27: 20 of 21 TIME_FORCE_CLOSE
    trades had opened AFTER this exact cutoff, some over an hour past it -
    exits.py enforced the cutoff on the exit side, nothing enforced it on
    the entry side. Same cutoff, opposite direction: entries stop exactly
    where holds get force-ended, so nothing ever opens with zero runway
    left to actually move."""
    return now >= force_close_at(now)


def should_exit(
    open_trade: dict[str, Any],
    current_contract: dict[str, Any],
    now: datetime,
    params: dict[str, float],
) -> ExitDecision:
    """`open_trade` is scoreboard.current_position_status()'s shape.
    `current_contract` is a chain row for the held contract_symbol
    (backtest_lab.MarketView.options_as_of()'s per-row shape). `params`
    is the hypothesis that opened this trade's own parameter dict -
    profit_target_pct/stop_loss_pct belong to that hypothesis, not one
    global constant. The force-close time is the one exception: a shared
    safety backstop under whatever target/stop is currently active."""
    if now >= force_close_at(now):
        return ExitDecision(True, TIME_FORCE_CLOSE)

    entry_price = open_trade["entry_price"]
    exit_price = exit_fill_price(current_contract)
    pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0

    if pnl_pct >= params["profit_target_pct"]:
        return ExitDecision(True, PROFIT_TARGET, pnl_pct)
    if pnl_pct <= params["stop_loss_pct"]:
        return ExitDecision(True, STOP_LOSS, pnl_pct)
    return ExitDecision(False, None, pnl_pct)
