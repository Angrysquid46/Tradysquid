"""Phase 11: rules-based self-tuning ("evolve" v1).

This is the gated ceiling described in the original design: bounded,
logged parameter nudges can run unsupervised, but only within hard limits
and only ever a fixed small step at a time - never a big jump, never an
unbounded drift, and never a change made on too little real data.
Anything bigger than a parameter nudge (an actual trading-logic change)
is explicitly out of scope here - that's Phase 12, gated behind owner
review.

The one parameter this bot owns and is actually meant to tune over time
is bankroll.POSITION_SIZE_PCT (see that module's own docstring) - the %
of current balance risked per trade. Every other knob the evolve bot's
real trades touch (entry signal, exit rule, contract selection) is
borrowed directly from spy_scanner's live, already-proven logic, not
something this bot owns or should be nudging independently.

Every real nudge is appended to SELF_TUNING_LOG_PATH below - the exact
same path presentation.py's own SELF_TUNING_LOG_PATH points at (both are
STATE_DIR / "self_tuning_log.jsonl"; duplicated as a plain constant here
rather than imported from presentation.py, since presentation.py imports
weekly_review.py which imports engine.py which imports this module -
importing presentation.py back from here would be circular, and would
also pull matplotlib into every live trading cycle just to read a path).
Phase 10's self-tuning log renderer was built to read this exact file and
has been correctly returning None (nothing to show) until this module
started writing to it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import bankroll
import tradelog

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
TUNING_STATE_PATH = STATE_DIR / "tuning_state.json"
SELF_TUNING_LOG_PATH = STATE_DIR / "self_tuning_log.jsonl"
# Same path engine.py itself uses (STATE_DIR / "trades.csv") - duplicated
# as a plain constant rather than imported from engine.py, since engine.py
# imports this module (to read current_position_size_pct()) and importing
# back would be circular.
LIVE_TRADELOG_PATH = STATE_DIR / "trades.csv"

# A nudge only ever fires with at least this many real closed trades to
# look at - the same threshold as the "10 real closed trades" milestone
# (presentation.compute_milestones), deliberately reused rather than
# picking a new number, since that milestone already marks the point the
# owner agreed real trailing performance starts being meaningful. Below
# this, trailing win rate is closer to a coin flip than a real signal -
# tuning on it would be reacting to noise, not results.
MIN_CLOSED_TRADES_BEFORE_TUNING = 10

# Only the most recent N closed trades inform each decision - trailing,
# not all-time, so the size adapts to how the bot has been doing lately,
# not to a single hot or cold stretch from long ago.
TRAILING_WINDOW = 10

# One fixed step per nudge, in either direction - deliberately small so a
# single evaluation can never swing sizing dramatically. Hard bounds keep
# it from ever drifting to reckless (too high) or pointless (too low)
# regardless of how many nudges accumulate over time.
STEP = 0.02
MIN_POSITION_SIZE_PCT = 0.05
MAX_POSITION_SIZE_PCT = 0.30

# A dead zone around 50% win rate on purpose - without one, a trailing
# win rate that's genuinely just noise around a coin flip would nudge the
# size up and down every single evaluation, thrashing instead of tuning.
WIN_RATE_UP_THRESHOLD = 0.55
WIN_RATE_DOWN_THRESHOLD = 0.45


def _load_state() -> dict[str, Any] | None:
    try:
        return json.loads(TUNING_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TUNING_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_log(entry: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with SELF_TUNING_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def current_position_size_pct() -> float:
    """The live sizing % right now - the last tuned value if one has ever
    been saved, otherwise bankroll's own starting default. Safe to call on
    every trading cycle; this is a cheap read, not the tuning evaluation
    itself."""
    state = _load_state()
    if state is None:
        return bankroll.POSITION_SIZE_PCT
    return float(state.get("position_size_pct", bankroll.POSITION_SIZE_PCT))


def _trailing_win_rate(closed: list[dict[str, str]]) -> tuple[float, int, int]:
    window = closed[-TRAILING_WINDOW:]
    wins = sum(1 for row in window if row.get("outcome") == "WIN")
    return wins / len(window), wins, len(window)


def evaluate_tuning(closed: list[dict[str, str]]) -> dict[str, Any]:
    """The pure core: takes an already-loaded list of closed trade rows
    (no I/O of its own beyond the tuning state/log) so a caller that has
    already loaded the trade log in memory - engine.py, every real cycle -
    can pass it straight in instead of this module re-reading the same
    file from disk a second time. run_tuning_cycle() below is the
    disk-reading convenience wrapper for standalone/CLI use.

    Safe to call on any cadence, or none - same "cheap, idempotent, only
    acts on real change" shape as retrain_loop.run_retrain_cycle.
    Evaluates at most once per newly-closed real trade (tracked via the
    last-considered trade_id, not a hash of the whole file, since a
    closed trade row never changes after it closes - unlike backtest
    rows, which get backfilled in place)."""
    state = _load_state()
    current_pct = (
        float(state["position_size_pct"]) if state and "position_size_pct" in state else bankroll.POSITION_SIZE_PCT
    )
    last_considered_id = state.get("last_considered_trade_id") if state else None
    latest_id = closed[-1]["trade_id"] if closed else None

    if len(closed) < MIN_CLOSED_TRADES_BEFORE_TUNING:
        return {
            "status": "not enough real closed trades yet",
            "n_closed": len(closed),
            "n_needed": MIN_CLOSED_TRADES_BEFORE_TUNING,
            "position_size_pct": current_pct,
        }

    if latest_id == last_considered_id:
        return {"status": "already evaluated this trade history", "position_size_pct": current_pct}

    win_rate, wins, window_size = _trailing_win_rate(closed)
    if win_rate >= WIN_RATE_UP_THRESHOLD:
        new_pct = round(min(MAX_POSITION_SIZE_PCT, current_pct + STEP), 4)
    elif win_rate <= WIN_RATE_DOWN_THRESHOLD:
        new_pct = round(max(MIN_POSITION_SIZE_PCT, current_pct - STEP), 4)
    else:
        new_pct = current_pct

    _save_state({"position_size_pct": new_pct, "last_considered_trade_id": latest_id})

    if new_pct == current_pct:
        return {
            "status": "evaluated, no change",
            "position_size_pct": current_pct,
            "trailing_win_rate": round(win_rate, 4),
            "trailing_window": window_size,
        }

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    direction = "up" if new_pct > current_pct else "down"
    threshold = WIN_RATE_UP_THRESHOLD if direction == "up" else WIN_RATE_DOWN_THRESHOLD
    reasoning = (
        f"trailing {window_size}-trade win rate {win_rate * 100:.0f}% ({wins}/{window_size}) "
        f"crossed the {direction}-threshold ({threshold * 100:.0f}%)"
    )
    _append_log(
        {
            "timestamp": timestamp,
            "change": f"position_size_pct {current_pct} -> {new_pct}",
            "reasoning": reasoning,
        }
    )
    return {
        "status": "tuned",
        "position_size_pct": new_pct,
        "previous_position_size_pct": current_pct,
        "trailing_win_rate": round(win_rate, 4),
        "trailing_window": window_size,
    }


def run_tuning_cycle() -> dict[str, Any]:
    """Standalone/CLI convenience wrapper - reads the real live trade log
    from disk itself. engine.py's own trading cycle calls evaluate_tuning()
    directly with its already-loaded rows instead of using this."""
    rows = tradelog.read_log(LIVE_TRADELOG_PATH)
    return evaluate_tuning(tradelog.closed_rows(rows))


if __name__ == "__main__":
    print(json.dumps(run_tuning_cycle(), indent=2))
