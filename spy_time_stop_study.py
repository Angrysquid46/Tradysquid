"""What is each strategy's entry worth on a pure clock?

Owner's question: take every signal all 15 strategies fire, ignore what
each one does about exits, and just hold for a fixed number of minutes -
5, 10, 15, 20, 25, 30 - then close at market. What does the P/L look like?

That isolates the ENTRY. Every strategy currently mixes two separate
claims: "this is a good moment to be long/short" and "these are the right
target and stop". Measuring them under one clock removes the second claim
entirely, so what is left is the first one.

## What is deliberately switched off

No profit target, no stop, no breakeven floor, no ratchet, no stagnation
bail, and for SPY_KEY_LEVELS no underlying stop or R-target either. The
ONLY things that can close a trade are the horizon and the 15:45 flatten
(`LAST_EXIT_MINUTE`), which is not optional - a 0DTE held past the bell is
not a trade anyone can make.

## Two things that will look like bugs and are not

1. **Trade counts differ across horizons.** One position at a time is a
   live rule, so a 5-minute clock frees the strategy to take the next
   signal while a 30-minute clock is still holding the first. Shorter
   horizons therefore take strictly more trades. Covered by
   `test_a_shorter_clock_frees_the_strategy_to_trade_again`.
2. **SPY_KEY_LEVELS is not comparable to its own baseline.** It exits on
   the UNDERLYING live (stop at the level, target at 2R), so it has no
   premium-percent exit to be measured against. It is scored on option
   premium here like the other 14, and flagged in the output rather than
   quietly ranked alongside them.

Entries come from `spy_live_new_strategies.NEW_STRATEGY_SPECS` - the same
callables the live scanner uses, at their live thresholds. That matters:
the older `spy_option_report.SHORTLIST` still names `1.0atr ext` and
`0.5atr drive` for two strategies that were recalibrated to 0.40 and 0.22,
so anything driven off SHORTLIST measures thresholds this system stopped
using.

One pass over the archive, all six horizons scored per signal, because
each horizon on its own walk would be six times ~40 minutes.

Run:  ./.venv-tradysquid/Scripts/python.exe spy_time_stop_study.py
"""

from __future__ import annotations

import io
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

import spy_backtest as bt
import spy_backtest_report as rep
import spy_live_new_strategies as lns
import spy_option_backtest as ob
import spy_option_data as od
import spy_option_model as om

HORIZONS = (5, 10, 15, 20, 25, 30)
OUT_JSON = Path("state/time_stop_study.json")
OUT_DOC = Path("docs/TIME_STOP_STUDY.md")

# Measured on option premium like the other 14, but it does not exit that
# way live - see the module docstring.
UNDERLYING_EXIT_STRATEGY = "SPY_KEY_LEVELS"


def clock_only(minutes: int) -> ob.OptionExit:
    """Hold for `minutes`, then close at market. Nothing else can fire."""
    return ob.OptionExit(
        target_pct=None, stop_pct=None,
        floor_trigger_pct=None, floor_pct=None,
        ratchet_stop_pct=None, step_pct=None,
        stagnation_pct=None, stagnation_minutes=None,
        underlying_stop_pct=None, underlying_r_multiple=None,
        time_stop_minutes=minutes,
        name=f"{minutes}m clock",
    )


def build_roster(conn) -> list[tuple[str, object]]:
    """(play_type, signal_fn) for all 15, from the live registry."""
    roster = [(spec["play_type"], spec["signal"]) for spec in lns.NEW_STRATEGY_SPECS]
    variants = rep.all_variants(conn=conn)
    key_levels = variants.get("LIVE SPY_KEY_LEVELS", {}).get("deployed rules")
    if key_levels is None:
        raise RuntimeError("SPY_KEY_LEVELS adapter missing - roster would be 14")
    roster.append((UNDERLYING_EXIT_STRATEGY, key_levels))
    return roster


def run(limit: int | None = None) -> dict:
    conn = bt.connect()
    option_conn = od.open_readonly()
    started = time.perf_counter()
    exits = {n: clock_only(n) for n in HORIZONS}
    trades: dict[tuple[str, int], list] = defaultdict(list)
    sessions_scored = 0

    try:
        roster = build_roster(conn)
        print(f"{len(roster)} strategies x {len(HORIZONS)} horizons, one pass",
              flush=True)
        tradeable = om.sessions_with_zero_dte(option_conn)
        vol_cache: dict[str, float | None] = {}

        # A smoke run takes the NEWEST sessions: the archive starts long
        # before same-day expiries existed, so the oldest N would be
        # skipped wholesale and score nothing.
        for session, rows in bt.load_sessions(conn, limit=limit,
                                              newest=bool(limit)):
            if session not in tradeable:
                continue
            if session not in vol_cache:
                vol_cache[session] = om.implied_vol_for_session(option_conn, session)
            vol = vol_cache[session]
            if not vol:
                continue
            sessions_scored += 1
            for play, signal_fn in roster:
                signals = signal_fn(rows)
                if not signals:
                    continue
                # Signals computed ONCE, then replayed under each clock.
                for minutes in HORIZONS:
                    trades[(play, minutes)].extend(
                        ob.simulate_option_trades(
                            rows, signals, vol, exits[minutes], strategy=play
                        )
                    )
            if sessions_scored % 100 == 0:
                print(f"  {sessions_scored} sessions "
                      f"({time.perf_counter() - started:.0f}s)", flush=True)
    finally:
        conn.close()
        option_conn.close()

    results = {
        play: {str(n): ob.summarize_options(trades[(play, n)]) for n in HORIZONS}
        for play, _ in build_roster_names(trades)
    }
    return {
        "sessions_scored": sessions_scored,
        "horizons": list(HORIZONS),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "results": results,
    }


