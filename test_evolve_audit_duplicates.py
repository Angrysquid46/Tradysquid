"""Tests for /evolve-audit-duplicates: owner-only command that runs
evolve_bot's own duplicate_audit.py as a subprocess against its .venv-evolve
(not an in-process import - engine.py pulls in lightgbm/shap, which aren't
installed in this bot's own venv) and reports the repair summary."""

from __future__ import annotations

import json
from unittest import mock

import discord_command_bot as bot


def _owner_interaction():
    bot.ALLOWED_USER_ID = "owner-1"
    return {"member": {"user": {"id": "owner-1"}}, "data": {}}


def _fake_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return mock.Mock(stdout=stdout, stderr=stderr, returncode=returncode)


def test_non_owner_cannot_run_the_audit():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {"member": {"user": {"id": "someone-else"}}, "data": {}}
    with mock.patch.object(bot.subprocess, "run") as run:
        try:
            bot.evolve_audit_duplicates_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        run.assert_not_called()


def test_runs_the_real_evolve_venv_python_against_duplicate_audit_py():
    result = {
        "applied": True, "trade_ids_checked": 5, "trade_ids_repaired": 0,
        "repaired": [], "cards_removed": 0, "cards_reposted": 0,
        "misplaced_channel_hits": 0, "orphaned_cards_removed": 0,
    }
    with mock.patch.object(bot.subprocess, "run", return_value=_fake_completed(stdout=json.dumps(result))) as run:
        reply = bot.evolve_audit_duplicates_reply(_owner_interaction())

    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == [str(bot.EVOLVE_PYTHON), "duplicate_audit.py"]
    assert kwargs["cwd"] == str(bot.EVOLVE_DIR)
    assert "Nothing to fix" in reply
    assert "Checked **5**" in reply


def test_reports_repairs_when_duplicates_were_found_and_fixed():
    result = {
        "applied": True, "trade_ids_checked": 5, "trade_ids_repaired": 2,
        "repaired": ["EVOLVE-20260812-001", "EVOLVE-20260812-002"],
        "cards_removed": 7, "cards_reposted": 2,
        "misplaced_channel_hits": 1, "orphaned_cards_removed": 0,
    }
    with mock.patch.object(bot.subprocess, "run", return_value=_fake_completed(stdout=json.dumps(result))):
        reply = bot.evolve_audit_duplicates_reply(_owner_interaction())

    assert "Repaired **2**" in reply
    assert "removed 7" in reply
    assert "reposted 2" in reply
    assert "1 card(s) were sitting in the wrong channel" in reply
    assert "EVOLVE-20260812-001" in reply


def test_a_nonzero_exit_code_reports_the_failure_instead_of_crashing():
    with mock.patch.object(bot.subprocess, "run", return_value=_fake_completed(stderr="Traceback...", returncode=1)):
        reply = bot.evolve_audit_duplicates_reply(_owner_interaction())
    assert "failed" in reply.lower()
    assert "Traceback" in reply


def test_a_subprocess_launch_failure_is_reported_not_raised():
    with mock.patch.object(bot.subprocess, "run", side_effect=OSError("python.exe not found")):
        reply = bot.evolve_audit_duplicates_reply(_owner_interaction())
    assert "Could not run" in reply
    assert "python.exe not found" in reply


def test_invalid_json_output_is_reported_not_raised():
    with mock.patch.object(bot.subprocess, "run", return_value=_fake_completed(stdout="not json")):
        reply = bot.evolve_audit_duplicates_reply(_owner_interaction())
    assert "no valid output" in reply.lower()
