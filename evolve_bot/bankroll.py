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
# adjust this over time based on trailing results. Raised from 0.15 to
# 0.25 on 2026-08-12 (owner: "it should be trading aggressively") - still
# bounded by self_tuning.MIN/MAX_POSITION_SIZE_PCT, still paper money with
# a real auto-reset safety net below, not an unbounded change.
POSITION_SIZE_PCT = 0.25

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


def position_size_dollars(state: dict[str, Any], position_size_pct: float = POSITION_SIZE_PCT) -> float:
    """How much to risk on the next trade - a % of the balance right now,
    not a fixed cap, so it compounds on wins and shrinks on losses.
    position_size_pct defaults to the module constant but is overridable
    so self_tuning.py's bounded, logged nudges (Phase 11) can move it over
    time without this module needing to know self_tuning.py exists -
    bankroll.py stays dependency-free, per its own module docstring."""
    return round(state["balance"] * position_size_pct, 2)


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

def blown_out(state: dict[str, Any], premium_per_contract: float) -> bool:
    """True when the ACCOUNT cannot fund a single contract.

    Judges the BALANCE, not the position size. That distinction is the
    whole bug: this used to ask whether `position_size` could fund a
    contract, and a 5% size on a healthy $1,000 balance is $50 against
    0DTE contracts costing $109-$177. So a brand-new run at full starting
    balance declared itself bankrupt on its first candidate, reset to
    $1,000, and did it again - 10 times on 2026-08-20 alone, with no trade
    taken since 2026-08-14. Every reset logged "blown out" while the
    account was untouched at $1,000.

    Being unable to afford a contract at 5% of a full bankroll is a SIZING
    problem, not bankruptcy. Bankruptcy is when the money is gone.
    """
    if premium_per_contract <= 0:
        return False
    return state["balance"] < premium_per_contract * 100


def contracts_for_trade(state: dict[str, Any], risk_budget: float,
                        premium_per_contract: float,
                        stop_pct: float = 1.0) -> int:
    """How many contracts to buy, sized by RISK rather than by notional.

    The old rule sized by notional: 5% of the balance was the most that
    could be spent, so a $1,000 account could spend $50 - against SPY 0DTE
    contracts that cost $40 to $500. Owner, correctly: "why limit it to 5%
    ... when options will range from 40 to 500 dollars." At that size the
    bot could not buy anything and froze for six days.

    5% of the account is a sensible thing to RISK. It is not a sensible
    thing to spend, because a long option's loss is bounded by the stop,
    not by what it cost. With the active -20% stop, a $177 contract puts
    $35 at risk - 3.5% of a $1,000 account. Spending $177 and risking $177
    are only the same thing if the stop never fires.

    So: risk_budget is the most this trade may LOSE, and the number of
    contracts is whatever keeps the stop-loss inside it.

    An option is indivisible, so when the budget lands between zero and one
    contract the answer is one contract as long as the ACCOUNT can fund it -
    the alternative is never trading, which is the state this replaces.
    Returns 0 only when the balance genuinely cannot buy a single contract.
    """
    if premium_per_contract <= 0:
        return 0
    if blown_out(state, premium_per_contract):
        return 0
    cost_per_contract = premium_per_contract * 100
    loss_per_contract = cost_per_contract * max(min(stop_pct, 1.0), 0.01)
    affordable_by_balance = int(state["balance"] // cost_per_contract)
    by_risk = int(risk_budget // loss_per_contract)
    return max(min(by_risk, affordable_by_balance), 1)


def start_new_run(state: dict[str, Any]) -> dict[str, Any]:
    """End the current run and begin the next one at STARTING_BALANCE.

    Same accounting as the reset inside credit_exit, extracted so a run can
    also be ended by being unable to trade rather than only by drawing down
    to the floor. Closed trades keep their run_number in the trade log, and
    the learning path (self_tuning / logic_proposals / retrain_loop) reads
    every closed trade regardless of run - so a reset restores the money
    without discarding what the run taught.
    """
    state = dict(state)
    state["total_resets"] += 1
    state["run_number"] += 1
    state["balance"] = STARTING_BALANCE
    state["peak_balance"] = STARTING_BALANCE
    return state
