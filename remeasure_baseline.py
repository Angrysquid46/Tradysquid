"""Re-measure all 15 strategies with volatility that is not broken.

The BASELINE in `state/backtest_cards.json` - and therefore the card each
strategy shows in `#backtest-results` - was produced by an option layer
that read implied volatility from `eod_chain`. That table is an end-of-day
snapshot, so for a same-day expiry it is a snapshot AT EXPIRY, and the IV
solved on a contract with no life left collapses toward zero. 480 of 988
sessions priced under 3% volatility, mean 0.044.

At 4% vol a SPY at-the-money 0DTE prices near 28 cents. The real contract
is $1.26 to $1.63. So every strategy was scored buying a $145 option for
$28, and a +115% target it needs a real move to reach was being cleared by
SPY moving a few cents. Measured on the same 506 sessions, one strategy at
a time, only the IV changed:

    SPY_CONFLUENCE_4   old  1,675 trades  entry $0.28  win 43.0%  +$4.94
    SPY_CONFLUENCE_4   new    439 trades  entry $1.45  win 21.9%  -$50.44

The 43% win rate against a 39.5% break-even looked exactly like a real,
thin edge. It was the option being cheap.

This rewrites the baseline with:

- volatility from `option_session_inputs`, which uses a measured intraday
  capture where one exists and VIX otherwise, never `eod_chain`
- each strategy under its OWN exit out of `NEW_STRATEGY_EXITS`
- `SPY_KEY_LEVELS` on its underlying stop/target, since it does not exit
  on premium at all

and records the provenance split in the file, so a future reader can see
what the numbers rest on instead of having to rediscover it.

Run:  ./.venv-tradysquid/Scripts/python.exe remeasure_baseline.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import backtest_cards as bc
import backtest_lab as lab
import spy_backtest as bt
import spy_backtest_live_strategies as blive
import spy_intraday_features as sif
import spy_live_new_strategies as lns
import spy_option_backtest as ob

KEY_LEVELS = "SPY_KEY_LEVELS"


def build_ideas() -> tuple[list[lab.Idea], dict[str, ob.OptionExit]]:
    conn = bt.connect()
    try:
        sma = blive.daily_sma200(sif.all_session_ohlc(conn))
    finally:
        conn.close()

    ideas: list[lab.Idea] = []
    shapes: dict[str, ob.OptionExit] = {}
    for spec in lns.NEW_STRATEGY_SPECS:
        play = spec["play_type"]
        target, stop, time_stop = lns.NEW_STRATEGY_EXITS[play]
        shapes[play] = ob.OptionExit(
            target_pct=target, stop_pct=stop, floor_trigger_pct=None,
            floor_pct=None, time_stop_minutes=time_stop)
        ideas.append(lab.Idea(play, spec["signal"], lab.premium_exit(shapes[play])))

    shapes[KEY_LEVELS] = ob.OptionExit(
        target_pct=None, stop_pct=None, floor_trigger_pct=None, floor_pct=None,
        underlying_stop_pct=0.15, underlying_r_multiple=2.0)
    ideas.append(lab.Idea(KEY_LEVELS, blive.live_key_levels(sma),
                          lab.premium_exit(shapes[KEY_LEVELS])))
    return ideas, shapes


def _exit_label(play: str, shape: ob.OptionExit) -> str:
    if play == KEY_LEVELS:
        return "Underlying stop 0.15% / target 2.0R"
    label = f"Target {shape.target_pct:+.0f}% / stop {shape.stop_pct:+.0f}% of premium"
    if shape.time_stop_minutes:
        label += f", time stop {shape.time_stop_minutes}min"
    return label


def card_stats(result: lab.Result, play: str, shape: ob.OptionExit) -> dict:
    """The schema backtest_cards.render_card reads."""
    win = result.win_rate / 100.0
    factor = result.profit_factor
    # payoff = average win / average loss, recovered from profit factor.
    payoff = (factor * (1 - win) / win) if 0 < win < 1 and factor not in (0, float("inf")) else float("nan")
    breakeven = (1 / (1 + payoff) * 100) if payoff == payoff and payoff > 0 else float("nan")
    return {
        "trades": result.trades,
        "win_rate": result.win_rate,
        "avg_dollars": result.avg_dollars,
        "total_dollars": result.total_dollars,
        "payoff_ratio": payoff,
        "breakeven_win_rate": breakeven,
        "target_pct": shape.target_pct,
        "stop_pct": shape.stop_pct,
        "exit_label": _exit_label(play, shape),
        "exit_note": (
            "Exits on the UNDERLYING, not on option premium. P/L is still "
            "marked off the option, which is the realised money."
            if play == KEY_LEVELS else None),
    }


def main() -> None:
    ideas, shapes = build_ideas()
    print(f"re-measuring {len(ideas)} strategies under their own exits...",
          flush=True)
    results, coverage = lab.measure(ideas, progress_every=250)

    payload = {}
    for result in results:
        payload[result.label] = card_stats(result, result.label,
                                           shapes[result.label])

    payload["_measurement"] = {
        "measured_on": date.today().isoformat(),
        "sessions_scored": coverage.sessions_scored,
        "first_session": coverage.first_session,
        "last_session": coverage.last_session,
        "sessions_with_measured_iv": coverage.measured_sessions,
        "sessions_on_vix_proxy": coverage.proxy_sessions,
        "note": (
            "Volatility comes from option_session_inputs: a measured "
            "intraday capture where one exists, VIX otherwise. eod_chain is "
            "NOT used - its 0DTE rows are end-of-day snapshots taken at "
            "expiry and priced 480 of 988 sessions under 3% vol, which is "
            "what made the previous baseline read all-positive."),
    }

    bc.RESULTS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8")

    print(f"\nsessions {coverage.sessions_scored:,}  "
          f"{coverage.first_session} to {coverage.last_session}  "
          f"(measured IV {coverage.measured_sessions:,}, "
          f"proxy {coverage.proxy_sessions:,})\n")
    print(f"{'strategy':<24}{'n':>7}{'win%':>7}{'BE%':>7}{'$/trade':>9}{'total':>11}")
    print("-" * 65)
    for result in sorted(results, key=lambda r: -r.avg_dollars):
        stats = payload[result.label]
        be = stats["breakeven_win_rate"]
        print(f"{result.label:<24}{result.trades:>7,}{result.win_rate:>6.1f}%"
              f"{be:>6.1f}%" if be == be else
              f"{result.label:<24}{result.trades:>7,}{result.win_rate:>6.1f}%"
              f"{'-':>7}", end="")
        print(f"{result.avg_dollars:>+9.2f}{result.total_dollars:>+11,.0f}")
    print(f"\nwrote {bc.RESULTS_PATH}")


if __name__ == "__main__":
    main()
