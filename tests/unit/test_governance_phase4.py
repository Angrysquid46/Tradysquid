import json
from pathlib import Path

import pytest

import ai_coordination as coordination

ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_DIR = ROOT / "governance"


# --- Static content: validated against the real, committed governance files ---

def test_validate_governance_schema_passes_against_the_real_files():
    assert coordination.validate_governance_schema() == []


def test_check_ownership_permits_codex_on_governance_directory():
    assert coordination.check_ownership("Codex", ["governance/"]) == []
    assert coordination.check_ownership("Claude", ["governance/nested/file.json"]) == []


def test_check_ownership_rejects_codex_on_owner_only_master_spec():
    violations = coordination.check_ownership(
        "Codex", ["TRADYSQUID_2_MASTER_PREBUILD.md"]
    )
    assert violations
    assert "TRADYSQUID_2_MASTER_PREBUILD.md" in violations[0]


def test_check_ownership_ignores_paths_with_no_ownership_entry():
    """Most of the tree is intentionally unassigned until the phase that
    creates it (OWNERSHIP.json's own not_yet_assigned list) - enforcement
    only applies to paths that already have an explicit entry."""
    assert coordination.check_ownership("Codex", ["bots/blacktide/strategy.py"]) == []
    assert coordination.check_ownership("Claude", ["some_random_new_file.py"]) == []


def test_enforce_ownership_raises_for_violation_and_not_for_permitted():
    with pytest.raises(RuntimeError, match="Ownership write-guard"):
        coordination.enforce_ownership("Codex", ["TRADYSQUID_2_MASTER_PREBUILD.md"])
    coordination.enforce_ownership("Codex", ["governance/OWNERSHIP.json"])  # no raise


# --- Isolated fixture: schema/staleness checks against synthetic files -------

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
    monkeypatch.setattr(coordination, "GOV_OWNERSHIP_PATH", gov_dir / "OWNERSHIP.json")
    monkeypatch.setattr(coordination, "GOV_IMMUTABLE_RULES_PATH", gov_dir / "IMMUTABLE_RULES.json")

    monkeypatch.setattr(coordination, "git", lambda *args: "abc123")
    monkeypatch.setattr(coordination, "update_current_state", lambda: {})
    monkeypatch.setattr(coordination, "update_git_history", lambda: None)
    coordination.EVENTS_PATH.touch()
    coordination.STATE_PATH.write_text("state\n", encoding="utf-8")
    return tmp_path


def test_schema_tolerates_no_governance_files_at_all(control):
    """A missing governance file is not a schema violation - only content
    that is present and malformed is. Most isolated test/partial-checkout
    contexts never populate every governance file."""
    assert coordination.validate_governance_schema() == []


def test_schema_flags_bad_phases_status_enum(control):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "PHASES.json").write_text(
        json.dumps({"phases": [{
            "phase_number": 0, "name": "x", "status": "NOT_A_REAL_STATUS",
            "discovered_subphases": [],
        }]}),
        encoding="utf-8",
    )
    problems = coordination.validate_governance_schema()
    assert "schema:PHASES.json:status_not_in_enum" in problems


def test_schema_flags_ownership_missing_entries_key(control):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "OWNERSHIP.json").write_text(
        json.dumps({"ownership_classes": ["SHARED_CORE"]}), encoding="utf-8"
    )
    problems = coordination.validate_governance_schema()
    assert "schema:OWNERSHIP.json:missing_key:entries" in problems


def test_schema_flags_active_handoff_missing_work_id_when_active(control):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "ACTIVE_HANDOFF.json").write_text(
        json.dumps({"active": True}), encoding="utf-8"
    )
    problems = coordination.validate_governance_schema()
    assert "schema:ACTIVE_HANDOFF.json:missing_key:work_id" in problems
    assert "schema:ACTIVE_HANDOFF.json:missing_key:actor" in problems
    assert "schema:ACTIVE_HANDOFF.json:missing_key:task" in problems


def test_check_state_freshness_not_stale_when_commit_matches(control):
    coordination.acquire("Codex", "shared work", "test")
    coordination.finish("Codex", "done", "test", "n/a", [])
    result = coordination.check_state_freshness()
    assert result["stale"] is False
    assert result["recorded_commit"] == result["actual_commit"] == "abc123"


def _dispatching_git_stub(rev_parse_result, is_ancestor, distance):
    """A commit can never record its own SHA - finish()/a manual resync
    always leaves PROJECT_STATE.json a few commits behind the commit that
    carries it. This stub lets tests exercise the resulting ancestor+
    distance logic precisely instead of the fixture's blanket 'abc123'
    stand-in, which can't distinguish git subcommands."""
    def git_stub(*args):
        if args[:2] == ("rev-parse", "HEAD"):
            return rev_parse_result
        if args[:2] == ("merge-base", "--is-ancestor"):
            if is_ancestor:
                return ""
            raise RuntimeError("not an ancestor")
        if args[:2] == ("rev-list", "--count"):
            return str(distance)
        raise AssertionError(f"unexpected git call: {args}")
    return git_stub