def build_roster_names(trades: dict) -> list[tuple[str, None]]:
    seen: list[tuple[str, None]] = []
    for play, _minutes in trades:
        if (play, None) not in seen:
            seen.append((play, None))
    return seen


def _rank(results: dict) -> list[str]:
    """Strategies ordered by their best horizon's $/trade, best first."""
    def best(play: str) -> float:
        return max((results[play][str(n)].get("avg_dollars") or 0.0)
                   for n in HORIZONS)
    return sorted(results, key=lambda p: -best(p))


def render(payload: dict) -> str:
    results = payload["results"]
    baseline = {}
    baseline_path = Path("state/backtest_cards.json")
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            baseline = {}

    lines = [
        "# Fixed-Clock Exit Study",
        "",
        (__doc__ or "").strip(),
        "",
        f"Sessions scored: **{payload['sessions_scored']:,}** "
        f"(only sessions where a same-day expiry really existed). "
        f"Run time {payload['elapsed_seconds'] / 60:.0f} min.",
        "",
        "## $/trade by horizon",
        "",
        "| Strategy | 5m | 10m | 15m | 20m | 25m | 30m | best | its own exit (BASELINE) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for play in _rank(results):
        row = results[play]
        cells = []
        best_dollars, best_n = None, None
        for n in HORIZONS:
            avg = row[str(n)].get("avg_dollars")
            trades = row[str(n)].get("trades") or 0
            cells.append("-" if not trades else f"{avg:+.2f}")
            if trades and (best_dollars is None or avg > best_dollars):
                best_dollars, best_n = avg, n
        base = baseline.get(play, {})
        # SPY_KEY_LEVELS has no target_pct/stop_pct at all - its card
        # carries None for both because it triggers on the underlying.
        # Formatting None as a number is what crashed the first render.
        target, stop = base.get("target_pct"), base.get("stop_pct")
        shape = (f" ({target:+.0f}/{stop:+.0f})"
                 if target is not None and stop is not None
                 else " (underlying stop/target)")
        base_cell = ("not measured" if not base
                     else f"{base.get('avg_dollars') or 0:+.2f}{shape}")
        label = play + (" *" if play == UNDERLYING_EXIT_STRATEGY else "")
        best_cell = "-" if best_n is None else f"**{best_dollars:+.2f}** @ {best_n}m"
        lines.append(f"| {label} | " + " | ".join(cells)
                     + f" | {best_cell} | {base_cell} |")

    lines += [
        "",
        f"`*` {UNDERLYING_EXIT_STRATEGY} exits on the UNDERLYING live, so its "
        "BASELINE column is not a like-for-like comparison.",
        "",
        "## Win rate by horizon",
        "",
        "| Strategy | 5m | 10m | 15m | 20m | 25m | 30m |",
        "|---|---|---|---|---|---|---|",
    ]
    for play in _rank(results):
        row = results[play]
        cells = []
        for n in HORIZONS:
            stats = row[str(n)]
            cells.append("-" if not stats.get("trades")
                         else f"{stats.get('win_rate', 0):.1f}%")
        lines.append(f"| {play} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Trades and total P/L by horizon",
        "",
        "| Strategy | " + " | ".join(f"{n}m trades / total $" for n in HORIZONS) + " |",
        "|---|" + "---|" * len(HORIZONS),
    ]
    for play in _rank(results):
        row = results[play]
        cells = []
        for n in HORIZONS:
            stats = row[str(n)]
            trades = stats.get("trades") or 0
            cells.append("-" if not trades
                         else f"{trades:,} / {stats.get('total_dollars', 0):+,.0f}")
        lines.append(f"| {play} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "Trade counts rise as the horizon shortens because one position at a "
        "time is a live rule: a 5-minute clock is free to take the next signal "
        "while a 30-minute clock is still holding the first.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    limit = None
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
        print(f"SMOKE RUN: {limit} sessions", flush=True)

    payload = run(limit=limit)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    results = payload["results"]
    header = f"{'strategy':<24}" + "".join(f"{f'{n}m':>9}" for n in HORIZONS) + f"{'best':>14}"
    print(f"\nsessions scored: {payload['sessions_scored']:,}\n")
    print(header)
    print("-" * len(header))
    for play in _rank(results):
        row = results[play]
        cells = ""
        best_dollars, best_n = None, None
        for n in HORIZONS:
            stats = row[str(n)]
            if not stats.get("trades"):
                cells += f"{'-':>9}"
                continue
            avg = stats.get("avg_dollars") or 0.0
            cells += f"{avg:>+9.2f}"
            if best_dollars is None or avg > best_dollars:
                best_dollars, best_n = avg, n
        best = "-" if best_n is None else f"{best_dollars:+.2f} @ {best_n}m"
        print(f"{play:<24}{cells}{best:>14}")

    if limit is None:
        OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
        OUT_DOC.write_text(render(payload), encoding="utf-8")
        print(f"\nwrote {OUT_DOC}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
