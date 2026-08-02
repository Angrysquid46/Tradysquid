"""Start the public information engine only after required Discord cards exist.

The supervisor previously treated a live socket as sufficient proof that the
information engine was ready. Required Discord status cards, performance
scorecards, and complete current trade-journal entries must be acknowledged
before the health port opens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import journal_contract
import performance_scorecards
import trade_intelligence

journal_contract.install()
journal_contract.validate_contract()
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
    """Publish and verify required Discord output before engine health opens."""
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

        trade_rows = public.ford_scan.read_log()
        journal_result = {
            "created": 0,
            "refreshed": 0,
            "closed_reviews": 0,
            "verified": 0,
            "entry_snapshots": 0,
            "pending": 0,
        }
        if trade_rows:
            journal_tracker = public.ford_scan.DiscordTracker(
                public.ford_scan.DISCORD_BOT_TOKEN,
                public.ford_scan.DISCORD_GUILD_ID,
            )
            if not journal_tracker.ready:
                raise RuntimeError("Discord tracker is unavailable for journal verification")
            journal_result = public.ford_scan.sync_all_trade_journals(
                trade_rows, journal_tracker
            )
            public.ford_scan.write_log(trade_rows)

        open_unverified = [
            str(row.get("trade_id") or "unknown")
            for row in trade_rows
            if str(row.get("outcome") or "OPEN") == "OPEN"
            and (
                str(row.get("discord_format_version") or "")
                != journal_contract.JOURNAL_FORMAT_VERSION
                or trade_intelligence.needs_sync(row, "journal-contract")
            )
        ]
        if open_unverified:
            raise RuntimeError(
                "Current open journals did not pass the complete entry contract: "
                + ", ".join(open_unverified[:8])
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
            "journal_contract": {
                "format_version": journal_contract.JOURNAL_FORMAT_VERSION,
                "canonical_trades": len(trade_rows),
                "verified_this_startup": journal_result.get("verified", 0),
                "entry_snapshots_found": journal_result.get("entry_snapshots", 0),
                "historical_journals_pending_batched_refresh": journal_result.get(
                    "pending", 0
                ),
                "all_open_journals_verified": True,
            },
            "contract": (
                "#breaking-alerts heartbeat, #premarket session card, daily/weekly/"
                "monthly scorecards, one scorecard per play type, and the complete "
                "entry checklist for every open journal were acknowledged before the "
                "engine health port opened; older historical journals continue through "
                "the bounded automatic repair queue"
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