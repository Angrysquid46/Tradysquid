from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import apply_proposal
import logic_state


def _write_proposals(path: Path, proposals: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for proposal in proposals:
            f.write(json.dumps(proposal) + "\n")


def _pending_proposal(proposal_id: str = "LOGIC-TEST-1", **overrides) -> dict:
    proposal = {
        "proposal_id": proposal_id,
        "timestamp": "2026-08-12T00:00:00",
        "category": "exit_parameter_change",
        "current": {"variant": "stop_50_target_50"},
        "proposed": {"variant": "stop_20_target_50"},  # a real grid combo
        "status": "pending_owner_review",
    }
    proposal.update(overrides)
    return proposal


def test_apply_proposal_writes_the_correct_override_and_marks_it_applied():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        proposals_path = temp_path / "logic_proposals.jsonl"
        override_path = temp_path / "active_exit_override.json"
        _write_proposals(proposals_path, [_pending_proposal()])

        with (
            mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path),
        ):
            result = apply_proposal.apply_proposal("LOGIC-TEST-1")

            assert result["status"] == "applied"
            assert result["variant_label"] == "stop_20_target_50"

            override = logic_state.load_active_override()
            assert override["stop_pct"] == 0.20
            assert override["target_pct"] == 0.50
            assert override["source_proposal_id"] == "LOGIC-TEST-1"

        saved_proposals = json.loads(proposals_path.read_text(encoding="utf-8").strip().splitlines()[0])
        assert saved_proposals["status"] == "applied"
        assert "applied_at" in saved_proposals


def test_apply_proposal_refuses_an_unknown_id():
    with tempfile.TemporaryDirectory() as temp:
        proposals_path = Path(temp) / "logic_proposals.jsonl"
        _write_proposals(proposals_path, [_pending_proposal()])
        with mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path):
            result = apply_proposal.apply_proposal("LOGIC-DOES-NOT-EXIST")
        assert result["status"] == "no such proposal"


def test_apply_proposal_refuses_a_proposal_that_is_not_pending():
    with tempfile.TemporaryDirectory() as temp:
        proposals_path = Path(temp) / "logic_proposals.jsonl"
        _write_proposals(proposals_path, [_pending_proposal(status="applied")])
        with mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path):
            result = apply_proposal.apply_proposal("LOGIC-TEST-1")
        assert "not pending" in result["status"]


def test_apply_proposal_refuses_an_unrecognized_category():
    with tempfile.TemporaryDirectory() as temp:
        proposals_path = Path(temp) / "logic_proposals.jsonl"
        _write_proposals(proposals_path, [_pending_proposal(category="entry_filter_change")])
        with mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path):
            result = apply_proposal.apply_proposal("LOGIC-TEST-1")
        assert "don't know how to apply category" in result["status"]


def test_apply_proposal_updates_logic_proposals_own_pending_state():
    """Regression guard for a real bug: apply_proposal() used to only
    update the proposal's own record in the queue file, leaving
    logic_proposals.py's internal tracking state stuck reporting
    "already proposed, awaiting owner review" forever for a proposal
    that had actually already been applied - found by actually running
    run_daily_refresh.ps1 against real data, not from a unit test."""
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        proposals_path = temp_path / "logic_proposals.jsonl"
        override_path = temp_path / "active_exit_override.json"
        proposal_state_path = temp_path / "logic_proposal_state.json"
        _write_proposals(proposals_path, [_pending_proposal()])
        proposal_state_path.write_text(
            json.dumps(
                {
                    "last_considered_file_hash": "abc123",
                    "last_proposed_variant": "stop_20_target_50",
                    "last_proposal_status": "pending_owner_review",
                    "last_proposal_id": "LOGIC-TEST-1",
                }
            ),
            encoding="utf-8",
        )

        with (
            mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(apply_proposal.logic_proposals, "PROPOSAL_STATE_PATH", proposal_state_path),
            mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path),
        ):
            apply_proposal.apply_proposal("LOGIC-TEST-1")

        saved_state = json.loads(proposal_state_path.read_text(encoding="utf-8"))
        assert saved_state["last_proposal_status"] == "applied"


def test_apply_proposal_does_not_touch_other_proposals_in_the_queue():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        proposals_path = temp_path / "logic_proposals.jsonl"
        override_path = temp_path / "active_exit_override.json"
        other = _pending_proposal(proposal_id="LOGIC-OTHER")
        _write_proposals(proposals_path, [_pending_proposal(), other])

        with (
            mock.patch.object(apply_proposal.logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path),
        ):
            apply_proposal.apply_proposal("LOGIC-TEST-1")

        lines = proposals_path.read_text(encoding="utf-8").strip().splitlines()
        saved = [json.loads(line) for line in lines]
        by_id = {entry["proposal_id"]: entry for entry in saved}
        assert by_id["LOGIC-TEST-1"]["status"] == "applied"
        assert by_id["LOGIC-OTHER"]["status"] == "pending_owner_review"


def test_revert_active_override_clears_it():
    with tempfile.TemporaryDirectory() as temp:
        override_path = Path(temp) / "active_exit_override.json"
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path):
            logic_state.save_active_override({"stop_pct": 0.2, "target_pct": 0.5, "floor_pct": -5.0, "floor_trigger_pct": 15.0})
            assert logic_state.load_active_override() is not None

            result = apply_proposal.revert_active_override()

            assert result["status"] == "reverted to live default"
            assert logic_state.load_active_override() is None
