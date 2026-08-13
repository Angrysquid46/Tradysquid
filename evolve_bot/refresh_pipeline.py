"""The one real "make the AI actually use new data" step.

A Robinhood MCP pull (interactive-only - see robinhood_cache.py's module
docstring) only adds raw bars to the local cache. By itself that does
nothing for the model, the retrain loop, or the logic-proposal queue
until someone walks those raw bars into labeled backtest rows and
re-checks whether anything downstream should update. Before this
module, that was four separate manual commands a human had to remember
to run in order, in the right sequence, after every pull - this module
is that chain, in one callable place.

Scoped deliberately to the Robinhood-pull-gated chain only (backtest
regen -> retrain -> proposals) - NOT the Discord dashboard, which
reflects real live trades/bankroll changes that happen independent of
any Robinhood pull and has its own daily gate already
(presentation.post_dashboard). Nesting the dashboard refresh inside
this module's "skip if no new cached days" gate would have meant a week
with no manual pulls also got no dashboard refresh, even though real
live trading activity happened that week - run_daily_refresh.ps1 calls
both this and post_dashboard as separate steps.

Runs on a dedicated daily schedule (run_daily_refresh.ps1 /
"Tradysquid Evolve Bot Daily Refresh"), deliberately separate from the
3-minute trading loop - backtest.run_backtest() re-walks every cached
real day with real Tradier API calls per day when there's new data to
process, which can take a while; that heavy work has no business
competing with the live loop's tight execution budget for a real
entry/exit check. Also directly runnable by hand (`python
refresh_pipeline.py`) right after finishing a manual MCP pull, instead
of waiting for the next scheduled run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import backtest
import logic_proposals
import retrain_loop
import robinhood_cache

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
REFRESH_STATE_PATH = STATE_DIR / "refresh_pipeline_state.json"


def _load_state() -> dict[str, Any] | None:
    try:
        return json.loads(REFRESH_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REFRESH_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_refresh(force: bool = False) -> dict[str, Any]:
    """Skips the expensive backtest walk entirely when the real cached
    equity-day set hasn't changed since the last refresh (a cheap local
    file-glob check, see robinhood_cache.cached_equity_days) - safe to
    call daily, or hourly, or by hand after every pull, since a day with
    no new data costs almost nothing. Each of the four real steps below
    is already independently idempotent (backtest upserts by trade_id,
    retrain_loop hashes the training file, logic_proposals tracks its
    own already-considered state, post_dashboard gates on the calendar
    day) - this function's own job is just running them in the right
    order and reporting what actually happened."""
    cached_days = sorted(robinhood_cache.cached_equity_days("SPY"))
    state = _load_state()
    if not force and state and state.get("last_seen_days") == cached_days:
        return {"status": "no new cached days since last refresh", "n_cached_days": len(cached_days)}

    backtest_result = backtest.run_backtest()
    retrain_result = retrain_loop.run_retrain_cycle()
    proposal_result = logic_proposals.run_proposal_cycle()

    _save_state({"last_seen_days": cached_days, "last_refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})

    return {
        "status": "refreshed",
        "n_cached_days": len(cached_days),
        "backtest": backtest_result,
        "retrain": retrain_result["status"],
        "proposals": proposal_result["status"],
    }


if __name__ == "__main__":
    print(json.dumps(run_refresh(force="--force" in sys.argv), indent=2))
