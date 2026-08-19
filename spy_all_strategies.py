"""Backtest EVERY strategy as its own independent trader.

The full roster, each with its own rules, scored individually:

  ten separate traders with ten different exits (step_pct/stop_pct), so
  they get ten separate results.
- SPY_KEY_LEVELS - own entry, own exit.
- Every new research strategy from Phases 3-4, each with its own entry.

Exits are in option-premium percent, which is what makes the ten ratchets
distinguishable at all.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import spy_backtest as bt
import spy_backtest_report as rep
import spy_option_backtest as ob
import spy_option_data as od
import spy_option_model as om
import spy_scanner as ss

OUT_JSON = Path("state/all_strategies.json")

# ONE exit for research strategies, applied identically to all of them.
# Not a grid: each strategy is one entry rule plus one exit rule, scored
# once. Multiplying by several exits would turn ~70 real strategies into
# hundreds of invented variants and make the ranking meaningless.
RESEARCH_EXIT = ob.OptionExit(
    target_pct=200, stop_pct=-80, floor_trigger_pct=None, floor_pct=None, name="t200/s80"
)


def build_roster(conn):
    """(trader_name, entry_signal_fn, exit_rules) for every trader."""
    variants = rep.all_variants(conn=conn)
    orb1 = variants["LIVE SPY_0DTE (ORB)"]["1-min bars (1M + 10 ratchets)"]
    orb5 = variants["LIVE SPY_0DTE (ORB)"]["5-min bars (5M)"]

    spy0dte_exit = ob.OptionExit(
        target_pct=ss.SPY_TARGET_PCT * 100,
        stop_pct=-ss.SPY_STOP_PCT * 100,
        floor_trigger_pct=ss.SPY_FLOOR_TRIGGER_PCT,
        floor_pct=ss.SPY_FLOOR_PCT,
        name="spy0dte +50/-50 floor+30",
    )

    roster = [
    ]
    roster.append((
        "LIVE SPY_KEY_LEVELS", variants["LIVE SPY_KEY_LEVELS"]["deployed rules"],
        ob.OptionExit(target_pct=100, stop_pct=-50, floor_trigger_pct=None,
                      floor_pct=None, name="key-levels 2R"),
    ))

    # Research strategies: own entry, best of the exit grid.
    for family, members in variants.items():
        if family.startswith("LIVE") or family.startswith("BASELINE"):
            continue
        for variant_name, fn in members.items():
            roster.append((f"{family} | {variant_name}", fn, RESEARCH_EXIT))
    return roster


def main() -> None:
    conn = bt.connect()
    option_conn = od.open_readonly()
    started = time.perf_counter()
    try:
        roster = build_roster(conn)
        print(f"traders to score: {len(roster)}", flush=True)
        tradeable = om.sessions_with_zero_dte(option_conn)
        trades = {name: [] for name, _, _ in roster}
        vol_cache: dict[str, float | None] = {}
        scored = 0

        for session, rows in bt.load_sessions(conn):
            if session not in tradeable:
                continue
            if session not in vol_cache:
                vol_cache[session] = om.implied_vol_for_session(option_conn, session)
            vol = vol_cache[session]
            if not vol:
                continue
            scored += 1
            signal_cache: dict[int, list] = {}
            for name, fn, rules in roster:
                key = id(fn)
                if key not in signal_cache:
                    signal_cache[key] = fn(rows)
                signals = signal_cache[key]
                if signals:
                    trades[name].extend(
                        ob.simulate_option_trades(rows, signals, vol, rules, strategy=name)
                    )
            if scored % 100 == 0:
                print(f"  {scored} sessions ({time.perf_counter()-started:.0f}s)", flush=True)

        results = {name: ob.summarize_options(t) for name, t in trades.items()}
    finally:
        conn.close()
        option_conn.close()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"sessions": scored, "results": results},
                                   indent=2, default=str), encoding="utf-8")

    scored_rows = [(n, s) for n, s in results.items() if s.get("trades", 0) >= 30]
    scored_rows.sort(key=lambda kv: -kv[1]["total_dollars"])
    print(f"\nsessions scored: {scored}   traders with >=30 trades: {len(scored_rows)}\n")
    print(f"{'#':>2}  {'TRADER':58s} {'TRADES':>7s} {'WIN%':>6s} {'EXP%':>8s} {'TOTAL P/L':>13s} {'PF':>5s}")
    for i, (name, s) in enumerate(scored_rows[:15], 1):
        pf = s["profit_factor"]
        print(f"{i:2d}  {name[:58]:58s} {s['trades']:>7,} {s['win_rate']:>5.1f}% "
              f"{s['expectancy_pct']:>+7.1f}% ${s['total_dollars']:>+12,.0f} "
              f"{'inf' if pf == float('inf') else f'{pf:>5.2f}'}")
    print(f"\nfull results: {OUT_JSON}")


if __name__ == "__main__":
    main()
