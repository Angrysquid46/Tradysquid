"""Each strategy through the option layer using ITS OWN exit rules.

Every option run before this one imposed a single +50/-50 exit on all 13
strategies. They do not use that shape - NEW_STRATEGY_EXITS gives six
distinct configurations, targets from +40% to +150% and stops from -40%
to -75%. Testing them all under one exit produced a "discovery" that
every strategy shares a payoff ratio of 1.32, which was not a finding at
all: it was the imposed exit showing up in the output.

It also understated them. On one entry, sweeping the exit moved results
from +$15.90/trade at +50/-50 to +$57.81 at +150/-50 - and +150/-75 is
what most of these strategies actually run.

Owner, repeatedly: every strategy gets its own rules. This measures them
that way.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

import spy_backtest as bt
import spy_live_new_strategies as lns
import spy_option_backtest as ob
import spy_option_data as od
import spy_option_report as orep

# play_type -> the research variant that implements the same entry.
ENTRY_KEYS = {
    "SPY_GAP_CONT_50": "S21 Gap continuation | gap>=0.5%",
    "SPY_FAILED_BREAK": "S7 Failed breakout | prev-day levels",
    "SPY_ORB_IMMEDIATE": "S2 ORB immediate | or30",
    "SPY_SWEEP_10": "S8 Liquidity sweep | reclaim<=10bars",
    "SPY_VWAP_RECLAIM": "S4 VWAP reclaim | chop<=2",
    "SPY_MOMENTUM_ADX25": "S14 Momentum continuation | adx25 unaligned",
    "SPY_TOD_MIDDAY": "S18 Time-of-day | MIDDAY",
    "SPY_CONFLUENCE_4": "S16 Confluence | 4+ levels",
    "SPY_TOD_FINAL30": "S18 Time-of-day | FINAL_30",
    "SPY_MTF_4OF4": "S19 MTF breakout | 4/4 agree",
    "SPY_EXHAUSTION_1ATR": "S15 Momentum exhaustion | 1.0atr ext",
    "SPY_FIRST_PULLBACK": "S12 First pullback | 0.5atr drive",
    "SPY_OPENING_GAP_FADE": "PB1 Opening gap fade | spec thresholds",
}

# SPY_KEY_LEVELS exits on an R-multiple of the underlying (2.0R target,
# 0.15% stop buffer), not an option-premium percentage, so it cannot be
# expressed in this framework. Run separately under the default shape and
# labelled as such rather than silently given someone else's exit.
EXTRA = {"LIVE SPY_KEY_LEVELS | deployed rules": None}

OUT = Path("docs/OPTION_RESULTS_OWN_EXITS.md")


def main() -> None:
    conn = bt.connect()
    option_conn = od.connect()
    rows = []
    shapes = {}
    for play, key in list(ENTRY_KEYS.items()) + [(k, k) for k in EXTRA]:
        if play in EXTRA:
            target, stop = 50.0, -50.0      # documented default, not its real exit
        else:
            target, stop, _t = lns.NEW_STRATEGY_EXITS[play]
        shapes[key] = ob.OptionExit(
            target_pct=target, stop_pct=stop,
            floor_trigger_pct=None, floor_pct=None,
            name=f"{play} ({target:+.0f}/{stop:+.0f})",
        )
    back = {v: k for k, v in list(ENTRY_KEYS.items()) + [(k, k) for k in EXTRA]}

    try:
        print(f"one pass, {len(shapes)} strategies, each with its own exit...",
              flush=True)
        res = orep.run(conn, option_conn, keys=list(shapes), exit_shapes=shapes)
    finally:
        conn.close()
        option_conn.close()

    payload = res.get("results") or {}
    for key, stats in payload.items():
        if not isinstance(stats, dict) or not stats.get("trades"):
            continue
        play = back.get(key, key)
        shape = shapes[key]
        n = stats["trades"]
        w = (stats.get("win_rate") or 0) / 100.0
        pf = stats.get("profit_factor") or 0
        ratio = pf * (1 - w) / w if 0 < w < 1 and pf > 0 else float("nan")
        be = 1 / (1 + ratio) * 100 if ratio == ratio and ratio > 0 else float("nan")
        rows.append((play, shape.target_pct, shape.stop_pct, n, w * 100, pf,
                     ratio, be, stats.get("avg_dollars") or 0,
                     stats.get("total_dollars") or 0))

    if not rows:
        print("no results")
        return
    rows.sort(key=lambda r: -r[8])
    print(f"\n{'strategy':<24}{'exit':>12}{'n':>8}{'win%':>7}{'ratio':>7}"
          f"{'BE%':>7}{'$/trade':>9}{'total $':>11}")
    print("-" * 86)
    for p, t, s, n, w, pf, ratio, be, avg, tot in rows:
        print(f"{p:<24}{f'{t:+.0f}/{s:+.0f}':>12}{n:>8,}{w:>7.1f}{ratio:>7.2f}"
              f"{be:>7.1f}{avg:>9.2f}{tot:>11,.0f}")
    good = [r for r in rows if r[8] > 0]
    solid = [r for r in good if r[3] >= 100]
    print(f"\nprofitable per trade: {len(good)}/{len(rows)}")
    print(f"profitable AND >=100 trades: {len(solid)}/{len(rows)}")

    lines = ["# Each Strategy With Its Own Exit Rules\n", __doc__ or "", "\n",
             "| Strategy | Exit | Trades | Win% | Payoff | BE win% | $/trade | Total |",
             "|---|---|---|---|---|---|---|---|"]
    for p, t, s, n, w, pf, ratio, be, avg, tot in rows:
        lines.append(f"| {p} | {t:+.0f}/{s:+.0f} | {n:,} | {w:.1f} | "
                     f"{ratio:.2f} | {be:.1f} | {avg:+.2f} | {tot:+,.0f} |")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
