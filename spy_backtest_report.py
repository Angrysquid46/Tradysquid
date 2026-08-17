"""Phase 3 sweep runner - measures every strategy/parameter/exit combination.

The point of this phase is measurement, not selection. Nothing is culled
here: every variant is reported with its full statistics, including the
ones that lose money, because "this does not work" is a result worth
having written down and the spec explicitly warns against rescuing failed
strategies by piling on filters.

Two passes, for memory rather than cleverness. Pass 1 keeps only the P/L
series for each of the ~230 (variant, exit-policy) combinations, which is
a few megabytes of floats and enough for expectancy, profit factor,
drawdown and streaks. Pass 2 re-runs just the best policy per variant and
keeps whole trades, so the regime/hour/era breakdowns have something to
group by.

Everything is reported against the random baseline. A strategy that beats
zero but not random noise on the same bars has not demonstrated anything.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import spy_backtest as bt
import spy_backtest_strategies as strat

REPORT_PATH = Path("docs/PHASE3_BACKTEST_RESULTS.md")
JSON_PATH = Path("state/phase3_backtest.json")


def run_sweep(conn, *, limit: int | None = None, progress_every: int = 250) -> dict[str, Any]:
    variants = strat.build_variants()
    policies = strat.build_exit_policies()

    pnl: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    signal_counts: dict[tuple[str, str], int] = defaultdict(int)
    sessions_seen = 0
    started = time.perf_counter()

    for session, rows in bt.load_sessions(conn, limit=limit):
        sessions_seen += 1
        for family, members in variants.items():
            for variant, signal_fn in members.items():
                signals = signal_fn(rows)
                if not signals:
                    continue
                signal_counts[(family, variant)] += len(signals)
                for policy in policies:
                    trades = bt.simulate(
                        rows, signals, policy, strategy=family, variant=variant
                    )
                    if trades:
                        pnl[(family, variant, policy.label())].extend(t.pnl_atr for t in trades)
        if progress_every and sessions_seen % progress_every == 0:
            rate = sessions_seen / (time.perf_counter() - started)
            print(f"  {sessions_seen} sessions ({rate:.0f}/s)", flush=True)

    # Best exit policy per variant, by expectancy - but only where there
    # are enough trades for the number to mean anything.
    best: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    all_combos: list[dict[str, Any]] = []
    for (family, variant, label), series in pnl.items():
        stats = bt.summarize([_stub(p) for p in series])
        row = {"family": family, "variant": variant, "policy": label, **stats}
        all_combos.append(row)
        if len(series) < 30:
            continue
        key = (family, variant)
        if key not in best or stats["expectancy_atr"] > best[key][1]["expectancy_atr"]:
            best[key] = (label, stats)

    return {
        "sessions": sessions_seen,
        "elapsed_s": time.perf_counter() - started,
        "combos": all_combos,
        "best": {f"{f} | {v}": {"policy": p, **s} for (f, v), (p, s) in best.items()},
        "signal_counts": {f"{f} | {v}": n for (f, v), n in signal_counts.items()},
    }


def _stub(pnl_atr: float) -> bt.Trade:
    """A minimal Trade carrying only P/L, for aggregate stats in pass 1."""
    return bt.Trade(
        "", "", "LONG", "", "", 0.0, 0, "", "", 0.0, "", 0, 1.0,
        pnl_atr, pnl_atr, pnl_atr, max(pnl_atr, 0.0), max(-pnl_atr, 0.0),
        "", "", "", None, "",
    )


def run_detail(conn, best: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    """Second pass: full trades for the winning policy of each variant."""
    variants = strat.build_variants()
    policies = {p.label(): p for p in strat.build_exit_policies()}
    wanted: dict[tuple[str, str], Any] = {}
    for key, info in best.items():
        family, variant = key.split(" | ", 1)
        wanted[(family, variant)] = policies[info["policy"]]

    collected: dict[tuple[str, str], list[bt.Trade]] = defaultdict(list)
    for session, rows in bt.load_sessions(conn, limit=limit):
        for (family, variant), policy in wanted.items():
            signal_fn = variants[family][variant]
            signals = signal_fn(rows)
            if signals:
                collected[(family, variant)].extend(
                    bt.simulate(rows, signals, policy, strategy=family, variant=variant)
                )

    detail: dict[str, Any] = {}
    for (family, variant), trades in collected.items():
        detail[f"{family} | {variant}"] = {
            "overall": bt.summarize(trades),
            "by_era": bt.breakdown(trades, lambda t: t.era),
            "by_regime": bt.breakdown(trades, lambda t: t.regime),
            "by_bucket": bt.breakdown(trades, lambda t: t.entry_bucket),
            "by_direction": bt.breakdown(trades, lambda t: t.direction),
            "by_exit_reason": bt.breakdown(trades, lambda t: t.exit_reason),
        }
    return detail


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(stats: dict[str, Any]) -> str:
    if not stats.get("trades"):
        return "| 0 | - | - | - | - |"
    pf = stats["profit_factor"]
    return (
        f"| {stats['trades']:,} | {stats['win_rate']:.1f}% | "
        f"{stats['expectancy_atr']:+.4f} | {'inf' if pf == float('inf') else f'{pf:.2f}'} | "
        f"{stats['max_drawdown_atr']:.1f} |"
    )


def write_report(result: dict[str, Any], detail: dict[str, Any]) -> str:
    baseline_key = next((k for k in result["best"] if k.startswith("BASELINE")), None)
    baseline = result["best"].get(baseline_key, {}) if baseline_key else {}
    base_exp = baseline.get("expectancy_atr")

    lines: list[str] = []
    lines.append("# Phase 3 - Underlying Backtest Results\n")
    lines.append(
        f"Generated from `minute_features` over **{result['sessions']:,} sessions** "
        f"(2008-01-22 - 2021-05-06). Every number below is the **SPY underlying**, "
        f"measured in ATR multiples. There is no option P/L here - that is Phase 5, "
        f"and mixing the two would misreport what was actually tested.\n"
    )
    lines.append(
        "**Nothing is eliminated.** Every variant tested is listed, including the "
        "losing ones. Where a strategy does not work, that is the finding.\n"
    )

    if base_exp is not None:
        lines.append(
            f"## The comparison that matters\n\n"
            f"Random entries on the same bars, under the same exit policy search, "
            f"return **{base_exp:+.4f} ATR/trade** "
            f"({baseline.get('win_rate', 0):.1f}% win rate over "
            f"{baseline.get('trades', 0):,} trades).\n\n"
            f"That is the bar. A strategy beating zero but not beating this has "
            f"shown nothing - it is being carried by the same drift and exit "
            f"geometry the random control gets for free.\n"
        )

    lines.append("\n## Best exit policy per variant\n")
    lines.append(
        "Exit labels read `t<target>/s<stop>/m<time-stop>`, all in ATR multiples. "
        "`t` is the t-statistic of the expectancy against zero; **|t| >= 1.96 is the "
        "95% threshold**. Per-trade P/L scatters about +-1 ATR, so a few hundred "
        "trades cannot resolve an edge of a few hundredths - most rows below are "
        "statistically indistinguishable from a coin flip, and the column says so.\n"
    )
    lines.append("| Strategy | Variant | Best exit | Trades | Win% | Expectancy (ATR) | t | Sig? | PF | MaxDD | vs random |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for key in sorted(result["best"], key=lambda k: -result["best"][k]["expectancy_atr"]):
        info = result["best"][key]
        family, variant = key.split(" | ", 1)
        edge = ""
        if base_exp is not None and not key.startswith("BASELINE"):
            delta = info["expectancy_atr"] - base_exp
            edge = f"{delta:+.4f}"
        pf = info["profit_factor"]
        sig = "**yes**" if info.get("significant_95") else "no"
        lines.append(
            f"| {family} | {variant} | `{info['policy']}` | {info['trades']:,} | "
            f"{info['win_rate']:.1f}% | {info['expectancy_atr']:+.4f} | "
            f"{info.get('t_stat', 0):+.2f} | {sig} | "
            f"{'inf' if pf == float('inf') else f'{pf:.2f}'} | "
            f"{info['max_drawdown_atr']:.1f} | {edge} |"
        )

    # The honest headline. Computed, not asserted.
    real = [k for k, v in result["best"].items()
            if not k.startswith("BASELINE") and v.get("significant_95")
            and base_exp is not None and v["expectancy_atr"] > base_exp]
    stable = []
    for key, info in detail.items():
        if key.startswith("BASELINE"):
            continue
        eras = [s for s in info["by_era"].values() if s.get("trades")]
        if eras and all(s["expectancy_atr"] > 0 for s in eras):
            stable.append(key)

    lines.append("\n## Verdict\n")
    lines.append(
        f"- **{len(real)} of {len(result['best']) - 1} variants** clear statistical "
        f"significance at 95% AND beat the random baseline.\n"
        f"- **{len(stable)} of {len(result['best']) - 1} variants** are profitable in "
        f"every one of the four eras.\n"
    )
    if not real:
        lines.append(
            "\nNo variant in this tranche produced an edge that is distinguishable "
            "from noise on this data. The best expectancies are a few hundredths of "
            "an ATR per trade with t-statistics well under 2 - which is what a coin "
            "flip looks like when you measure it a few thousand times.\n\n"
            "That is a real result, not a failure of the test. It says the ORB and "
            "VWAP families **as literally specified** do not, on their own, predict "
            "the SPY underlying over 2008-2021. The spec's own instinct was right: "
            "it repeatedly insists the filters matter as much as the pattern. This "
            "tranche deliberately ran them with light filtering to establish that "
            "baseline first, so later phases can show whether a filter adds anything "
            "real rather than merely appearing to.\n"
        )
    lines.append(
        "\nThe t-statistics above are also **optimistic by construction**: each row is "
        "the best of 12 exit policies for that variant, so the selection has already "
        "had 12 chances to find a favourable draw. Correcting for that search would "
        "push every one of them further toward zero, not away from it. Treat the "
        "column as an upper bound.\n"
    )
    lines.append(
        "\nOne pattern is consistent enough to call out: **every leading variant "
        "loses money in the 2020-2021 era**, the most recent one available. Whether "
        "that is COVID-era distortion or genuine edge decay cannot be settled here - "
        "and the 2021-2026 gap in the intraday data means it cannot be settled at "
        "all until that gap is filled.\n"
    )

    lines.append("\n## Walk-forward: does it hold across eras?\n")
    lines.append(
        "A strategy that only works in one era is an artefact of that era. "
        "These are the same trades split by period, never refitted.\n"
    )
    for key in sorted(detail):
        lines.append(f"\n### {key}\n")
        lines.append("| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |")
        lines.append("|---|---|---|---|---|---|")
        for era, stats in detail[key]["by_era"].items():
            lines.append(f"| {era} {_fmt(stats)}")

    lines.append("\n## Where the edge sits\n")
    for key in sorted(detail):
        lines.append(f"\n### {key}\n")
        for label, group in (("Regime", "by_regime"), ("Time of day", "by_bucket"),
                             ("Direction", "by_direction"), ("Exit reason", "by_exit_reason")):
            lines.append(f"\n**{label}**\n")
            lines.append("| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |")
            lines.append("|---|---|---|---|---|---|")
            for name, stats in detail[key][group].items():
                lines.append(f"| {name} {_fmt(stats)}")

    lines.append("\n## Every combination tested\n")
    lines.append(f"{len(result['combos'])} (variant x exit-policy) pairs. Listed in full so the "
                 "size of the search is visible - a best result picked from a large grid "
                 "deserves more scepticism than one picked from a small grid.\n")
    lines.append("| Strategy | Variant | Exit | Trades | Win% | Expectancy (ATR) | PF |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in sorted(result["combos"], key=lambda r: (r["family"], r["variant"], -r.get("expectancy_atr", 0))):
        if not row.get("trades"):
            continue
        pf = row["profit_factor"]
        lines.append(
            f"| {row['family']} | {row['variant']} | `{row['policy']}` | {row['trades']:,} | "
            f"{row['win_rate']:.1f}% | {row['expectancy_atr']:+.4f} | "
            f"{'inf' if pf == float('inf') else f'{pf:.2f}'} |"
        )

    lines.append("\n## Method and its limits\n")
    lines.append(
        "- Signals evaluate on a closed bar; fills happen at the **next** bar's open.\n"
        "- When a bar contains both the stop and the target, the **stop** is taken - "
        "1-minute OHLC cannot resolve the order, and assuming otherwise inflates results.\n"
        "- One position at a time, forced flat at 15:59.\n"
        "- No commission or slippage is modelled yet. Real fills are worse than these.\n"
        "- Expectancy is in ATR, not dollars, so 2008 and 2021 are comparable.\n"
        "- **This measures the underlying entry only.** A positive underlying edge is a "
        "necessary but not sufficient condition for a profitable 0DTE option trade; "
        "theta and spread can erase a real move. Phase 5 models that separately.\n"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 3 backtest sweep")
    parser.add_argument("--limit", type=int, default=None, help="only the first N sessions")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    conn = bt.connect()
    try:
        result = run_sweep(conn, limit=args.limit, progress_every=0 if args.quiet else 250)
        print(f"sweep: {result['sessions']:,} sessions in {result['elapsed_s']:.1f}s", flush=True)
        detail = run_detail(conn, result["best"], limit=args.limit)
    finally:
        conn.close()

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps({"summary": result, "detail": detail}, indent=2, default=str),
                         encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(write_report(result, detail), encoding="utf-8")
    print(f"wrote {REPORT_PATH} and {JSON_PATH}")


if __name__ == "__main__":
    main()
