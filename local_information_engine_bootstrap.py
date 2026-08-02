"""Start the public information engine only after required Discord cards exist.

The supervisor previously treated a live socket as sufficient proof that the
information engine was ready.  That allowed deployment to announce success
before the newly required #premarket and #breaking-alerts cards had actually
been written.  This bootstrap runs both visibility jobs synchronously and exits
on any failure, so the supervisor keeps the service unhealthy and retries it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import local_information_engine_public as public


ROOT = Path(__file__).resolve().parent
ACCEPTANCE_PATH = ROOT / "state" / "market-intelligence-startup.json"
REQUIRED_STARTUP_JOBS = (
    "provider-event-queue",
    "premarket-visibility",
)


def _write_acceptance(payload: dict[str, Any]) -> None:
    ACCEPTANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ACCEPTANCE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(ACCEPTANCE_PATH)


def _required_job(name: str):
    job = next((item for item in public.engine.JOBS if item.name == name), None)
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
    """Publish both requested Discord cards before the engine becomes healthy."""
    connection = public.engine.connect_db()
    results: dict[str, Any] = {}
    try:
        for name in REQUIRED_STARTUP_JOBS:
            job = _required_job(name)
            public.engine.run_job(connection, job)
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
            "verified_at": public.engine.iso_now(),
            "required_jobs": results,
            "contract": (
                "#breaking-alerts heartbeat and #premarket session card were "
                "acknowledged before the engine health port opened"
            ),
        }
        _write_acceptance(payload)
        return payload
    except Exception as exc:
        payload = {
            "status": "FAILED",
            "verified_at": public.engine.iso_now(),
            "required_jobs": results,
            "error": f"{type(exc).__name__}: {exc}",
        }
        _write_acceptance(payload)
        raise
    finally:
        connection.close()


def main() -> int:
    run_required_startup_jobs()
    return public.engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
