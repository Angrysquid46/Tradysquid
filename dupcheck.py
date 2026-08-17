"""Phase 6: duplicate-signal detection across the live strategy set.

The owner's requirement is that every strategy is its own idea with its own
rules - no copy-paste. This measures whether that actually holds on real
data, rather than assuming it because the code paths differ.

Two strategies can have completely different code and still be the same
trade: if they fire on the same bar in the same direction most of the time,
they are one signal wearing two names, and running both just doubles size
on one idea while looking like diversification.
"""
from __future__ import annotations
import itertools, json
from collections import defaultdict

import spy_backtest as bt
import spy_backtest_report as rep
import spy_live_new_strategies as lns

SESSIONS = 600   # enough for stable overlap rates without a full sweep

def main() -> None:
    conn = bt.connect()
    variants = rep.all_variants(conn=conn)
    # Map each live strategy to the signal function actually traded.
    fns = {}
    for spec in lns.NEW_STRATEGY_SPECS:
        fns[spec["play_type"]] = spec["signal"]
    fns["SPY_KEY_LEVELS"] = variants["LIVE SPY_KEY_LEVELS"]["deployed rules"]

    # (bar_time, direction) sets per strategy
    fired = defaultdict(set)
    n = 0
    for session, rows in bt.load_sessions(conn, limit=SESSIONS):
        n += 1
        for play_type, fn in fns.items():
            try:
                for index, direction in fn(rows):
                    fired[play_type].add((rows[index]["bar_time"], direction))
            except Exception:
                pass
    conn.close()

    print(f"sessions analysed: {n}\n")
    print(f"{'strategy':24s} {'signals':>8s}")
    for play_type in fns:
        print(f"  {play_type:22s} {len(fired[play_type]):>8,}")

    print("\npairwise overlap (Jaccard = shared / combined; >0.50 means near-duplicate)")
    pairs = []
    for a, b in itertools.combinations(fns, 2):
        sa, sb = fired[a], fired[b]
        if not sa or not sb:
            continue
        shared = len(sa & sb)
        union = len(sa | sb)
        jac = shared / union if union else 0.0
        # How much of the SMALLER strategy is contained in the larger - a
        # strategy fully swallowed by another is redundant even if the
        # Jaccard looks moderate because of size difference.
        containment = shared / min(len(sa), len(sb))
        pairs.append((jac, containment, a, b, shared))
    pairs.sort(reverse=True)
    for jac, cont, a, b, shared in pairs[:15]:
        flag = "DUPLICATE" if jac > 0.5 or cont > 0.8 else ""
        print(f"  {jac:5.3f} jac  {cont:5.3f} contained  {shared:>6,} shared  {a} <-> {b}  {flag}")

    worst = [p for p in pairs if p[0] > 0.5 or p[1] > 0.8]
    print(f"\nnear-duplicate pairs: {len(worst)} of {len(pairs)}")
    json.dump({"sessions": n,
               "counts": {k: len(v) for k, v in fired.items()},
               "pairs": [{"jaccard": j, "containment": c, "a": a, "b": b, "shared": s}
                         for j, c, a, b, s in pairs]},
              open("state/signal_overlap.json", "w"), indent=2)

if __name__ == "__main__":
    main()
