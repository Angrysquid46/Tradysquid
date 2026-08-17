"""Phase 5 step 3 - replay strategies as 0DTE options rather than as
underlying moves.

Everything upstream measured SPY itself, in ATR. That answers "did price
go the right way", which is necessary but not sufficient: a 0DTE call can
lose money on a day the underlying moved in its favour, because theta
took more than delta gave. This module answers the actual question -
would buying the contract have made money.

Two rules keep it honest:

1. **Only sessions where a same-day expiry actually existed.** Before
   2023 most days had none (38-157 per year). Pricing a 0DTE on a day it
   was never listed would be scoring a contract nobody could buy.
2. **Every price is modelled**, from a real IV level for that day. The
   archive has no intraday option quotes at all, so this is the only
   honest way to answer the question - and the modelled flag travels into
   the report rather than being dropped once the numbers look concrete.

Exits are expressed in **option-premium percent**, which is how the live
system already defines them (`SPY_0DTE_TARGET_PCT`, the ratchet
`step_pct`/`stop_pct`). That is what finally makes the 10 ratchet
variants separable - on underlying bars they share one entry and are
indistinguishable.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import spy_option_model as om

# Live contract-selection rules, mirrored from spy_scanner so the trade
# being measured is the trade the system would actually take.
DEFAULT_TARGET_DELTA = 0.50
MAX_CONTRACT_ASK = 5.00        # SPY_0DTE_MAX_CONTRACT_ASK
MAX_RISK_PER_TRADE = 500.0     # SPY_0DTE_MAX_RISK_PER_TRADE
COMMISSION_PER_CONTRACT = 0.65  # each way; typical retail 0DTE
LAST_EXIT_MINUTE = 375         # 15:45 - the live system closes before expiry


@dataclass
class OptionExit:
    """Exit rules in option-premium percent."""
    target_pct: float | None = 50.0
    stop_pct: float | None = -50.0
    floor_trigger_pct: float | None = 30.0   # one-time floor raise (SPY_0DTE)
    floor_pct: float | None = -15.0
    step_pct: float | None = None            # ratchet: locks a floor each step
    ratchet_stop_pct: float | None = None
    name: str = "spy_0dte"


@dataclass
class OptionTrade:
    strategy: str
    session_date: str
    direction: str
    kind: str
    strike: float
    entry_minute: int
    exit_minute: int
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl_dollars: float
    peak_pct: float
    exit_reason: str
    contracts: int
    vol: float
    modelled: bool = True


def _exit_signal(pnl_pct: float, peak_pct: float, minutes_since_open: int,
                 rules: OptionExit) -> tuple[str, bool]:
    """Returns (reason, should_exit). Mirrors the live exit shapes."""
    if rules.step_pct:
        # Ratchet: once peak crosses a step, the floor locks at the
        # highest step multiple reached and only ever rises.
        if peak_pct >= rules.step_pct:
            floor = (peak_pct // rules.step_pct) * rules.step_pct
            if pnl_pct <= floor:
                return "ratchet_floor", True
        elif rules.ratchet_stop_pct is not None and pnl_pct <= rules.ratchet_stop_pct:
            return "stop", True
    else:
        stop_level = rules.stop_pct
        if (rules.floor_trigger_pct is not None and rules.floor_pct is not None
                and peak_pct >= rules.floor_trigger_pct):
            stop_level = rules.floor_pct
        if stop_level is not None and pnl_pct <= stop_level:
            return "breakeven_floor" if stop_level != rules.stop_pct else "stop", True
        if rules.target_pct is not None and pnl_pct >= rules.target_pct:
            return "target", True

    if minutes_since_open >= LAST_EXIT_MINUTE:
        return "eod_close", True
    return "", False


def simulate_option_trades(
    rows: Sequence[dict[str, Any]],
    signals: Sequence[tuple[int, str]],
    vol: float,
    rules: OptionExit,
    *,
    strategy: str,
    target_delta: float = DEFAULT_TARGET_DELTA,
) -> list[OptionTrade]:
    """One session, one strategy, one exit shape - as options.

    Same structural rules as the underlying engine: fill at the NEXT
    bar's open, one position at a time, forced flat before expiry."""
    by_index = dict(signals)
    trades: list[OptionTrade] = []
    index = 0
    total = len(rows)

    while index < total:
        direction = by_index.get(index)
        if direction is None:
            index += 1
            continue

        entry_index = index + 1
        if entry_index >= total:
            break
        entry_row = rows[entry_index]
        spot = entry_row.get("open")
        entry_minute = entry_row.get("minutes_since_open")
        if spot is None or entry_minute is None or entry_minute >= LAST_EXIT_MINUTE:
            index += 1
            continue

        kind = "call" if direction == "LONG" else "put"
        strike = om.select_strike(spot, entry_minute, vol, kind, target_delta)
        entry_quote = om.quote(spot, strike, entry_minute, vol, kind)
        entry_price = entry_quote.ask

        # Live risk gates: contract must be affordable and inside the cap.
        if entry_price <= 0.05 or entry_price > MAX_CONTRACT_ASK:
            index += 1
            continue
        contracts = max(int(MAX_RISK_PER_TRADE // (entry_price * 100)), 0)
        if contracts < 1:
            index += 1
            continue

        peak_pct = 0.0
        exit_index = entry_index
        exit_price = entry_price
        reason = "eod_close"

        for offset in range(entry_index, total):
            bar = rows[offset]
            minute = bar.get("minutes_since_open")
            close = bar.get("close")
            if minute is None or close is None:
                continue
            mark = om.quote(close, strike, minute, vol, kind).bid
            pnl_pct = (mark - entry_price) / entry_price * 100.0
            peak_pct = max(peak_pct, pnl_pct)

            reason_now, should_exit = _exit_signal(pnl_pct, peak_pct, minute, rules)
            if should_exit:
                exit_index, exit_price, reason = offset, mark, reason_now
                break
        else:
            last = rows[-1]
            exit_index = total - 1
            exit_price = om.quote(last["close"], strike,
                                  last.get("minutes_since_open") or LAST_EXIT_MINUTE,
                                  vol, kind).bid

        gross = (exit_price - entry_price) * 100.0 * contracts
        commission = COMMISSION_PER_CONTRACT * contracts * 2
        net = gross - commission
        trades.append(OptionTrade(
            strategy=strategy, session_date=entry_row["session_date"], direction=direction,
            kind=kind, strike=strike, entry_minute=entry_minute,
            exit_minute=rows[exit_index].get("minutes_since_open") or 0,
            entry_price=entry_price, exit_price=exit_price,
            pnl_pct=(exit_price - entry_price) / entry_price * 100.0,
            pnl_dollars=net, peak_pct=peak_pct, exit_reason=reason,
            contracts=contracts, vol=vol,
        ))
        index = exit_index + 1

    return trades


def summarize_options(trades: Sequence[OptionTrade]) -> dict[str, Any]:
    """Option P/L stats. Reported in percent AND dollars, because a 0DTE
    strategy can show a respectable average percent while losing money
    once position size and commission are real."""
    if not trades:
        return {"trades": 0}

    pct = [t.pnl_pct for t in trades]
    dollars = [t.pnl_dollars for t in trades]
    wins = [p for p in pct if p > 0]
    gross_win = sum(d for d in dollars if d > 0)
    gross_loss = -sum(d for d in dollars if d <= 0)

    stdev = statistics.stdev(pct) if len(pct) > 1 else 0.0
    stderr = stdev / (len(pct) ** 0.5) if stdev > 1e-9 else 0.0

    return {
        "trades": len(trades),
        "win_rate": 100.0 * len(wins) / len(trades),
        "expectancy_pct": statistics.fmean(pct),
        "total_dollars": sum(dollars),
        "avg_dollars": statistics.fmean(dollars),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "t_stat": (statistics.fmean(pct) / stderr) if stderr > 0 else 0.0,
        "significant_95": stderr > 0 and abs(statistics.fmean(pct) / stderr) >= 1.96,
        "pct_eod_exits": 100.0 * sum(1 for t in trades if t.exit_reason == "eod_close") / len(trades),
        "avg_hold_minutes": statistics.fmean([t.exit_minute - t.entry_minute for t in trades]),
        "modelled": True,
    }


def ratchet_rules(step_pct: float, stop_pct: float) -> OptionExit:
    """One of the 10 live SPY_RATCHET_* exit shapes."""
    return OptionExit(
        target_pct=None, stop_pct=None, floor_trigger_pct=None, floor_pct=None,
        step_pct=step_pct, ratchet_stop_pct=stop_pct,
        name=f"ratchet_{step_pct:.0f}_{abs(stop_pct):.0f}",
    )


def live_exit_shapes() -> list[OptionExit]:
    """Every exit shape the live system actually runs, so they can be
    compared head to head - which underlying bars could never do."""
    import spy_scanner as ss
    shapes = [OptionExit(
        target_pct=ss.SPY_0DTE_TARGET_PCT * 100,
        stop_pct=-ss.SPY_0DTE_STOP_PCT * 100,
        floor_trigger_pct=ss.SPY_0DTE_FLOOR_TRIGGER_PCT,
        floor_pct=ss.SPY_0DTE_FLOOR_PCT,
        name="spy_0dte (+50/-50, floor +30->-15)",
    )]
    for variant in ss.SPY_RATCHET_VARIANTS:
        shapes.append(ratchet_rules(variant["step_pct"], variant["stop_pct"]))
    return shapes
