"""Phase 5 step 4 - re-run the shortlist as 0DTE options.

Produces the side-by-side the owner asked for: underlying edge next to
option edge, so it is visible which strategies are actually better as
0DTE trades rather than as underlying moves.

Scored only on sessions where a same-day expiry really existed, and every
option number is modelled from a real IV level for that day. Both facts
are stated in the output rather than left in a docstring.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import spy_backtest as bt
import spy_option_backtest as ob
import spy_option_data as od
import spy_option_model as om
import spy_backtest_report as rep

REPORT_PATH = Path("docs/OPTION_RESULTS.md")
JSON_PATH = Path("state/option_results.json")

# The 15 the owner selected for Discord, by (family, variant) key.
SHORTLIST = [
    "S21 Gap continuation | gap>=0.5%",
    "S7 Failed breakout | prev-day levels",
    "S21 Gap continuation | gap>=0.25%",
    "S8 Liquidity sweep | reclaim<=10bars",
    "S8 Liquidity sweep | reclaim<=5bars",
    "S14 Momentum continuation | adx25 unaligned",
    "S18 Time-of-day | MIDDAY",
    "S16 Confluence | 4+ levels",
    "S18 Time-of-day | FINAL_30",
    "S19 MTF breakout | 4/4 agree",
    "LIVE SPY_KEY_LEVELS | deployed rules",
    "S15 Momentum exhaustion | 1.0atr ext",
    "S21 Gap continuation | gap>=1.0%",
    "S12 First pullback | 0.5atr drive",
    "PB1 Opening gap fade | spec thresholds",
]


def run(conn, option_conn, *, keys=None, exit_shape=None, limit=None) -> dict[str, Any]:
    variants = rep.all_variants(conn=conn)
    wanted = {}
    for key in (keys or SHORTLIST):
        family, variant = key.split(" | ", 1)
        if family in variants and variant in variants[family]:
            wanted[key] = variants[family][variant]

    tradeable = om.sessions_with_zero_dte(option_conn)
    rules = exit_shape or ob.OptionExit()

    trades: dict[str, list] = defaultdict(list)
    vol_cache: dict[str, float | None] = {}
    sessions_scored = 0

    for session, rows in bt.load_sessions(conn, limit=limit):
        if session not in tradeable:
            continue
        if session not in vol_cache:
            vol_cache[session] = om.implied_vol_for_session(option_conn, session)
        vol = vol_cache[session]
        if not vol:
            continue
        sessions_scored += 1
        for key, signal_fn in wanted.items():
            signals = signal_fn(rows)
            if signals:
                trades[key].extend(
                    ob.simulate_option_trades(rows, signals, vol, rules, strategy=key)
                )

    return {
        "sessions_scored": sessions_scored,
        "exit_shape": rules.name,
        "results": {k: ob.summarize_options(v) for k, v in trades.items()},
    }


def compare_exit_shapes(conn, option_conn, key: str, *, limit=None) -> dict[str, Any]:
    """Run one strategy through every live exit shape.

    This is what underlying bars could never do: the 10 ratchet variants
    share one entry and differ only here, so this is the first time they
    can be ranked against each other at all."""
    out = {}
    for shape in ob.live_exit_shapes():
        result = run(conn, option_conn, keys=[key], exit_shape=shape, limit=limit)
        out[shape.name] = result["results"].get(key, {"trades": 0})
    return out


def write_report(underlying: dict[str, Any], option: dict[str, Any],
                 shapes: dict[str, Any], key: str) -> str:
    lines = ["# 0DTE Option Results (Phase 5)\n"]
    lines.append(
        "The side-by-side: **underlying edge next to option edge**, so it is "
        "visible which strategies are actually better as 0DTE trades rather than "
        "as underlying moves.\n"
    )
    lines.append(
        f"\n> ⚠️ **Every option number here is MODELLED.** The archive contains no "
        f"intraday option quotes at all — only 16:00 snapshots, at which point a "
        f"0DTE is minutes from expiry and worth roughly intrinsic. Prices are "
        f"Black-Scholes from a **real IV level for that day**, priced to the "
        f"session close. Validated against real 1DTE quotes: median error −8.2%, "
        f"87% within 25%.\n"
        f">\n"
        f"> Scored on **{option['sessions_scored']:,} sessions where a same-day "
        f"expiry actually existed**. Before 2023, most days had none (38–157 per "
        f"year), so this sample is far smaller than the underlying results and "
        f"the conclusions are correspondingly weaker.\n"
        f">\n"
        f"> Entry pays the ask, exit receives the bid, ${ob.COMMISSION_PER_CONTRACT:.2f}"
        f"/contract each way. Position size uses the live ${ob.MAX_RISK_PER_TRADE:.0f} "
        f"cap and ${ob.MAX_CONTRACT_ASK:.2f} max ask.\n"
    )

    lines.append(f"\n## The shortlist as options — exit shape `{option['exit_shape']}`\n")
    lines.append("| Strategy | Underlying exp (ATR) | Option trades | Win% | Option exp (%) | **Total P/L** | PF | EOD exits | Survives? |")
    lines.append("|---|---|---|---|---|---|---|---|---|")

    survivors = []
    for key_name in SHORTLIST:
        under = underlying.get(key_name, {})
        opt = option["results"].get(key_name, {"trades": 0})
        if not opt.get("trades"):
            lines.append(f"| {key_name} | {under.get('expectancy_atr', 0):+.4f} | 0 | — | — | — | — | — | no data |")
            continue
        survived = opt["total_dollars"] > 0 and opt["expectancy_pct"] > 0
        if survived:
            survivors.append((key_name, opt))
        pf = opt["profit_factor"]
        lines.append(
            f"| {key_name} | {under.get('expectancy_atr', 0):+.4f} | {opt['trades']:,} | "
            f"{opt['win_rate']:.1f}% | {opt['expectancy_pct']:+.1f}% | "
            f"${opt['total_dollars']:+,.0f} | "
            f"{'inf' if pf == float('inf') else f'{pf:.2f}'} | "
            f"{opt['pct_eod_exits']:.0f}% | {'**YES**' if survived else 'no'} |"
        )

    lines.append(
        f"\n**{len(survivors)} of {len(SHORTLIST)} survive the option layer** "
        f"(positive total P/L and positive average return per trade, after "
        f"spread and commission).\n"
    )
    if survivors:
        lines.append("\nSurvivors, best first:\n")
        for name, opt in sorted(survivors, key=lambda kv: -kv[1]["total_dollars"]):
            lines.append(
                f"- **{name}** — {opt['trades']:,} trades, {opt['win_rate']:.1f}% win, "
                f"{opt['expectancy_pct']:+.1f}% per trade, **${opt['total_dollars']:+,.0f}** total."
            )
        lines.append("")

    if shapes:
        lines.append(f"\n## Exit-shape comparison on `{key}`\n")
        lines.append(
            "The 10 live ratchet variants share one entry and differ **only** in "
            "exit shape, which is defined in option-premium percent. On underlying "
            "bars they are indistinguishable; this is the first time they can be "
            "ranked against each other.\n"
        )
        lines.append("| Exit shape | Trades | Win% | Exp (%) | Total P/L | PF | EOD exits |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, stats in sorted(shapes.items(), key=lambda kv: -(kv[1].get("total_dollars") or -1e9)):
            if not stats.get("trades"):
                lines.append(f"| `{name}` | 0 | — | — | — | — | — |")
                continue
            pf = stats["profit_factor"]
            lines.append(
                f"| `{name}` | {stats['trades']:,} | {stats['win_rate']:.1f}% | "
                f"{stats['expectancy_pct']:+.1f}% | ${stats['total_dollars']:+,.0f} | "
                f"{'inf' if pf == float('inf') else f'{pf:.2f}'} | {stats['pct_eod_exits']:.0f}% |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    conn = bt.connect()
    option_conn = od.open_readonly()
    try:
        underlying = {}
        if Path("state/backtest_results.json").exists():
            underlying = json.loads(
                Path("state/backtest_results.json").read_text(encoding="utf-8")
            )["summary"]["best"]

        print("running shortlist as options...", flush=True)
        option = run(conn, option_conn)
        print(f"  {option['sessions_scored']:,} tradeable sessions", flush=True)

        top = SHORTLIST[0]
        print(f"comparing exit shapes on {top}...", flush=True)
        shapes = compare_exit_shapes(conn, option_conn, top)
    finally:
        conn.close()
        option_conn.close()

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps({"option": option, "shapes": shapes}, indent=2, default=str),
                         encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(write_report(underlying, option, shapes, top), encoding="utf-8")
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
