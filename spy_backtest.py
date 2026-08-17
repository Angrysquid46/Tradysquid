"""Phase 3 - event-driven 1-minute backtest engine (underlying only).

The spec is explicit that the SPY entry should be optimised BEFORE
contract selection, and that the underlying backtest and the option
backtest must never be conflated. So everything here is measured in SPY
points and ATR multiples. There is no option P/L in this module, and the
+25%/+50%/+100% profit targets from the spec are option percentages that
belong to Phase 5 - applying them to the underlying would be a category
error that silently reports a different strategy than the one specified.

Three realism rules matter more than anything else here, because each one
inflates results when skipped:

1. **Signals are evaluated on a closed bar and filled at the NEXT bar's
   open.** You cannot trade the close you are still watching form.
2. **When a stop and a target both sit inside one bar, the stop wins.**
   One-minute OHLC cannot say which came first, and assuming the target
   is the single most common way a backtest invents profit that never
   existed.
3. **Positions are forced flat at the close.** These are 0DTE ideas;
   carrying one overnight is not a real option.

Signal generation is separated from exit simulation so a variant's
entries are computed once and then replayed against many exit policies.
That is what makes a full parameter sweep affordable.
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, Iterator, Sequence

import spy_intraday_features as sif

# ---------------------------------------------------------------------------
# Eras - walk-forward buckets. Never fit or judge on one blended sample.
# ---------------------------------------------------------------------------

ERAS: tuple[tuple[str, str, str], ...] = (
    ("2008-2011 crisis+recovery", "2008-01-01", "2011-12-31"),
    ("2012-2015 low-vol bull", "2012-01-01", "2015-12-31"),
    ("2016-2019 late bull", "2016-01-01", "2019-12-31"),
    ("2020-2021 covid era", "2020-01-01", "2021-12-31"),
)

SESSION_LAST_MINUTE = 389          # 15:59, the final regular-session bar


def era_for(session_date: str) -> str:
    for name, start, end in ERAS:
        if start <= session_date <= end:
            return name
    return "unclassified"


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    strategy: str
    variant: str
    direction: str                  # LONG or SHORT (call-side / put-side)
    session_date: str
    entry_time: str
    entry_price: float
    entry_minute: int
    entry_bucket: str
    exit_time: str
    exit_price: float
    exit_reason: str
    bars_held: int
    atr: float
    pnl_points: float
    pnl_atr: float
    pnl_pct: float
    mfe_atr: float                  # max favourable excursion
    mae_atr: float                  # max adverse excursion
    regime: str
    day_type: str
    alignment: str
    gap_pct: float | None
    era: str


@dataclass
class ExitPolicy:
    """Underlying exit rules, all in ATR multiples so they are comparable
    across the 2008 $90 SPY and the 2021 $420 SPY."""
    target_atr: float | None = 1.0
    stop_atr: float | None = 0.75
    time_stop_minutes: int | None = 30
    breakeven_after_atr: float | None = None
    name: str = ""

    def label(self) -> str:
        if self.name:
            return self.name
        parts = [
            f"t{self.target_atr}" if self.target_atr else "t-",
            f"s{self.stop_atr}" if self.stop_atr else "s-",
            f"m{self.time_stop_minutes}" if self.time_stop_minutes else "m-",
        ]
        if self.breakeven_after_atr:
            parts.append(f"be{self.breakeven_after_atr}")
        return "/".join(parts)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _resolve_bar_exit(
    row: dict[str, Any], direction: str, stop: float | None, target: float | None
) -> tuple[float, str] | None:
    """Which exit, if any, this bar triggers - resolved pessimistically.

    A one-minute bar records only open/high/low/close, so when price
    visited both the stop and the target inside that minute there is no
    way to know the order. Assuming the favourable one is the classic way
    a backtest manufactures edge, so the stop is always taken."""
    high, low = row["high"], row["low"]
    if high is None or low is None:
        return None

    if direction == "LONG":
        hit_stop = stop is not None and low <= stop
        hit_target = target is not None and high >= target
    else:
        hit_stop = stop is not None and high >= stop
        hit_target = target is not None and low <= target

    if hit_stop:
        return (stop, "stop_and_target_same_bar" if hit_target else "stop")
    if hit_target:
        return (target, "target")
    return None


def simulate(
    rows: Sequence[dict[str, Any]],
    signals: Sequence[tuple[int, str]],
    policy: ExitPolicy,
    *,
    strategy: str,
    variant: str,
) -> list[Trade]:
    """Replay one session's signals under one exit policy.

    Only one position is open at a time - matching how the live system
    trades - so a signal arriving while a trade is running is skipped
    rather than stacked."""
    by_index = dict(signals)
    trades: list[Trade] = []
    index = 0
    total = len(rows)

    while index < total:
        direction = by_index.get(index)
        if direction is None:
            index += 1
            continue

        # Fill at the NEXT bar's open; the signal bar's close is only
        # observable at the instant it completes.
        entry_index = index + 1
        if entry_index >= total:
            break
        entry_row = rows[entry_index]
        entry_price = entry_row["open"]
        atr = rows[index].get("atr_14")
        if entry_price is None or not atr:
            index += 1
            continue

        stop = target = None
        if policy.stop_atr:
            stop = entry_price - policy.stop_atr * atr if direction == "LONG" else entry_price + policy.stop_atr * atr
        if policy.target_atr:
            target = entry_price + policy.target_atr * atr if direction == "LONG" else entry_price - policy.target_atr * atr

        mfe = mae = 0.0
        exit_price: float | None = None
        exit_reason = ""
        exit_index = entry_index

        for offset in range(entry_index, total):
            bar = rows[offset]
            high, low, close = bar["high"], bar["low"], bar["close"]
            if high is None or low is None:
                continue

            favourable = (high - entry_price) if direction == "LONG" else (entry_price - low)
            adverse = (entry_price - low) if direction == "LONG" else (high - entry_price)
            mfe = max(mfe, favourable)
            mae = max(mae, adverse)

            hit = _resolve_bar_exit(bar, direction, stop, target)
            if hit:
                exit_price, exit_reason = hit
                exit_index = offset
                break

            # Breakeven trail, armed once the trade has run far enough.
            if policy.breakeven_after_atr and favourable >= policy.breakeven_after_atr * atr:
                stop = entry_price

            held = offset - entry_index + 1
            if policy.time_stop_minutes and held >= policy.time_stop_minutes:
                exit_price, exit_reason, exit_index = close, "time_stop", offset
                break
            if bar["minutes_since_open"] is not None and bar["minutes_since_open"] >= SESSION_LAST_MINUTE:
                exit_price, exit_reason, exit_index = close, "session_close", offset
                break
        else:
            last = rows[-1]
            exit_price, exit_reason, exit_index = last["close"], "session_close", total - 1

        if exit_price is None:
            index = entry_index + 1
            continue

        pnl = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
        signal_row = rows[index]
        trades.append(Trade(
            strategy=strategy, variant=variant, direction=direction,
            session_date=entry_row["session_date"],
            entry_time=entry_row["bar_time"], entry_price=entry_price,
            entry_minute=entry_row["minutes_since_open"] or 0,
            entry_bucket=entry_row.get("time_bucket") or "UNKNOWN",
            exit_time=rows[exit_index]["bar_time"], exit_price=exit_price,
            exit_reason=exit_reason, bars_held=exit_index - entry_index + 1,
            atr=atr, pnl_points=pnl, pnl_atr=pnl / atr,
            pnl_pct=100.0 * pnl / entry_price,
            mfe_atr=mfe / atr, mae_atr=mae / atr,
            regime=signal_row.get("regime") or "UNKNOWN",
            day_type=signal_row.get("day_type") or "UNKNOWN",
            alignment=signal_row.get("alignment") or "UNKNOWN",
            gap_pct=signal_row.get("gap_pct"),
            era=era_for(entry_row["session_date"]),
        ))
        index = exit_index + 1          # no overlapping positions

    return trades


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _max_drawdown(values: Sequence[float]) -> float:
    peak = running = 0.0
    worst = 0.0
    for value in values:
        running += value
        peak = max(peak, running)
        worst = min(worst, running - peak)
    return worst


def _streaks(wins: Sequence[bool]) -> tuple[int, int]:
    best = worst = current_w = current_l = 0
    for win in wins:
        if win:
            current_w += 1
            current_l = 0
        else:
            current_l += 1
            current_w = 0
        best = max(best, current_w)
        worst = max(worst, current_l)
    return best, worst


def summarize(trades: Sequence[Trade]) -> dict[str, Any]:
    """Expectancy and friends, all in ATR units.

    Expectancy is the number that matters: win rate alone says nothing
    about whether the wins are bigger than the losses."""
    if not trades:
        return {"trades": 0}

    pnl = [t.pnl_atr for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    expectancy = statistics.fmean(pnl)

    # Is the expectancy distinguishable from zero at all? Per-trade P/L
    # scatters roughly +-1 ATR, so a +0.02 mean over a few hundred trades
    # is well inside the noise. Without this, a tiny positive number
    # reads as a finding when it is a coin flip.
    stdev = statistics.stdev(pnl) if len(pnl) > 1 else 0.0
    # Near-zero variance means every trade in the group had effectively
    # identical P/L - true of any group sliced BY its exit, since every
    # stop loses exactly the stop distance. The residual spread is then
    # float noise around 1e-16, and dividing by it produced t-statistics
    # like 2.3e15. There is no meaningful t-test on a constant.
    degenerate = stdev < 1e-9
    stderr = 0.0 if degenerate else stdev / math.sqrt(len(pnl))
    t_stat = (expectancy / stderr) if stderr > 0 else 0.0

    return {
        "trades": len(trades),
        "win_rate": 100.0 * len(wins) / len(trades),
        "expectancy_atr": expectancy,
        "stdev_atr": stdev,
        "stderr_atr": stderr,
        "t_stat": t_stat,
        "significant_95": (not degenerate) and abs(t_stat) >= 1.96,
        "total_atr": sum(pnl),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else math.inf,
        "avg_win_atr": statistics.fmean(wins) if wins else 0.0,
        "avg_loss_atr": statistics.fmean(losses) if losses else 0.0,
        "max_drawdown_atr": _max_drawdown(pnl),
        "avg_mfe_atr": statistics.fmean([t.mfe_atr for t in trades]),
        "avg_mae_atr": statistics.fmean([t.mae_atr for t in trades]),
        "avg_bars_held": statistics.fmean([t.bars_held for t in trades]),
        "longest_win_streak": _streaks([p > 0 for p in pnl])[0],
        "longest_loss_streak": _streaks([p > 0 for p in pnl])[1],
        "pct_long": 100.0 * sum(1 for t in trades if t.direction == "LONG") / len(trades),
    }


def breakdown(trades: Sequence[Trade], key: Callable[[Trade], str]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped[key(trade)].append(trade)
    return {name: summarize(group) for name, group in sorted(grouped.items())}


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

# Only what the strategies and trade records actually read. `SELECT *`
# pulls all 69 columns and roughly doubles the cost of the scan.
BACKTEST_COLUMNS: tuple[str, ...] = (
    "bar_time", "session_date", "minutes_since_open", "time_bucket",
    "open", "high", "low", "close", "volume",
    "vwap", "vwap_slope", "above_vwap", "vwap_crosses", "vwap_distance_atr",
    "atr_14", "relative_volume", "gap_pct",
    "or5_high", "or5_low", "or5_state", "or5_break_minute",
    "or15_high", "or15_low", "or15_state", "or15_break_minute",
    "or30_high", "or30_low", "or30_state", "or30_break_minute",
    "regime", "day_type", "alignment",
)


def load_sessions(
    conn: sqlite3.Connection, ticker: str = "SPY", *, limit: int | None = None
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yield one session of feature rows at a time.

    Reads the whole table as ONE sequential scan of the (ticker,
    bar_time) primary key and splits it into sessions while streaming,
    rather than issuing a query per session. Per-session queries meant
    3,347 index seeks scattered across a 1.1 GB table - about 1.08s each,
    an hour of pure I/O before any strategy logic ran. A single ordered
    scan reads the same data in the order it is physically stored.

    Still streamed, so memory holds one session at a time."""
    columns = ", ".join(BACKTEST_COLUMNS)
    cursor = conn.execute(
        f"SELECT {columns} FROM minute_features WHERE ticker=? ORDER BY bar_time", (ticker,)
    )
    current: str | None = None
    batch: list[dict[str, Any]] = []
    yielded = 0

    for row in cursor:
        record = dict(row)
        session = record["session_date"]
        if session != current:
            if batch:
                yield current, batch
                yielded += 1
                if limit and yielded >= limit:
                    return
            current, batch = session, []
        batch.append(record)

    if batch and (not limit or yielded < limit):
        yield current, batch


def connect() -> sqlite3.Connection:
    return sif.connect()
