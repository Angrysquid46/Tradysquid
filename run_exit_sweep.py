"""Every entry against a grid of exits, with corrected pricing."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
import backtest_lab as lab, exit_sweep as es
import spy_live_new_strategies as lns, spy_backtest_live_strategies as blive
import spy_backtest as bt, spy_intraday_features as sif

TARGETS = (25, 50, 75, 100, 150)
STOPS = (-25, -40, -50, -60, -75)
CLOCKS = (5, 10, 15, 20, 30, 45)
TRAILS = ((15, 20), (25, 40), (40, 60))
COMBOS = ((50, -50, 15), (75, -50, 30), (100, -60, 30))

def build_exits():
    out = {}
    for t in TARGETS:
        for s in STOPS:
            out[f"t{t}/s{abs(s)}"] = lab.target_and_stop(float(t), float(s))
    for m in CLOCKS:
        out[f"clock{m}m"] = lab.hold_for(m)
    for give, arm in TRAILS:
        out[f"trail{give}@{arm}"] = lab.trailing_stop(float(give), float(arm))
    for t, s, m in COMBOS:
        out[f"t{t}/s{abs(s)}/{m}m"] = lab.first_of(
            lab.target_and_stop(float(t), float(s)), lab.hold_for(m))
    return out

def build_entries():
    conn = bt.connect()
    try:
        sma = blive.daily_sma200(sif.all_session_ohlc(conn))
    finally:
        conn.close()
    e = {s["play_type"]: s["signal"] for s in lns.NEW_STRATEGY_SPECS}
    e["SPY_KEY_LEVELS"] = blive.live_key_levels(sma)
    return e

def main():
    # A window, not a count: `limit` takes the OLDEST sessions, which are
    # 2008-2009 and had no same-day expiry at all - it scores nothing.
    since = sys.argv[1] if len(sys.argv) > 1 else None
    until = sys.argv[2] if len(sys.argv) > 2 else None
    entries, exits = build_entries(), build_exits()
    print(f"{len(entries)} entries x {len(exits)} exits = "
          f"{len(entries)*len(exits)} combinations", flush=True)
    results, cov = es.sweep(entries, exits, since=since, until=until)
    payload = {f"{k[0]}|{k[1]}": {"entry": k[0], "exit": k[1],
               "trades": r.trades, "win_rate": r.win_rate,
               "avg_dollars": r.avg_dollars, "total_dollars": r.total_dollars}
               for k, r in results.items()}
    Path("state/exit_sweep.json").write_text(json.dumps(
        {"coverage": {"sessions": cov.sessions_scored,
                      "first": cov.first_session, "last": cov.last_session,
                      "measured_iv": cov.measured_sessions,
                      "proxy_iv": cov.proxy_sessions},
         "results": payload}, indent=2), encoding="utf-8")
    winners = [r for r in results.values() if r.trades >= 100 and r.avg_dollars > 0]
    print(f"\nsessions {cov.sessions_scored:,}  {cov.first_session} to {cov.last_session}")
    print(f"combinations with >=100 trades and positive $/trade: "
          f"{len(winners)} of {len(results)}")
    for r in sorted(winners, key=lambda r: -r.avg_dollars)[:25]:
        print(f"  {r.label:<40}{r.trades:>7,}{r.win_rate:>6.1f}%"
              f"{r.avg_dollars:>+9.2f}{r.total_dollars:>+11,.0f}")
    if not winners:
        best = sorted(results.values(), key=lambda r: -r.avg_dollars)[:10]
        print("\nnothing cleared. closest 10:")
        for r in best:
            print(f"  {r.label:<40}{r.trades:>7,}{r.win_rate:>6.1f}%"
                  f"{r.avg_dollars:>+9.2f}")

if __name__ == "__main__":
    main()
