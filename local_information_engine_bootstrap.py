"""Start the public information engine only after required Discord cards exist.

The supervisor previously treated a live socket as sufficient proof that the
information engine was ready. Required Discord status cards and performance
scorecards must be acknowledged before the health port opens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import performance_scorecards

performance_scorecards.install()
performance_scorecards.validate_reconciliation()

import local_information_engine_public as public


ROOT = Path(__file__).resolve().parent
ACCEPTANCE_PATH = ROOT / "state" / "market-intelligence-startup.json"
REQUIRED_STARTUP_JOBS = (
    "provider-event-queue",
    "premarket-visibility",
    "discord-reporting",
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
    """Publish required Discord cards before the engine becomes healthy."""
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

        report_state = public.ford_scan.read_report_state()
        performance_version = str(
            report_state.get("performance_reconciliation_version") or ""
        )
        if performance_version != performance_scorecards.REPORT_VERSION:
            raise RuntimeError(
                "discord-reporting did not persist the required performance "
                f"scorecard version: {performance_version or 'missing'}"
            )
        if not report_state.get("performance_reconciliation_scorecard_only"):
            raise RuntimeError("discord-reporting did not confirm scorecard-only mode")
        history_pages = int(
            report_state.get("performance_reconciliation_history_pages", -1)
        )
        if history_pages != 0:
            raise RuntimeError(
                f"performance channels still contain history-page output: {history_pages}"
            )

        payload = {
            "status": "PASSED",
            "verified_at": public.engine.iso_now(),
            "required_jobs": results,
            "performance_reconciliation": {
                "version": performance_version,
                "canonical_closed_trades": report_state.get(
                    "performance_reconciliation_closed_trades", 0
                ),
                "daily_scorecards": report_state.get(
                    "performance_reconciliation_daily_reports", 0
                ),
                "weekly_scorecards": report_state.get(
                    "performance_reconciliation_weekly_reports", 0
                ),
                "monthly_scorecards": report_state.get(
                    "performance_reconciliation_monthly_reports", 0
                ),
                "strategy_scorecards": report_state.get(
                    "performance_reconciliation_strategy_groups", 0
                ),
                "history_pages": history_pages,
            },
            "contract": (
                "#breaking-alerts heartbeat, #premarket session card, daily/weekly/"
                "monthly scorecards, and one scorecard per play type were acknowledged "
                "before the engine health port opened"
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
