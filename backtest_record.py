"""Write the current backtest + live record to one readable file.

So a later session can learn how every strategy is actually doing by
reading ONE file - no Discord fetch, and above all no re-running a
backtest, which costs about 40 minutes a pass. The Discord cards are for
the owner; this is the same information in a form that is cheap to read.

Refreshed by the `backtest-cards` job, so it is never more than a few
hours stale. The drift section is the useful part: a strategy whose LIVE
win rate has fallen below its OWN break-even is failing, and that is
invisible if you only look at total P/L.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

RECORD_PATH = Path("state/strategy_live_record.md")


def build(results: dict[str, Any], forward: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Strategy Record (backtest + live forward)",
        "",
        f"Refreshed {datetime.now().isoformat(timespec='seconds')} by the "
        "`backtest-cards` job. **Read this instead of re-running a backtest** "
        "- a full option pass is about 40 minutes.",
        "",
        "Backtest: each strategy under its OWN exit, one contract, "
        "$0.04/contract, modelled option prices across 988 sessions that had "
        "a same-day expiry. Live: real fills since the cards went up.",
        "",
        "| Strategy | Exit | BT trades | BT win% | Break-even | BT $/trade "
        "| Live trades | Live win% | Live $/trade |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for play in sorted(results):
        stats = results[play]
        fwd = forward.get(play) or {"trades": 0}
        be = stats.get("breakeven_win_rate")
        n = fwd.get("trades") or 0

        be_text = f"{be:.1f}%" if be else "-"
        live_win = f"{fwd['win_rate']:.1f}%" if n else "-"
        live_avg = f"{fwd['avg_dollars']:+.2f}" if n else "-"

        lines.append(
            f"| {play} | {stats.get('exit_label', '-')} "
            f"| {stats.get('trades', 0):,} "
            f"| {stats.get('win_rate', 0):.1f}% "
            f"| {be_text} "
            f"| {stats.get('avg_dollars', 0):+.2f} "
            f"| {n} | {live_win} | {live_avg} |"
        )

    drifting = []
    for play, stats in results.items():
        fwd = forward.get(play) or {}
        be = stats.get("breakeven_win_rate")
        if (fwd.get("trades") or 0) >= 20 and be and fwd["win_rate"] < be:
            drifting.append(
                f"{play} (live {fwd['win_rate']:.1f}% vs break-even {be:.1f}%)"
            )

    lines += [
        "",
        "## Watch",
        "",
        "Strategies whose LIVE win rate has dropped below their OWN "
        "break-even, with 20+ live trades:",
        "",
    ]
    lines.append("- " + ("\n- ".join(drifting) if drifting else "none"))
    lines += [
        "",
        "A strategy is profitable exactly when its win rate clears its own "
        "break-even, which is set by its exit's payoff ratio. Total P/L hides "
        "this; a high-frequency strategy just below the line bleeds quietly.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write(results: dict[str, Any], forward: dict[str, dict[str, Any]]) -> Path:
    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORD_PATH.write_text(build(results, forward), encoding="utf-8")
    return RECORD_PATH