def test_check_state_freshness_not_stale_when_recorded_commit_is_a_few_behind(control, monkeypatch):
    """finish() necessarily leaves PROJECT_STATE.json recording the commit
    before the one that carries it - a 1-2 commit gap is normal, not
    staleness."""
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "PROJECT_STATE.json").write_text(
        json.dumps({"current_commit": "older-sha"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        coordination, "git", _dispatching_git_stub("newer-sha", is_ancestor=True, distance=2)
    )
    result = coordination.check_state_freshness()
    assert result["stale"] is False


def test_check_state_freshness_stale_when_recorded_commit_is_far_behind(control, monkeypatch):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "PROJECT_STATE.json").write_text(
        json.dumps({"current_commit": "ancient-sha"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        coordination, "git", _dispatching_git_stub("newer-sha", is_ancestor=True, distance=50)
    )
    result = coordination.check_state_freshness()
    assert result["stale"] is True
    assert result["reason"] == "PROJECT_STATE_STALE"


def test_check_state_freshness_stale_when_recorded_commit_is_not_an_ancestor(control, monkeypatch):
    """Recorded commit missing from history entirely (rebase, hard reset,
    wrong branch) - always stale regardless of distance."""
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "PROJECT_STATE.json").write_text(
        json.dumps({"current_commit": "orphaned-sha"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        coordination, "git", _dispatching_git_stub("newer-sha", is_ancestor=False, distance=0)
    )
    result = coordination.check_state_freshness()
    assert result["stale"] is True


def test_check_state_freshness_not_stale_when_lock_active_despite_commit_mismatch(control, monkeypatch):
    coordination.acquire("Codex", "shared work", "test")
    gov_dir = control / "governance"
    (gov_dir / "PROJECT_STATE.json").write_text(
        json.dumps({"current_commit": "stale-sha-000"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        coordination, "git", _dispatching_git_stub("abc123", is_ancestor=False, distance=0)
    )
    result = coordination.check_state_freshness()
    assert result["stale"] is False


def test_verify_blocks_on_stale_state(control, monkeypatch):
    monkeypatch.setattr(
        coordination,
        "check_state_freshness",
        lambda: {"stale": True, "recorded_commit": "a", "actual_commit": "b", "reason": "PROJECT_STATE_STALE"},
    )
    with pytest.raises(RuntimeError, match="state_stale:commit_mismatch"):
        coordination.verify()


def test_finish_succeeds_when_files_are_within_actor_writers(control):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "OWNERSHIP.json").write_text(
        json.dumps({
            "ownership_classes": ["SHARED_CORE"],
            "entries": [{
                "path": "shared/thing.py", "owner": "SHARED_CORE",
                "readers": ["Codex", "Claude"], "writers": ["Codex", "Claude"],
                "protected": True, "purpose": "test",
            }],
        }),
        encoding="utf-8",
    )
    coordination.acquire("Codex", "shared work", "test")
    event = coordination.finish("Codex", "done", "test", "n/a", ["shared/thing.py"])
    assert event["event"] == "COMPLETE"
    assert not coordination.LOCK_PATH.exists()


def test_finish_rejects_when_files_include_a_path_actor_cannot_write(control):
    gov_dir = control / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "OWNERSHIP.json").write_text(
        json.dumps({
            "ownership_classes": ["CLAUDE_ONLY"],
            "entries": [{
                "path": "bots/claude/strategy.py", "owner": "CLAUDE_ONLY",
                "readers": ["Claude"], "writers": ["Claude"],
                "protected": True, "purpose": "test",
            }],
        }),
        encoding="utf-8",
    )
    coordination.acquire("Codex", "shared work", "test")
    with pytest.raises(RuntimeError, match="Ownership write-guard"):
        coordination.finish("Codex", "done", "test", "n/a", ["bots/claude/strategy.py"])
    # The guard fires before any write: the lock is still held and no
    # COMPLETE event was appended.
    assert coordination.LOCK_PATH.exists()
    events = coordination.EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    assert not any(json.loads(line)["event"] == "COMPLETE" for line in events)


# --- mark_phase_status ------------------------------------------------------

@pytest.fixture
def phases_file(tmp_path, monkeypatch):
    path = tmp_path / "PHASES.json"
    path.write_text(json.dumps({
        "phases": [
            {"phase_number": 0, "name": "a", "status": "complete",
             "dependencies": [], "completion_criteria": "x",
             "completion_evidence": "done", "discovered_subphases": []},
            {"phase_number": 1, "name": "b", "status": "not_started",
             "dependencies": [0], "completion_criteria": "x",
             "discovered_subphases": []},
            {"phase_number": 2, "name": "c", "status": "not_started",
             "dependencies": [1], "completion_criteria": "x",
             "discovered_subphases": []},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(coordination, "GOV_PHASES_PATH", path)
    return path


def test_mark_phase_status_writes_atomically(phases_file):
    coordination.mark_phase_status(1, "in_progress")
    data = json.loads(phases_file.read_text(encoding="utf-8"))
    assert data["phases"][1]["status"] == "in_progress"
    assert not phases_file.with_suffix(".json.tmp").exists()


def test_mark_phase_status_rejects_out_of_order_transition(phases_file):
    """Phase 1 is still not_started; marking phase 2 in_progress would make
    the started set {0, 2} - not a contiguous prefix from 0."""
    with pytest.raises(ValueError, match="contiguous-prefix"):
        coordination.mark_phase_status(2, "in_progress")


def test_mark_phase_status_rejects_complete_without_evidence(phases_file):
    with pytest.raises(ValueError, match="completion_evidence"):
        coordination.mark_phase_status(1, "complete")


def test_mark_phase_status_rejects_unknown_phase(phases_file):
    with pytest.raises(ValueError, match="No phase"):
        coordination.mark_phase_status(99, "in_progress")
