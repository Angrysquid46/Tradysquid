"""The suite must not write the live supervisor state file.

Reproduces the 2026-08-20 finding directly: after a full-suite run the real
`state/supervisor-state.json` contained `"service_health": {"fake-service":
false}` and an empty `service_process_ids`. See `conftest.py` for the
mechanism - `run_supervisor_simple` rebinds `supervisor.ensure_services` at
import, and the replacement writes the real file.

Every assertion here is "the canary did NOT reach the live file" rather
than "the live file is byte-identical", because the real supervisor is
running while these tests run and legitimately rewrites that file every two
minutes. A byte comparison would fail on a healthy system.
"""

from __future__ import annotations

import importlib
import json
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import tradysquid_supervisor as supervisor

LIVE = Path(__file__).resolve().parent / "state" / "supervisor-state.json"


def _live_text() -> str:
    return LIVE.read_text(encoding="utf-8") if LIVE.exists() else ""


def test_state_path_is_redirected_away_from_the_live_file() -> None:
    # Fails without conftest.py: the module constant still points at the
    # file the watchdog reads.
    assert supervisor.DEPLOY_STATE_PATH.resolve() != LIVE.resolve()


def test_write_state_cannot_reach_the_live_file(sandboxed_supervisor_state) -> None:
    canary = f"pytest-canary-{uuid.uuid4().hex}"
    supervisor.write_state(supervisor_mode=canary)

    assert canary not in _live_text(), "a test wrote into the live supervisor state"
    assert json.loads(Path(sandboxed_supervisor_state).read_text(
        encoding="utf-8"
    ))["supervisor_mode"] == canary


def test_seeded_sandbox_still_reads_like_the_real_state(
    sandboxed_supervisor_state,
) -> None:
    # Redirecting must not blind tests that legitimately READ the state -
    # the sandbox starts as a copy of the real file.
    if not LIVE.exists():
        pytest.skip("no live state file on this checkout")
    payload = supervisor.state_payload()
    assert payload.get("deployed_sha")


def test_the_fake_service_scenario_does_not_touch_the_live_file() -> None:
    """The exact path that corrupted the file on 2026-08-20."""
    # Importing this module is what rebinds supervisor.ensure_services to
    # the state-writing wrapper - the same thing test_simple_upgrade_flow
    # does, which is how unrelated tests inherited the write.
    importlib.import_module("run_supervisor_simple")
    assert supervisor.ensure_services.__module__ == "run_supervisor_simple"

    process = Mock()
    process.pid = 40001
    process.poll.return_value = None  # alive
    service = supervisor.Service("fake-service", lambda: [], lambda: True)

    original_services = supervisor.SERVICES
    original_processes = dict(supervisor.PROCESSES)
    supervisor.SERVICES = [service]
    supervisor.PROCESSES = {"fake-service": process}
    try:
        with patch.object(supervisor, "discord_post"):
            supervisor.ensure_services()
    finally:
        supervisor.SERVICES = original_services
        supervisor.PROCESSES = original_processes

    live = _live_text()
    assert "fake-service" not in live, (
        "the fake service reached the live supervisor state file"
    )
    assert json.loads(supervisor.DEPLOY_STATE_PATH.read_text(encoding="utf-8"))[
        "service_health"
    ] == {"fake-service": True}
