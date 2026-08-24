"""Start the public information engine with retrying Discord acceptance.

The engine health listener must remain available even when Discord or a provider
has a transient outage. Required cards, scorecards, and open-journal contracts
are still verified, but failures put startup acceptance into RETRYING state
instead of crashing the entire information engine into a supervisor restart loop.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import local_information_engine as public


ROOT = Path(__file__).resolve().parent
ACCEPTANCE_PATH = ROOT / "state" / "market-intelligence-startup.json"
# Phase 3 purge: "premarket-visibility" and "discord-reporting" were old-
# strategy Discord reporting jobs, removed along with the strategies they
# reported on. Only provider-event-queue survives as a required startup job.
REQUIRED_STARTUP_JOBS = (
    "provider-event-queue",
)
STARTUP_INITIAL_DELAY_SECONDS = max(
    0,
    min(30, int(os.environ.get("ENGINE_STARTUP_ACCEPTANCE_DELAY_SECONDS", "2"))),
)
STARTUP_RETRY_SECONDS = max(
    15,
    min(900, int(os.environ.get("ENGINE_STARTUP_ACCEPTANCE_RETRY_SECONDS", "60"))),
)


def _write_acceptance(payload: dict[str, Any]) -> None:
    ACCEPTANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ACCEPTANCE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(ACCEPTANCE_PATH)


def _required_job(name: str):
    job = next((item for item in public.JOBS if item.name == name), None)
    if job is None:
        raise RuntimeError(f"Required startup job is missing: {name}")
    return job


def _latest_run(connection, name: str):
    return connection.execute(
        """
        SELECT job_name, started_at, finished_at, status, detail
        FROM job_runs
        WHERE job_name=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (name,),
    ).fetchone()


def run_required_startup_jobs() -> dict[str, Any]:
    """Publish and verify required Discord output without owning process health.

    Phase 3 purge: this used to also verify performance-scorecard and trade-
    journal completeness against spy_scanner's trade log - all removed along
    with the old strategy roster. Now only confirms the surviving required
    jobs actually ran."""
    connection = public.connect_db()
    results: dict[str, Any] = {}
    try:
        for name in REQUIRED_STARTUP_JOBS:
            job = _required_job(name)
            public.run_job(connection, job)
            row = _latest_run(connection, name)
            if row is None or str(row["status"]) != "OK":
                detail = str(row["detail"] if row is not None else "no job receipt")
                raise RuntimeError(f"{name} startup publication failed: {detail}")
            results[name] = {
                "status": str(row["status"]),
                "finished_at": str(row["finished_at"] or ""),
                "detail": str(row["detail"] or ""),
            }

        payload = {
            "status": "PASSED",
            "verified_at": public.iso_now(),
            "required_jobs": results,
            "contract": (
                "The engine health listener remains available while required "
                "startup jobs are verified."
            ),
        }
        _write_acceptance(payload)
        return payload
    except Exception as exc:
        payload = {
            "status": "FAILED",
            "verified_at": public.iso_now(),
            "required_jobs": results,
            "error": f"{type(exc).__name__}: {exc}",
        }
        _write_acceptance(payload)
        raise
    finally:
        connection.close()


def startup_acceptance_worker() -> None:
    """Retry required publications until verified without killing the engine."""
    if STARTUP_INITIAL_DELAY_SECONDS:
        time.sleep(STARTUP_INITIAL_DELAY_SECONDS)
    attempt = 0
    while True:
        attempt += 1
        try:
            payload = run_required_startup_jobs()
            print(
                "Startup acceptance PASSED after "
                f"{attempt} attempt(s) at {payload.get('verified_at')}."
            )
            return
        except Exception as exc:
            _write_acceptance(
                {
                    "status": "RETRYING",
                    "verified_at": public.iso_now(),
                    "attempt": attempt,
                    "next_retry_seconds": STARTUP_RETRY_SECONDS,
                    "error": f"{type(exc).__name__}: {exc}",
                    "contract": (
                        "The information engine remains online while required Discord "
                        "cards and durable receipts retry automatically."
                    ),
                }
            )
            print(
                "Startup acceptance RETRYING: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(STARTUP_RETRY_SECONDS)


def start_acceptance_retry_worker() -> threading.Thread:
    thread = threading.Thread(
        target=startup_acceptance_worker,
        name="startup-acceptance-retry",
        daemon=True,
    )
    thread.start()
    return thread


def main() -> int:
    _write_acceptance(
        {
            "status": "STARTING",
            "verified_at": public.iso_now(),
            "next_retry_seconds": STARTUP_INITIAL_DELAY_SECONDS,
            "contract": (
                "The health listener opens immediately; required Discord publications "
                "are verified by the background acceptance worker."
            ),
        }
    )
    start_acceptance_retry_worker()
    return public.main()


if __name__ == "__main__":
    raise SystemExit(main())
