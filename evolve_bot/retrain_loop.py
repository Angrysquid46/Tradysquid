"""Phase 5: continuous retraining loop.

"Continuous" here means safely callable over and over (any schedule, or
none at all - see run_retrain_cycle's docstring) without wasting work or
producing noise: a retrain only happens when the training data has
actually changed since the last one. Re-running train.run_training() on
an unchanged dataset would produce an identical model and just add churn
to the history log, not a real update.

This is infrastructure, not a quality claim - it does nothing to address
the small-sample-size caveat documented in train.py's run_training. It
exists so that WHEN real data volume grows (more real trading days
pulled, real live trades once the bot goes live), the model picks that up
automatically instead of needing another manual `python train.py` run,
and so there's a real, append-only record of how metrics moved over time
as that happens - useful for judging honestly whether more data is
actually helping, rather than trusting any single run's numbers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import train

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
RETRAIN_STATE_PATH = MODELS_DIR / "retrain_state.json"
RETRAIN_HISTORY_PATH = MODELS_DIR / "retrain_history.jsonl"


def _current_data_signature() -> dict[str, Any]:
    rows = train.load_training_rows()
    days = sorted({row["trading_day"] for row in rows if row.get("trading_day")})
    return {"n_rows": len(rows), "n_days": len(days), "days": days}


def _load_state() -> dict[str, Any] | None:
    try:
        return json.loads(RETRAIN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(state: dict[str, Any]) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RETRAIN_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_history(entry: dict[str, Any]) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with RETRAIN_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def should_retrain(current: dict[str, Any] | None = None, last_state: dict[str, Any] | None = None) -> bool:
    """True the first time (no prior state), or whenever the training
    data's row count or day set has changed since the last retrain -
    never on an unchanged dataset, since that would just reproduce the
    same model."""
    current = current if current is not None else _current_data_signature()
    last_state = last_state if last_state is not None else _load_state()
    if last_state is None:
        return True
    return current["n_rows"] != last_state.get("n_rows") or current["days"] != last_state.get("days")


def run_retrain_cycle() -> dict[str, Any]:
    """Safe to call on any cadence - a cron job, a manual run, or (as of
    2026-08-12) neither, since scheduling is deliberately deferred until
    the rest of the evolve bot is further along. Skips the actual
    retraining work entirely when should_retrain() is False."""
    current = _current_data_signature()
    last_state = _load_state()
    if not should_retrain(current, last_state):
        return {"status": "skipped - no new data", **current}

    result = train.run_training()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    state = {**current, "last_retrain_at": timestamp}
    _save_state(state)
    _append_history({"retrained_at": timestamp, **current, "result": result})
    # result's own "status" (e.g. train.run_training's "ok"/"not enough
    # rows to train") means something different from this wrapper's own
    # status - splat result FIRST so "retrained" always wins the key
    # collision, rather than being silently overwritten by result's value.
    return {**result, "status": "retrained"}


if __name__ == "__main__":
    print(json.dumps(run_retrain_cycle(), indent=2))
