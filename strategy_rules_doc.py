"""Generate docs/STRATEGY_RULES.md from the live registry.

This exists because the strategy rules kept getting rediscovered from
scratch - which exit each one uses, which signal, which channel, whether
it is enabled - and every rediscovery cost time and produced at least one
wrong answer. Worse, several conclusions were drawn from settings that
were no longer live: strategies measured under a borrowed +50/-50 exit
none of them use, and two measured at ATR thresholds they had been
recalibrated away from.

The document is GENERATED, never hand-written, and a test asserts it
matches the code. So it cannot drift: change a strategy and the test
fails until the doc is regenerated. A hand-maintained list would have
gone stale the first time a threshold moved, which is exactly the failure
this is meant to stop.

Regenerate with:  python strategy_rules_doc.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOC_PATH = Path("docs/STRATEGY_RULES.md")
MEASURED_PATH = Path("state/backtest_cards.json")


# What each strategy actually TRADES, in plain words. Taken from the
# strategy implementations, not invented - a numbers table does not tell
# you what a play IS, and confusing two similar-sounding ones is how a
# wrong exit gets attached to the wrong idea.
PLAY_STYLES = {
    "SPY_GAP_CONT_50":
        "Gap continuation. SPY gaps at least 0.5% at the open; trade in the "
        "direction of the gap, betting the move keeps going rather than fills.",
    "SPY_FAILED_BREAK":
        "Failed breakout reversal. Price breaks a prior-day level, fails to "
        "hold it, and reverses back through - trade the reversal, not the break.",
    "SPY_ORB_IMMEDIATE":
        "Opening-range breakout taken on the breakout bar ITSELF, not on a "
        "retest. Fires once per session per direction. Needs relative volume "
        "at or above 1.0, so it will not chase a quiet break.",
    "SPY_SWEEP_10":
        "Liquidity sweep. A stricter failed breakout: price must poke through "
        "the level and reclaim it QUICKLY - within 10 bars. A slow grind back "
        "is acceptance, not a sweep, and that distinction is the whole idea.",
    "SPY_VWAP_RECLAIM":
        "Lose VWAP, reclaim it, hold the retest, then break the pullback high. "
        "A chop filter rejects the setup once SPY has crossed VWAP too many "
        "times that session, since repeated crosses mean no one is in control.",
    "SPY_MOMENTUM_ADX25":
        "Momentum, small consolidation, then the continuation break - "
        "deliberately NOT the largest candle. Requires ADX at or above 25 so "
        "it only trades when a trend is actually established.",
    "SPY_TOD_MIDDAY":
        "The same momentum rule as ADX25, restricted to the midday session. "
        "SPY does not behave identically all day; this holds the rule fixed "
        "and varies only the clock.",
    "SPY_CONFLUENCE_4":
        "Four or more independent references stacked at one price, THEN "
        "confirmation. Touching four levels is explicitly not itself a trade - "
        "the confirming break is required.",
    "SPY_TOD_FINAL30":
        "The momentum rule restricted to the final 30 minutes. Its 30-minute "
        "time stop is redundant in practice: the closing bell always arrives "
        "first.",
    "SPY_MTF_4OF4":
        "Breakout requiring all four tracked timeframes to agree. The strictest "
        "of the multi-timeframe variants - 2-of-4 and 3-of-4 also exist and "
        "were not promoted.",
    "SPY_EXHAUSTION_1ATR":
        "Momentum exhaustion. Price stretches far from VWAP, market structure "
        "turns against it, and the bar closes through the prior bar's extreme - "
        "fade the overextension. A reversal snap: if it has not snapped back "
        "within 30 minutes the thesis was wrong, which is what the time stop "
        "enforces.",
    "SPY_FIRST_PULLBACK":
        "Strong drive off the open, then the FIRST controlled pullback - "
        "explicitly not chasing the drive itself. Takes one trade per session.",
    "SPY_OPENING_GAP_FADE":
        "Fade the opening gap, strictly between 09:45 and 10:00. Needs a gap "
        "of 0.4% or more, a volume z-score above 1.5, momentum already flipped "
        "against the gap, and the bar closing at the extreme of its own range. "
        "Rare by construction.",
    "SPY_KEY_LEVELS":
        "Price trading at a key level - prior-day, premarket, opening-range or "
        "VWAP - with 1/3/5-minute direction agreeing, plus its own economic "
        "catalyst check. The only strategy that exits on the UNDERLYING "
        "(stop at the level, target at 2R) rather than on option premium.",
    "SPY_COMPRESSION_3BAR":
        "Quiet range, then a bar that expands out of it. Three bars of "
        "compression is the trigger; the 5- and 10-bar variants exist and were "
        "not promoted because their samples are 21 and 1 trade.",
}


def _measured() -> dict[str, Any]:
    if not MEASURED_PATH.exists():
        return {}
    try:
        loaded = json.loads(MEASURED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def build() -> str:
    import spy_live_new_strategies as lns
    import spy_scanner as scanner

    enabled = scanner.trade_types_enabled()
    measured = _measured()

    lines = [
        "# Live Strategy Rules",
        "",
        "**Generated from the code by `strategy_rules_doc.py` - do not edit by "
        "hand.** `test_strategy_rules_doc.py` fails if this drifts from the "
        "registry, so a strategy cannot change its rules without this changing "
        "too.",
        "",
        "Why it exists: these rules were repeatedly re-derived from scratch, and "
        "several measurements were taken against settings that were no longer "
        "live - a shared exit none of the strategies use, and ATR thresholds two "
        "of them had been recalibrated away from. Read this first.",
        "",
        "## The roster",
        "",
        "| # | Strategy | Signal | Exit (option premium) | Max signal age | Channel | Live |",
        "|---|---|---|---|---|---|---|",
    ]

    specs = {s["play_type"]: s for s in lns.NEW_STRATEGY_SPECS}
    for entry in sorted(lns.CHANNEL_ROSTER, key=lambda e: e["rank"]):
        play = entry["play_type"]
        spec = specs.get(play)
        if play == scanner.SPY_KEY_LEVELS_PLAY_TYPE:
            exit_text = (f"**underlying** stop "
                         f"{scanner.SPY_KEY_LEVELS_STOP_BUFFER_PCT}% / target "
                         f"{scanner.SPY_KEY_LEVELS_TARGET_R_MULTIPLE}R")
            signal_text = "live level/VWAP/ORB read in `spy_scanner`"
            flag = "spy_key_levels"
            age = "n/a (state, not a bar event)"
        else:
            target, stop, time_stop = lns.NEW_STRATEGY_EXITS[play]
            exit_text = f"{target:+.0f}% / {stop:+.0f}%"
            if time_stop:
                exit_text += f", {time_stop}min"
            signal_text = f"`{spec['signal'].__qualname__.split('.')[0]}`" if spec else "-"
            flag = lns.config_flag(play)
            age = f"{lns.max_signal_age(play)} bar(s)"
        lines.append(
            f"| {entry['rank']} | **{play}** | {signal_text} | {exit_text} | "
            f"{age} | `{lns.channel_slug(play)}` | "
            f"{'yes' if enabled.get(flag) else '**NO**'} |"
        )

    lines += ["", "## What each strategy trades", ""]
    for entry in sorted(lns.CHANNEL_ROSTER, key=lambda e: e["rank"]):
        play = entry["play_type"]
        lines.append(f"**{play}** - {PLAY_STYLES.get(play, 'UNDOCUMENTED')}")
        lines.append("")

    lines += [
        "## Measured performance",
        "",
        "Each strategy under **its own** exit rules, one contract, "
        "$0.04/contract commission. Break-even win rate is set by the exit's "
        "payoff ratio - a strategy is profitable exactly when its win rate "
        "clears it.",
        "",
        "| Strategy | Trades | Win% | Break-even | $/trade |",
        "|---|---|---|---|---|",
    ]
    for entry in sorted(lns.CHANNEL_ROSTER, key=lambda e: e["rank"]):
        play = entry["play_type"]
        stats = measured.get(play)
        if not stats:
            lines.append(f"| {play} | - | - | - | not measured |")
            continue
        be = stats.get("breakeven_win_rate")
        lines.append(
            f"| {play} | {stats.get('trades', 0):,} | "
            f"{stats.get('win_rate', 0):.1f}% | "
            f"{be:.1f}%" .format(be=be) if be else f"| {play} | "
            f"{stats.get('trades', 0):,} | {stats.get('win_rate', 0):.1f}% | - |"
        )
    # rebuild that table cleanly rather than risk a malformed row
    lines = lines[:lines.index("|---|---|---|---|---|") + 1]
    for entry in sorted(lns.CHANNEL_ROSTER, key=lambda e: e["rank"]):
        play = entry["play_type"]
        stats = measured.get(play)
        if not stats:
            lines.append(f"| {play} | - | - | - | not measured |")
            continue
        be = stats.get("breakeven_win_rate")
        lines.append(
            f"| {play} | {stats.get('trades', 0):,} | "
            f"{stats.get('win_rate', 0):.1f}% | "
            f"{(f'{be:.1f}%' if be else '-')} | "
            f"{stats.get('avg_dollars', 0):+.2f} |"
        )

    lines += [
        "",
        "## Rules that apply to every strategy",
        "",
        "- **One position at a time.** A strategy holding a trade is skipped "
        "entirely by the entry scan until it closes.",
        "- **One contract per trade**, so risk is `ask x 100` - between about "
        "$1 and $500, never more. The backtest sizes the same way.",
        "- **Scanned every minute** during market hours, with a per-strategy "
        "lookback so a signal is still caught when a cycle runs late. "
        "Capture is 100%.",
        "- **`POSITION_FILE_LOCK` is never held across network I/O**, so entry "
        "scanning cannot delay an exit.",
        "- **Each strategy has its own channel, its own ledger and its own "
        "backtest card.** Nothing shares an exit or a signal.",
        "## Known limits",
        "",
        "- **Premarket-based strategies cannot work**: `premarket_high/low/range` "
        "are 0% populated on recent sessions and the live feature builder never "
        "constructs them. S5 Premarket Breakout scored well and was rejected for "
        "this reason.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(build(), encoding="utf-8")
    print(f"wrote {DOC_PATH}")


if __name__ == "__main__":
    main()
