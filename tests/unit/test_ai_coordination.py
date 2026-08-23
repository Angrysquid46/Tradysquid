import json

import pytest

import ai_coordination as coordination


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(coordination, "CONTROL_DIR", tmp_path)
    monkeypatch.setattr(coordination, "LOCK_PATH", tmp_path / "UPDATE_LOCK.json")
    monkeypatch.setattr(coordination, "ACTIVE_TASK_PATH", tmp_path / "ACTIVE_TASK.json")
    monkeypatch.setattr(coordination, "EVENTS_PATH", tmp_path / "CHANGELOG.jsonl")
    monkeypatch.setattr(coordination, "STATE_PATH", tmp_path / "CURRENT_STATE.md")
    monkeypatch.setattr(coordination, "HISTORY_PATH", tmp_path / "GIT_HISTORY.md")
    monkeypatch.setattr(coordination, "git", lambda *args: "abc123")
    monkeypatch.setattr(coordination, "update_current_state", lambda: {})
    monkeypatch.setattr(coordination, "update_git_history", lambda: None)
    coordination.EVENTS_PATH.touch()
    coordination.STATE_PATH.write_text("state\n", encoding="utf-8")
    return tmp_path


def test_two_actors_cannot_hold_the_edit_lock(control):
    first = coordination.acquire("Codex", "shared work", "test")

    status = coordination.verify()
    assert status["status"] == "READY_ACTIVE"
    assert status["lock_available"] is False

    with pytest.raises(RuntimeError, match="Another update is active"):
        coordination.acquire("Claude", "conflicting work", "test")

    assert first["work_id"]
    assert json.loads(coordination.LOCK_PATH.read_text())["actor"] == "Codex"


def test_checkpoint_requires_lock_owner_and_is_recoverable(control):
    started = coordination.acquire("Claude", "phase zero", "test")

    with pytest.raises(RuntimeError, match="Lock belongs to Claude"):
        coordination.checkpoint("Codex", "wrong actor", "stop")

    event = coordination.checkpoint("Claude", "validated files", "run tests")
    active = json.loads(coordination.ACTIVE_TASK_PATH.read_text())
    assert event["work_id"] == started["work_id"]
    assert active["last_successful_action"] == "validated files"
    assert active["next_safe_action"] == "run tests"


def test_verify_rejects_lock_without_matching_active_task(control):
    coordination.acquire("Codex", "shared work", "test")
    coordination.ACTIVE_TASK_PATH.unlink()

    with pytest.raises(RuntimeError, match="lock_active_task_mismatch"):
        coordination.verify()


def test_begin_rejects_inconsistent_hub_before_creating_lock(control):
    coordination.STATE_PATH.unlink()

    with pytest.raises(RuntimeError, match="missing:CURRENT_STATE.md"):
        coordination.acquire("Claude", "phase zero", "test")

    assert not coordination.LOCK_PATH.exists()


def test_finish_preserves_work_id_and_releases_lock(control):
    started = coordination.acquire("Codex", "shared work", "test")
    event = coordination.finish(
        "Codex", "finished", "test", "pytest passed", ["AGENTS.md"]
    )

    assert event["work_id"] == started["work_id"]
    assert not coordination.LOCK_PATH.exists()
    assert not coordination.ACTIVE_TASK_PATH.exists()
    status = coordination.verify()
    assert status["status"] == "READY_CLEAR"
    assert status["lock_available"] is True
