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

    lines += [
        "",
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
        "",
        "## Things that are NOT live (do not resurrect)",
        "",
        "- The 10 ratchet variants - retired; ten channels off one signal.",
        "- `SPY_0DTE_1M` / `SPY_0DTE_5M`, `SPY_GAP_CONT_25`, `SPY_GAP_CONT_100`, "
        "`SPY_SWEEP_5` - retired play types. Closed rows survive in the trade "
        "log and are filtered out of all reporting.",
        "- `SPY_EXPANSION_LEVEL` - disabled.",
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
