"""Parameterized clone of spy_scanner.spy_0dte_exit_signal for the backtest.

The live function reads its stop/target/floor levels off module-level
constants (SPY_0DTE_STOP_PCT etc.) sourced from config/scanner.json - fine
for live trading where there's one active setting, but the backtest wants
to replay the SAME real historical price path under many different
stop/target/floor combinations to generate volume from a limited number of
real trading days (same technique already proven on the ratchet-floor
backtest: 1,680 parameter combos over one real dataset). Rather than adding
a parameter-override path to the live exit function - which would touch
code that already governs real trades - this is a standalone copy with the
levels passed in explicitly. The exit LOGIC is identical to the live
version; only where the numbers come from differs.
"""

from __future__ import annotations


def backtest_exit_signal(
    entry_price: float,
    mark: float,
    minutes_remaining: float,
    peak_pct: float,
    stop_pct: float,
    target_pct: float,
    floor_pct: float,
    floor_trigger_pct: float,
) -> tuple[str, str]:
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    pnl_pct = (mark - entry_price) / entry_price * 100
    stop_floor = floor_pct if peak_pct >= floor_trigger_pct else -stop_pct * 100
    if pnl_pct <= stop_floor:
        if stop_floor > -stop_pct * 100:
            return "BREAKEVEN STOP", (
                f"peaked at {peak_pct:.0f}%, down to {pnl_pct:.0f}% - protecting the proven "
                f"move instead of risking a full round-trip to the {stop_pct * 100:.0f}% stop"
            )
        return "STOP OUT", f"down {pnl_pct:.0f}%, past the {stop_pct * 100:.0f}% 0DTE stop"
    if pnl_pct >= target_pct * 100:
        return "TAKE PROFIT", f"up {pnl_pct:.0f}%, past the {target_pct * 100:.0f}% 0DTE target"
    if minutes_remaining <= 15:
        return "EOD CLOSE", "closing ahead of same-day expiration - 0DTE never holds overnight"
    return "HOLD", "no exit condition met"
