"""AXIOM launches standalone (`python -m bots.claude`), never through the
frozen run_with_env.py - that file only accepts targets whose parent
directory is the repo root, so it structurally can't launch anything
under bots/claude/ (Phase 15 launch-readiness finding).

This replicates just run_with_env.py's plain .env-loading logic - not its
other steps (install_runtime_overrides, clean-rebuild handoff), which are
specific to the other live processes and don't apply to AXIOM.

Must be imported and called BEFORE any module that reads an environment
variable as a module-level constant at import time (market_data.py's
TRADIER_TOKEN, discord_transport.py's DISCORD_BOT_TOKEN, etc.) - calling
it later, e.g. inside main(), is too late: those constants are already
bound by the time main() runs. This is why every entry point (runtime.py,
preflight.py) calls this as its very first statement, before any other
import.

Silently no-ops if .env doesn't exist (unlike run_with_env.py's hard
failure) - CI and any environment without a local .env must still be able
to import this module (every AXIOM test file does) without crashing at
collection time. A genuinely missing token is caught downstream, visibly,
by preflight.py's live-connectivity check - not by an import-time
exception here.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ[name.strip()] = value.strip()
