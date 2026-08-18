"""SPY_KEY_LEVELS under its OWN exit rule.

It exits on the underlying - a stop at the key level (0.15% buffer) and a
target at 2R - while marking P/L off the real option premium. The option
framework only understood premium-percentage triggers, so every previous
run gave it a borrowed +50/-50 shape that it does not use.

The signal function returns (bar, direction) and not the key level that
defines R, so the exact stop distance cannot be reconstructed. Rather than
pick one and present it as the answer, this sweeps the stop distance and
reports the range.
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
import spy_backtest as bt, spy_option_backtest as ob
import spy_option_data as od, spy_option_report as orep

KEY = "LIVE SPY_KEY_LEVELS | deployed rules"
STOPS = [0.10, 0.15, 0.20, 0.30, 0.45, 0.60]

conn = bt.connect(); oc = od.connect()
shapes = {}
for stop in STOPS:
    shapes[stop] = ob.OptionExit(
        target_pct=None, stop_pct=None, floor_trigger_pct=None, floor_pct=None,
        underlying_stop_pct=stop, underlying_r_multiple=2.0,
        name=f"underlying {stop}% stop, 2R target")

print(f"{'stop %':>8}{'trades':>9}{'win%':>8}{'ratio':>8}{'BE%':>7}{'$/trade':>10}{'total $':>11}")
print("-" * 62)
try:
    for stop, shape in shapes.items():
        res = orep.run(conn, oc, keys=[KEY], exit_shape=shape)
        st = (res.get("results") or {}).get(KEY) or {}
        n = st.get("trades") or 0
        if not n:
            print(f"{stop:>8.2f}{'no trades':>9}"); continue
        w = (st.get("win_rate") or 0) / 100.0
        pf = st.get("profit_factor") or 0
        ratio = pf * (1 - w) / w if 0 < w < 1 and pf > 0 else float("nan")
        be = 1 / (1 + ratio) * 100 if ratio == ratio and ratio > 0 else float("nan")
        print(f"{stop:>8.2f}{n:>9,}{w*100:>8.1f}{ratio:>8.2f}{be:>7.1f}"
              f"{st.get('avg_dollars') or 0:>10.2f}{st.get('total_dollars') or 0:>11,.0f}")
finally:
    conn.close(); oc.close()
