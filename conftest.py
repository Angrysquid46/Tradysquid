"""Repo-wide pytest guard: tests must never write the LIVE supervisor state.

Found 2026-08-20. Straight after a full-suite run, the live
`state/supervisor-state.json` read:

    "service_health": {"fake-service": false}
    "service_process_ids": {}

i.e. the file the watchdog and the diagnostics consult was claiming zero
healthy services and no running processes. The real supervisor's next
heartbeat repaired it about fifteen seconds later, so nothing broke - but
anything that read the file inside that window would have seen a system
that looked entirely down.

The chain: `run_supervisor_simple` rebinds `supervisor.ensure_services` at
IMPORT time (run_supervisor_simple.py:347), and the replacement calls
`supervisor.write_state(...)` on the way in and out. So the moment any test
imports that module, every later `supervisor.ensure_services()` call in the
same session writes the real file - including the two tests in
`test_supervisor_availability.py` that deliberately install a fake service
to exercise the health-failure debounce. Neither test does anything wrong;
the write is invisible from where they sit.

`tradysquid_supervisor.write_state` is the only writer of that file in the
repository, and it resolves `DEPLOY_STATE_PATH` at call time, so pointing
that one name at a sandbox closes the whole surface rather than the two
callers that happened to be noticed. The sandbox is seeded with a copy of
the real state, so tests that READ it still see plausible content.

`tradysquid_supervisor.py` and `run_supervisor_simple.py` are both under
the AGENTS.md updater freeze. This fixes it from the test side, which
needs no exception to that freeze.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
LIVE_SUPERVISOR_STATE = ROOT / "state" / "supervisor-state.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sandbox_dir() -> Path:
    """A writable directory for the fake state file.

    Deliberately NOT pytest's `tmp_path_factory`: on this Windows checkout
    its shared `pytest-of-<user>` base directory raises PermissionError
    (the same environment fault already noted against
    tests/unit/test_verifier_modules.py). An autouse session fixture that
    can raise would take the entire suite down with it, so this falls back
    to the repo's own gitignored state/ directory, which the supervisor
    writes to constantly and is therefore known-writable.
    """
    try:
        return Path(tempfile.mkdtemp(prefix="tradysquid-supervisor-state-"))
    except OSError:
        fallback = ROOT / "state" / "pytest-sandbox"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@pytest.fixture(scope="session", autouse=True)
def sandboxed_supervisor_state():
    """Point supervisor state writes at a temp file for the whole session."""
    try:
        import tradysquid_supervisor as supervisor
    except Exception:  # the suite must still run where the module won't import
        yield None
        return

    sandbox = _sandbox_dir() / "supervisor-state.json"
    if LIVE_SUPERVISOR_STATE.exists():
        shutil.copy2(LIVE_SUPERVISOR_STATE, sandbox)

    original = supervisor.DEPLOY_STATE_PATH
    supervisor.DEPLOY_STATE_PATH = sandbox
    try:
        yield sandbox
    finally:
        supervisor.DEPLOY_STATE_PATH = original
