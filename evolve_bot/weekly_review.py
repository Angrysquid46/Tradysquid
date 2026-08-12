"""Phase 9: weekly review data gathering.

This module only ASSEMBLES the real numbers from all four of the evolve
bot's data sources - it deliberately does NOT write the narrative
assessment itself. A real review is "genuine reasoning grounded in what
actually drove the decision, not a template" (the owner's own words,
first said about per-trade theses, equally true at the portfolio level)
- that kind of synthesis is a job for an LLM reading real numbers fresh
each time, not a fixed Python f-string mechanically filling in blanks.
This module's job is making sure whoever writes that narrative is
working from real, correctly-computed numbers, not guesses.

Scheduling caveat (not this module's concern, but worth recording where
the code lives): there is no durable "run this every week forever"
mechanism available in this environment - CronCreate jobs are session-
only and auto-expire after 7 days regardless. A real weekly cadence needs
either a manual ask each time, or a new OS-level scheduled task (a real
infrastructure decision, not something to add unilaterally given the
live system's own supervisor scheduling is explicitly frozen per
CLAUDE.md).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import backtest
import bankroll
import engine
import retrain_loop
import shadow


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _closed_trade_stats(rows: list[dict[str, str]], pl_key: str = "pl_pct") -> dict[str, Any]:
    """WIN/LOSS/SCRATCH rows only - OPEN rows have no outcome to
    summarize yet. Returns None for rates/averages when there's nothing
    closed, rather than a fabricated 0 that would look like a real
    (bad) result."""
    closed = [r for r in rows if r.get("outcome") in ("WIN", "LOSS", "SCRATCH")]
    wins = [r for r in closed if r["outcome"] == "WIN"]
    losses = [r for r in closed if r["outcome"] == "LOSS"]
    pl_values = [float(r[pl_key]) for r in closed if r.get(pl_key)]
    return {
        "n_closed": len(closed),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_scratch": len(closed) - len(wins) - len(losses),
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "avg_pl_pct": round(sum(pl_values) / len(pl_values), 2) if pl_values else None,
    }


def _shadow_score_calibration(shadow_rows: list[dict[str, str]]) -> dict[str, Any]:
    """The one question shadow mode (Phase 6) exists to answer: do higher
    model scores actually track more real wins? Compares the mean
    model_score on closed shadow WINs vs closed shadow LOSSes - if the
    model has any real skill, WINs should average a higher score than
    LOSSes. Returns None fields when there aren't enough closed shadow
    trades on both sides to compare (a single data point either way isn't
    a real comparison, and pretending it is would be dishonest)."""
    closed = [r for r in shadow_rows if r.get("outcome") in ("WIN", "LOSS") and r.get("model_score")]
    win_scores = [float(r["model_score"]) for r in closed if r["outcome"] == "WIN"]
    loss_scores = [float(r["model_score"]) for r in closed if r["outcome"] == "LOSS"]
    return {
        "n_closed_with_score": len(closed),
        "n_wins_scored": len(win_scores),
        "n_losses_scored": len(loss_scores),
        "avg_score_on_wins": round(sum(win_scores) / len(win_scores), 4) if win_scores else None,
        "avg_score_on_losses": round(sum(loss_scores) / len(loss_scores), 4) if loss_scores else None,
        "enough_data_to_compare": bool(win_scores and loss_scores),
    }


def gather_review_data() -> dict[str, Any]:
    live_rows = _read_csv(engine.TRADELOG_PATH)
    shadow_rows = _read_csv(shadow.SHADOW_LOG_PATH)
    backtest_rows = _read_csv(backtest.BACKTEST_TRADES_PATH)
    retrain_history = _read_jsonl(retrain_loop.RETRAIN_HISTORY_PATH)
    bank = bankroll.load_state(engine.BANKROLL_PATH)

    return {
        "live_trading": {
            "bankroll": {
                "balance": bank["balance"],
                "starting_balance": bank["starting_balance"],
                "peak_balance": bank["peak_balance"],
                "all_time_high_balance": bank["all_time_high_balance"],
                "run_number": bank["run_number"],
                "total_resets": bank["total_resets"],
            },
            "n_open": len(engine.tradelog.open_rows(live_rows)),
            **_closed_trade_stats(live_rows, pl_key="pl_pct"),
        },
        "shadow_mode": {
            "n_total_logged": len(shadow_rows),
            "n_open": len(shadow.open_rows(shadow_rows)),
            **_closed_trade_stats(shadow_rows, pl_key="pl_pct"),
            "score_calibration": _shadow_score_calibration(shadow_rows),
        },
        "backtest_training_data": {
            "n_rows": len(backtest_rows),
            "n_trading_days": len({r["trading_day"] for r in backtest_rows if r.get("trading_day")}),
            "n_real_priced_rows": len([r for r in backtest_rows if r.get("price_source_at_entry") == "real"]),
        },
        "retraining": {
            "n_retrains_recorded": len(retrain_history),
            "most_recent": retrain_history[-1] if retrain_history else None,
        },
    }


if __name__ == "__main__":
    print(json.dumps(gather_review_data(), indent=2))
