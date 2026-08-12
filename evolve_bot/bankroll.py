"""Simulated bankroll for the evolve bot - starts at STARTING_BALANCE,
position sizing scales with the *current* balance (not a fixed dollar cap
like the other strategies use), and auto-resets to STARTING_BALANCE if it
gets blown down to the floor. Each reset starts a new numbered "run" so
history isn't lost, only the active balance resets.

Deliberately its own tiny module with no dependency on spy_scanner or
anything else in this repo - the bankroll is pure arithmetic and file I/O,
easy to reason about and test in complete isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STARTING_BALANCE = 1000.0

# % of the *current* balance risked per trade - deliberately more aggressive
# than the other strategies' fixed $500/trade cap, since this bot is meant
# to size up as it wins and down as it loses. This is a starting default,
# not a permanent constant - Phase 11 (rules-based self-tuning) is meant to
# adjust this over time based on trailing results.
POSITION_SIZE_PCT = 0.15

# Balance at or below this triggers a reset. Not exactly zero - a few
# dollars left over isn't enough to realistically buy even one 0DTE
# contract, so treat "can't trade anymore" as "blown up" rather than
# waiting for a literal $0.00.
RESET_FLOOR = 25.0


def default_state() -> dict[str, Any]:
    return {
        "run_number": 1,
        "balance": STARTING_BALANCE,
        "starting_balance": STARTING_BALANCE,
        "peak_balance": STARTING_BALANCE,
        "all_time_high_balance": STARTING_BALANCE,
        "all_time_high_run": 1,
        "total_resets": 0,
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_state()
    merged = default_state()
    merged.update(state)
    return merged


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(path)


def position_size_dollars(state: dict[str, Any]) -> float:
    """How much to risk on the next trade - a % of the balance right now,
    not a fixed cap, so it compounds on wins and shrinks on losses."""
    return round(state["balance"] * POSITION_SIZE_PCT, 2)


def contracts_affordable(position_size: float, premium_per_contract: float) -> int:
    """Whole contracts only - options trade in 100-share lots, so a
    fractional contract isn't a real order. 0 means the position size
    can't afford even one contract at this premium; the caller should skip
    the trade rather than round up into an oversized position."""
    if premium_per_contract <= 0:
        return 0
    cost_per_contract = premium_per_contract * 100
    return int(position_size // cost_per_contract)


def debit_entry(state: dict[str, Any], cost_dollars: float) -> dict[str, Any]:
    """Cash leaves the account the moment a position opens, same as a real
    brokerage - not deferred until close. This matters once more than one
    position can be open at a time: without debiting at entry, sizing a
    second concurrent trade off the still-undiminished balance would let
    the bot allocate the same capital twice. contracts_affordable() always
    sizes within the balance available at call time, so this should never
    push the balance negative - guarded anyway rather than assumed."""
    state = dict(state)
    state["balance"] = round(max(state["balance"] - cost_dollars, 0.0), 2)
    return state


def credit_exit(state: dict[str, Any], proceeds_dollars: float) -> dict[str, Any]:
    """Cash returns when a position closes. This is where a realized loss
    actually crystallizes, so the reset-on-blowup check belongs here, not
    at entry - tracks the peak/all-time-high first, then resets to
    STARTING_BALANCE (starting a new numbered run) if the balance has been
    blown down to the floor. Returns the updated state; does not write it
    to disk - call save_state separately so the caller controls when a
    write actually happens."""
    state = dict(state)
    state["balance"] = round(state["balance"] + proceeds_dollars, 2)
    state["peak_balance"] = max(state["peak_balance"], state["balance"])
    if state["balance"] > state["all_time_high_balance"]:
        state["all_time_high_balance"] = state["balance"]
        state["all_time_high_run"] = state["run_number"]
    if state["balance"] <= RESET_FLOOR:
        state["total_resets"] += 1
        state["run_number"] += 1
        state["balance"] = STARTING_BALANCE
        state["peak_balance"] = STARTING_BALANCE
    return state
