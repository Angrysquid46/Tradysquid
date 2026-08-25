"""Phase 13: AXIOM's tunable parameters - the only place a bare threshold
is allowed to live. Every other module in this package reads a named
field from here, never a literal.

Per the owner's direct instruction (2026-08-25): AXIOM is not gated behind
a data-measurement threshold before it can trade - only ~2 trading days of
real captured SPY data exist right now, nowhere near enough to statistically
derive entry/exit thresholds, and waiting on that was the wrong call. These
values are AXIOM's initial working defaults: reasoned from options/market
structure, not copied from the old purged system (spy_scanner.py's
0.40-0.60 delta / $500 cap / +50%/-50% exit would violate the master
spec's clean-slate objective - "no old strategy result becomes starting
knowledge"), and not backtest-measured yet either. bots/claude/backtest_runner.py
keeps re-evaluating them against the growing real dataset and can propose
refinements later; nothing here is final.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Parameters:
    # --- signal.py: entry regime/confirmation thresholds ---
    opening_range_minutes: int = 30
    # Bottom-third ATR-percentile regime - the "coiled spring" precondition.
    # Reasoned, not measured: a compressed range preceding a real breakout
    # is a structurally different bet than trading every range crossing.
    compression_atr_percentile_max: float = 35.0
    # 20% above the trailing 20-bar average - a modest, not extreme,
    # participation bar for treating a breakout as real.
    relative_volume_min: float = 1.2

    # --- contract_selection.py ---
    delta_min: float = 0.35
    delta_max: float = 0.55
    # Leaves buffer under the $1,000 bankroll cap rather than spending it
    # entirely on one contract's spread risk.
    premium_cap_usd: float = 450.0

    # --- execution.py ---
    # Liquidity/data-quality sanity bound, not an edge parameter.
    max_spread_pct: float = 0.15

    # --- exits.py ---
    # Deliberately not +50/-50 - docs/STRATEGY_RULES.md documents that
    # exact default as a repeated mistake pattern in this codebase.
    # Asymmetric to account for 0DTE's fast theta decay working against a
    # held loser.
    profit_target_pct: float = 0.40
    stop_loss_pct: float = -0.35
    # 0DTE settles same day, but late-day quotes thin out - an operational
    # safety margin, not an edge parameter. 15 minutes before
    # market_data.MARKET_CLOSE (15:00 Central) - times here are Central,
    # matching market_data.MARKET_TZ, the convention this whole repo uses.
    force_close_hour: int = 14
    force_close_minute: int = 45


DEFAULT_PARAMETERS = Parameters()
