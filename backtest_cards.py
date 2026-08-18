"""One self-updating Discord card per strategy, showing its backtest
record and then tracking forward against live results.

Deliberately separate from the performance reporting. Daily/weekly/monthly
still cover only the 15 live strategies and are unaffected by anything
here - these cards are a research surface, not a P/L statement.

What each card carries:

* the strategy's OWN exit rules, since measuring them all under one
  borrowed shape is what produced a whole evening of wrong conclusions;
* the backtest record at those settings - trades, win rate, payoff,
  break-even win rate, dollars per trade;
* the live forward record accumulated since the card was created, so the
  backtest claim is continuously checked against reality rather than
  quoted forever.

The gap between the two is the point. A strategy whose forward win rate
drifts below its break-even line is failing in public rather than
quietly.

Everything here is modelled option pricing over 988 sessions that had a
same-day expiry, so the backtest half is evidence and not proof. The
forward half is real fills.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULTS_PATH = Path("state/backtest_cards.json")
CHANNEL_KEY = "backtest_results"


def load_results() -> dict[str, Any]:
    if not RESULTS_PATH.exists():
        return {}
    try:
        loaded = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_results(results: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, sort_keys=True,
                                       default=str), encoding="utf-8")


def _verdict(win_rate: float, breakeven: float) -> str:
    if breakeven != breakeven:
        return "unknown"
    margin = win_rate - breakeven
    if margin >= 5:
        return f"CLEAR (+{margin:.1f}pp over break-even)"
    if margin > 0:
        return f"THIN (+{margin:.1f}pp over break-even)"
    return f"BELOW break-even by {abs(margin):.1f}pp"


def forward_record(rows: list[dict[str, str]], play_type: str) -> dict[str, Any]:
    """Closed live trades for this strategy, since the card went up."""
    closed = [r for r in rows
              if r.get("play_type") == play_type
              and (r.get("outcome") or "").upper() not in ("", "OPEN")]
    if not closed:
        return {"trades": 0}
    wins = 0
    total = 0.0
    for row in closed:
        try:
            pnl = float(str(row.get("pnl_dollars") or row.get("pnl") or 0) or 0)
        except (TypeError, ValueError):
            pnl = 0.0
        total += pnl
        if pnl > 0:
            wins += 1
    n = len(closed)
    return {"trades": n, "win_rate": wins / n * 100.0,
            "total_dollars": total, "avg_dollars": total / n}


def render_card(play_type: str, stats: dict[str, Any],
                forward: dict[str, Any] | None = None) -> str:
    """Markdown that spy_scanner.discord_card turns into an embed."""
    target = stats.get("target_pct")
    stop = stats.get("stop_pct")
    exit_label = stats.get("exit_label") or (
        f"{target:+.0f}% / {stop:+.0f}% of premium"
        if target is not None and stop is not None else "see strategy")

    n = stats.get("trades") or 0
    win = stats.get("win_rate") or 0.0
    ratio = stats.get("payoff_ratio")
    be = stats.get("breakeven_win_rate")
    avg = stats.get("avg_dollars") or 0.0
    total = stats.get("total_dollars") or 0.0

    lines = [f"## {play_type}", "", "### Exit rules", f"**{exit_label}**", ""]
    if stats.get("exit_note"):
        lines += [stats["exit_note"], ""]

    lines += ["### Backtest record",
              f"**{n:,} trades** · win rate **{win:.1f}%**"]
    if ratio is not None and ratio == ratio:
        lines.append(f"Payoff **{ratio:.2f}:1** · break-even win rate "
                     f"**{be:.1f}%**")
        lines.append(f"Verdict: **{_verdict(win, be)}**")
    lines += [f"Per trade **{avg:+.2f}** · total **{total:+,.0f}**", ""]

    lines += ["### Live forward record"]
    if forward and forward.get("trades"):
        fw_n = forward["trades"]
        fw_win = forward.get("win_rate") or 0.0
        drift = fw_win - win
        lines += [f"**{fw_n:,} trades** · win rate **{fw_win:.1f}%** "
                  f"({drift:+.1f}pp vs backtest)",
                  f"Per trade **{forward.get('avg_dollars', 0):+.2f}** · "
                  f"total **{forward.get('total_dollars', 0):+,.0f}**"]
        if be is not None and be == be and fw_win < be:
            lines.append("**Forward win rate is below this strategy's "
                         "break-even line.**")
    else:
        lines.append("No closed live trades yet. Populates as this strategy "
                     "trades forward.")

    lines += ["", "### Reading this",
              "Backtest option prices are modelled across 988 sessions that "
              "had a same-day expiry, so treat that half as evidence rather "
              "than proof. The forward half is real fills. Sizing is one "
              "contract, matching live.",
              "",
              "*Research surface only. Daily, weekly and monthly performance "
              "cover the 15 live strategies and are not affected by this "
              "channel.*"]
    return "\n".join(lines)


def card_key(play_type: str) -> str:
    return f"backtest-card:{play_type}"
