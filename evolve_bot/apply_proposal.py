"""The one and only path from a Phase 12 review-queue proposal to an
actually-applied live trading-logic change.

Nothing in this codebase calls apply_proposal() automatically - there is
no scheduled job, no cron entry, no cadence, nothing wired to invoke it
without a human explicitly choosing a specific proposal_id and running
it. This is deliberate: logic_proposals.py can only ever generate
evidence-backed recommendations; this module is where an owner's actual
"yes, do that one" decision takes effect, and it applies exactly the one
proposal it's told to, exactly once, refusing anything ambiguous rather
than guessing.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import backtest
import logic_proposals
import logic_state


def _read_proposals() -> list[dict[str, Any]]:
    if not logic_proposals.LOGIC_PROPOSALS_PATH.exists():
        return []
    entries = []
    with logic_proposals.LOGIC_PROPOSALS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _write_proposals(proposals: list[dict[str, Any]]) -> None:
    logic_proposals.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with logic_proposals.LOGIC_PROPOSALS_PATH.open("w", encoding="utf-8") as f:
        for entry in proposals:
            f.write(json.dumps(entry) + "\n")


def _variant_parameters(variant_label: str) -> dict[str, float] | None:
    """Looks up a proposal's variant_label in the exact same grid
    backtest.py generated it from - the proposal itself only carries
    aggregate performance stats (win rate, profit factor), not the raw
    stop/target/floor numbers, so this is where those get resolved back
    from the label."""
    for variant in backtest.DEFAULT_VARIANTS:
        if variant["label"] == variant_label:
            return variant
    return None


def apply_proposal(proposal_id: str) -> dict[str, Any]:
    """Applies exactly the named proposal, exactly once, only if it's
    still genuinely pending. Every failure mode returns a real status
    string rather than raising or silently doing nothing, so a caller
    (a human running this by hand, or a future Discord command) always
    gets a clear answer about what happened."""
    proposals = _read_proposals()
    target = None
    target_index = None
    for i, proposal in enumerate(proposals):
        if proposal.get("proposal_id") == proposal_id:
            target = proposal
            target_index = i
            break

    if target is None:
        return {"status": "no such proposal", "proposal_id": proposal_id}
    if target.get("status") != "pending_owner_review":
        return {
            "status": f"proposal is not pending (current status: {target.get('status')})",
            "proposal_id": proposal_id,
        }
    if target.get("category") != "exit_parameter_change":
        return {
            "status": f"don't know how to apply category '{target.get('category')}'",
            "proposal_id": proposal_id,
        }

    variant_label = target["proposed"]["variant"]
    params = _variant_parameters(variant_label)
    if params is None:
        return {
            "status": f"variant '{variant_label}' not found in backtest.DEFAULT_VARIANTS",
            "proposal_id": proposal_id,
        }

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    logic_state.save_active_override(
        {
            "stop_pct": params["stop_pct"],
            "target_pct": params["target_pct"],
            "floor_pct": params["floor_pct"],
            "floor_trigger_pct": params["floor_trigger_pct"],
            "source_proposal_id": proposal_id,
            "variant_label": variant_label,
            "applied_at": timestamp,
        }
    )

    target["status"] = "applied"
    target["applied_at"] = timestamp
    proposals[target_index] = target
    _write_proposals(proposals)
    logic_proposals.record_resolution(proposal_id, "applied")

    return {"status": "applied", "proposal_id": proposal_id, "variant_label": variant_label}


def revert_active_override() -> dict[str, Any]:
    """Instant, one-call return to the live default exit rule. Does not
    touch the proposal's own record in the queue - it stays "applied", an
    honest historical fact - this only undoes the currently-ACTIVE
    effect, not the history of what was once approved and applied."""
    logic_state.clear_active_override()
    return {"status": "reverted to live default"}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python apply_proposal.py <proposal_id>")
    else:
        print(json.dumps(apply_proposal(sys.argv[1]), indent=2))
