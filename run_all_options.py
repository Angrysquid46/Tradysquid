"""Every strategy variant through the option layer, with corrected costs.

Two corrections since the last run:

* Commission was $0.65/contract each way - roughly 16x what this account
  pays. On a $115 contract that is 1.13% of position per round trip
  instead of 0.07%, charged against strategies whose entire edge is a few
  percent. It flipped Gap continuation >=1.0% from -$23,091 to +$24,595.
* The spread figure I had been quoting (4.6% of mid) was measured across
  every 0DTE contract in the chain, including expiring OTM ones with 58%
  spreads that the delta 0.40-0.60 filter would never select. On
  contracts actually tradeable it is 2.5%.

Ranked by DOLLARS PER TRADE, not by total. Total P/L mostly measures how
often a strategy trades: -$31/trade over 16,065 trades is -$497k, while
+$16/trade over 1,547 trades is +$25k, and the second is the better
strategy despite the smaller headline. Sample size is shown next to every
row because several apparent winners rest on ~12 trades.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

import spy_backtest as bt
import spy_backtest_report as rep
import spy_option_backtest as ob
import spy_option_data as od
import spy_option_report as orep

OUT_JSON = Path("state/option_results_all.json")
OUT_MD = Path("docs/OPTION_RESULTS_ALL.md")


def main() -> None:
    conn = bt.connect()
    option_conn = od.connect()
    try:
        variants = rep.all_variants(conn=conn)
        keys = [f"{fam} | {var}" for fam, vs in variants.items() for var in vs]
        print(f"running {len(keys)} variants through the option layer "
              f"at ${ob.COMMISSION_PER_CONTRACT:.2f}/contract...", flush=True)
        result = orep.run(conn, option_conn, keys=keys)
    finally:
        conn.close()
        option_conn.close()

    # run() returns {sessions_scored, exit_shape, results: {name: stats}} -
    # iterating the top level yields an int and a string and silently
    # filters every strategy out, which is exactly what happened on the
    # first 40-minute run.
    payload = result.get("results") if isinstance(result, dict) else None
    if not isinstance(payload, dict):
        payload = result
    rows = []
    for name, stats in payload.items():
        if not isinstance(stats, dict):
            continue
        n = stats.get("trades") or 0
        if not n:
            continue
        total = stats.get("total_dollars")
        if total is None:
            continue
        rows.append({
            "strategy": name, "trades": n,
            "per_trade": total / n,
            "total": total,
            "win_pct": stats.get("win_rate") or stats.get("win_pct") or 0,
            "exp_pct": stats.get("expectancy_pct") or 0,
            "pf": stats.get("profit_factor") or 0,
        })
    rows.sort(key=lambda r: -r["per_trade"])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    print(f"\n{'strategy':<46}{'trades':>8}{'$/trade':>10}{'total $':>12}"
          f"{'win%':>7}{'PF':>7}")
    print("-" * 90)
    for r in rows:
        flag = "  (thin)" if r["trades"] < 100 else ""
        print(f"{r['strategy'][:45]:<46}{r['trades']:>8,}{r['per_trade']:>10.2f}"
              f"{r['total']:>12,.0f}{r['win_pct']:>7.1f}{r['pf']:>7.2f}{flag}")

    good = [r for r in rows if r["per_trade"] > 0]
    solid = [r for r in good if r["trades"] >= 100]
    print(f"\nprofitable per trade: {len(good)}/{len(rows)}")
    print(f"profitable AND >=100 trades: {len(solid)}/{len(rows)}")
    for r in solid:
        print(f"   {r['strategy']:<46}{r['trades']:>7,} trades  "
              f"${r['per_trade']:>6.2f}/trade  ${r['total']:>10,.0f}")

    lines = ["# Every Variant Through the Option Layer\n", __doc__ or "", "\n",
             "| Strategy | Trades | $/trade | Total $ | Win% | PF |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['strategy']} | {r['trades']:,} | "
                     f"{r['per_trade']:+.2f} | {r['total']:+,.0f} | "
                     f"{r['win_pct']:.1f} | {r['pf']:.2f} |")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
