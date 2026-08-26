"""Phase 15: AXIOM's standalone launch entrypoint.

Runs the readiness gate (bots.claude.preflight.require_ready) with the
market-open check treated as informational rather than blocking - the job
loop in runtime.py already refuses to enter or manage a position outside
market hours (each trading Job is market_hours_only=True inside due()), so
there's no safety reason to also refuse to *start* the process after hours.
Every other check (deployed==origin/main, instance lock free, live Tradier,
today's 0DTE listed, clean Gen-1/$1,000/0-trades/FLAT state) still blocks
launch exactly as it does for the interactive CLI (preflight.main()).

Once the gate passes this hands off to runtime.main(), which acquires its
own instance lock and runs forever (job loop, not a per-session process) -
this file adds nothing but the readiness gate in front of it.

Usage:
    ./.venv-tradysquid/Scripts/python.exe -m bots.claude.launch
"""

from __future__ import annotations

from bots.claude.env_bootstrap import load_env

load_env()

from bots.claude import runtime
from bots.claude.preflight import require_ready


def main() -> int:
    ready, report = require_ready(skip_market_check=True)
    report.render()
    if not ready:
        print("AXIOM launch aborted: readiness gate failed.")
        return 1
    print("AXIOM readiness gate passed. Starting live job loop.")
    return runtime.main()


if __name__ == "__main__":
    raise SystemExit(main())
