import json
from pathlib import Path

import pytest

import ai_coordination as coordination

ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_DIR = ROOT / "governance"


# --- Static content: the files authored directly in the real repo ---------

def _load(name: str) -> dict:
    return json.loads((GOVERNANCE_DIR / name).read_text(encoding="utf-8"))


def test_phases_file_covers_all_seventeen_phases_in_order():
    data = _load("PHASES.json")
    phases = data["phases"]
    assert [p["phase_number"] for p in phases] == list(range(17))
    names = [p["name"] for p in phases]
    assert "Governance bootstrap" in names[0]
    assert "Competition launch" in names[15]
    assert "Learning Center population" in names[16]
    for phase in phases:
        assert phase["status"] in {"not_started", "in_progress", "complete"}
        assert isinstance(phase["discovered_subphases"], list)


def test_no_phase_is_started_out_of_order():
    """Section 19's phase list is a build order, not a menu - a phase may only
    be in_progress/complete if every phase before it already is too, and
    every phase after the last non-not_started one must still be
    not_started. Durable across however many phases have actually run,
    unlike asserting a specific snapshot of which phase number is current."""
    phases = _load("PHASES.json")["phases"]
    started = [p["phase_number"] for p in phases if p["status"] != "not_started"]
    assert started == list(range(len(started))), (
        f"started phases {started} are not a contiguous prefix from 0"
    )
    for phase in phases:
        assert phase["status"] in {"not_started", "in_progress", "complete"}
        if phase["status"] == "complete":
            assert phase.get("completion_evidence"), (
                f"Phase {phase['phase_number']} marked complete with no completion_evidence"
            )


def test_ownership_file_defines_all_declared_classes():
    data = _load("OWNERSHIP.json")
    assert set(data["ownership_classes"]) == {
        "SHARED_CORE", "SHARED_DATA", "BLACKTIDE_ONLY",
        "CLAUDE_ONLY", "HUMAN_LEARNING_CENTER", "GROK_ONLY",
    }
    paths = {entry["path"] for entry in data["entries"]}
    assert "governance/" in paths
    assert "ai_coordination.py" in paths


def test_immutable_rules_match_master_spec_section_four_exactly():
    data = _load("IMMUTABLE_RULES.json")
    rules = data["immutable_competition_rules"]
    assert rules["starting_bankroll_per_generation_usd"] == 1000
    assert rules["max_open_trades_per_bot"] == 1
    assert rules["no_lookahead"] is True
    assert rules["official_completed_trades_immutable"] is True
    assert rules["money_resets_history_does_not"] is True
    boundary = data["private_competitor_boundary"]
    assert boundary["competitors"]["BLACKTIDE"]["owner"] == "ChatGPT/Codex"
    assert "AXIOM" not in boundary["competitors"]
    assert boundary["removed_competitors"]["AXIOM"]["owner"] == "Claude"


# --- Dynamic mirror: governed by ai_coordination.py's begin/checkpoint/finish ---

@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(coordination, "CONTROL_DIR", tmp_path)
    monkeypatch.setattr(coordination, "LOCK_PATH", tmp_path / "UPDATE_LOCK.json")
    monkeypatch.setattr(coordination, "ACTIVE_TASK_PATH", tmp_path / "ACTIVE_TASK.json")
    monkeypatch.setattr(coordination, "EVENTS_PATH", tmp_path / "CHANGELOG.jsonl")
    monkeypatch.setattr(coordination, "STATE_PATH", tmp_path / "CURRENT_STATE.md")
    monkeypatch.setattr(coordination, "HISTORY_PATH", tmp_path / "GIT_HISTORY.md")

    gov_dir = tmp_path / "governance"
    monkeypatch.setattr(coordination, "GOVERNANCE_DIR", gov_dir)
    monkeypatch.setattr(coordination, "GOV_PROJECT_STATE_PATH", gov_dir / "PROJECT_STATE.json")
    monkeypatch.setattr(coordination, "GOV_PHASES_PATH", gov_dir / "PHASES.json")
    monkeypatch.setattr(coordination, "GOV_ACTIVE_HANDOFF_PATH", gov_dir / "ACTIVE_HANDOFF.json")
    monkeypatch.setattr(coordination, "GOV_CHANGELOG_PATH", gov_dir / "CHANGELOG.jsonl")

    monkeypatch.setattr(coordination, "git", lambda *args: "abc123")
    monkeypatch.setattr(coordination, "update_current_state", lambda: {})
    monkeypatch.setattr(coordination, "update_git_history", lambda: None)
    coordination.EVENTS_PATH.touch()
    coordination.STATE_PATH.write_text("state\n", encoding="utf-8")
    return tmp_path


def test_begin_without_new_args_still_works_like_codexs_existing_calls(control):
    payload = coordination.acquire("Codex", "shared work", "test")
    assert payload["work_id"]
    handoff = json.loads(coordination.GOV_ACTIVE_HANDOFF_PATH.read_text())
    assert handoff["active"] is True
    assert handoff["phase"] is None
    assert handoff["reason"] == ""


def test_begin_with_handoff_fields_populates_active_handoff(control):
    coordination.acquire(
        "Claude", "phase zero", "test",
        phase="Phase 0",
        reason="testing the handoff fields",
        before_state="nothing built yet",
        intended_scope="governance files only",
        expected_effects="new governance/ directory",
        required_tests="test_governance_phase0.py",
        risks="none",
        next_safe_action="run the tests",
    )
    handoff = json.loads(coordination.GOV_ACTIVE_HANDOFF_PATH.read_text())
    assert handoff["phase"] == "Phase 0"
    assert handoff["reason"] == "testing the handoff fields"
    assert handoff["before_state"] == "nothing built yet"
    assert handoff["next_safe_action_if_interrupted"] == "run the tests"

    state = json.loads(coordination.GOV_PROJECT_STATE_PATH.read_text())
    assert state["current_phase"] == "Phase 0"
    assert state["active_lock"]["actor"] == "Claude"


def test_checkpoint_updates_governance_mirror_and_preserves_phase(control):
    coordination.acquire("Claude", "phase zero", "test", phase="Phase 0")
    coordination.checkpoint("Claude", "made progress", "keep going")

    handoff = json.loads(coordination.GOV_ACTIVE_HANDOFF_PATH.read_text())
    assert handoff["next_safe_action_if_interrupted"] == "keep going"
    assert handoff["phase"] == "Phase 0"

    state = json.loads(coordination.GOV_PROJECT_STATE_PATH.read_text())
    assert state["current_phase"] == "Phase 0"

    events = coordination.GOV_CHANGELOG_PATH.read_text().splitlines()
    assert any(json.loads(line)["event"] == "CHECKPOINT" for line in events)


def test_finish_clears_active_handoff_and_appends_governance_changelog(control):
    coordination.acquire("Codex", "shared work", "test", phase="Phase 0")
    coordination.finish("Codex", "finished", "test", "pytest passed", ["AGENTS.md"])

    handoff = json.loads(coordination.GOV_ACTIVE_HANDOFF_PATH.read_text())
    assert handoff["active"] is False
    assert handoff["work_id"] is None

    events = [json.loads(line) for line in coordination.GOV_CHANGELOG_PATH.read_text().splitlines()]
    assert any(e["event"] == "COMPLETE" for e in events)
    assert not coordination.LOCK_PATH.exists()
