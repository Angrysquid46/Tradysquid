"""Phase 12's applied-changes state - the ONE place an approved logic
change actually takes effect in live trading.

Starts empty (no override file), meaning the evolve bot's exit rule is an
exact mirror of spy_scanner's live SPY_0DTE_STOP_PCT/TARGET_PCT constants
- identical behavior to every earlier phase. An override only ever
appears here via apply_proposal.apply_proposal(), which only ever runs
when explicitly invoked with one specific, already-approved proposal_id.
There is no scheduled job, no automatic trigger, and no path from a
generated proposal to an active override that skips that explicit human
decision - the review queue (logic_proposals.py) can only ever recommend;
this module is where a recommendation someone actually said yes to takes
effect.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import backtest_exit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
ACTIVE_OVERRIDE_PATH = STATE_DIR / "active_exit_override.json"


def load_active_override() -> dict[str, Any] | None:
    try:
        return json.loads(ACTIVE_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_active_override(override: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_OVERRIDE_PATH.write_text(json.dumps(override, indent=2), encoding="utf-8")


def clear_active_override() -> None:
    """Instant, one-call revert to the live default - deleting this file
    is enough; current_exit_signal falls straight back to spy_scanner's
    own live constants the moment it's gone."""
    if ACTIVE_OVERRIDE_PATH.exists():
        ACTIVE_OVERRIDE_PATH.unlink()


def current_exit_signal(
    entry_price: float, mark: float, minutes_remaining: float, peak_pct: float
) -> tuple[str, str]:
    """What engine.py actually calls to evaluate an open position's exit.
    Live spy_scanner default when nothing has ever been applied (the
    unchanged behavior of every earlier phase); the applied override's
    own stop/target/floor parameters, via the same exit LOGIC
    (backtest_exit.backtest_exit_signal, the exact function already
    proven against the live one via backtest_exit's own drift-guard
    test), once/if the owner has approved a Phase 12 proposal."""
    override = load_active_override()
    if override is None:
        return s.spy_0dte_exit_signal(entry_price, mark, minutes_remaining, peak_pct)
    return backtest_exit.backtest_exit_signal(
        entry_price,
        mark,
        minutes_remaining,
        peak_pct,
        override["stop_pct"],
        override["target_pct"],
        override["floor_pct"],
        override["floor_trigger_pct"],
    )
