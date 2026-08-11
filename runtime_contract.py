"""Small, explicit live-runtime contract for Tradysquid.

One supervisor owns one updater, one command bot, and one information engine.
Completed upgrade verifiers are not services. Diagnostics observe and retry but
never block updates or turn provider outages into code defects.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, time as clock_time, timedelta
from typing import Any, Callable

RETIRED_JOBS = {
    "upgrade-request-migration",
    "upgrade-batch-44-acceptance",
    "upgrade-lifecycle-dashboard",
    "applied-upgrades-dashboard",
    "market-hours-upgrade-review",
}
RETIRED_KEYS = {
    *(f"job-{name}" for name in RETIRED_JOBS),
    "diagnostic-owner-channel-bootstrap",
    "diagnostic-live-message-proof",
    "diagnostic-live-acceptance-post",
}
RECOVERED = {"RECOVERED", "RESOLVED", "VERIFIED"}
ACTIVE = {"DEGRADED", "FAILED", "RETRYING", "FAILED AGAIN"}
IMMEDIATE_CORE = {
    "deployment-rollback",
    "git-main-branch",
    "git-tracked-cleanliness",
    "installed-deployed-commit",
}
CORE_PREFIXES = (
    "supervisor-",
    "service-",
    "watchdog-",
    "git-",
    "installed-",
    "deployment-",
    "scheduler-",
    "required-job-",
    "job-",
)


def dedupe_and_retire_jobs(engine: Any) -> None:
    """Keep exactly one current job per name."""
    output = []
    seen: set[str] = set()
    for job in engine.JOBS:
        if job.name in RETIRED_JOBS or job.name in seen:
            continue
        output.append(job)
        seen.add(job.name)
    engine.JOBS = output


def install_safe_intraday_history(spy_scanner: Any) -> None:
    """Never ask Tradier for bars from a future session window."""
    if getattr(spy_scanner, "_tradysquid_safe_intraday", False):
        return

    def previous_weekday(day):
        day -= timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day

    def intraday_session_window(moment: datetime | None = None) -> tuple[str, str]:
        current = (moment or spy_scanner.now_ct()).astimezone(spy_scanner.MARKET_TZ)
        day = current.date()
        start = datetime.combine(
            day, clock_time(*spy_scanner.MARKET_OPEN), tzinfo=spy_scanner.MARKET_TZ
        )
        end = datetime.combine(
            day, clock_time(*spy_scanner.MARKET_CLOSE), tzinfo=spy_scanner.MARKET_TZ
        )
        if current.weekday() >= 5 or current <= start + timedelta(minutes=1):
            day = previous_weekday(day)
            start = datetime.combine(
                day, clock_time(*spy_scanner.MARKET_OPEN), tzinfo=spy_scanner.MARKET_TZ
            )
            end = datetime.combine(
                day, clock_time(*spy_scanner.MARKET_CLOSE), tzinfo=spy_scanner.MARKET_TZ
            )
        elif current < end:
            end = max(start, current - timedelta(minutes=1))
        # Tradier's timesales endpoint interprets naive start/end strings in
        # America/New_York, one hour ahead of MARKET_TZ (America/Chicago) -
        # confirmed live (see spy_scanner._et_window_str). start/end above
        # are correct CT moments; only the string sent to Tradier needs the
        # ET shift, so the "never ask for a future window" logic above is
        # untouched.
        return (
            start.astimezone(spy_scanner.TRADIER_TIMESALES_TZ).strftime("%Y-%m-%d %H:%M"),
            end.astimezone(spy_scanner.TRADIER_TIMESALES_TZ).strftime("%Y-%m-%d %H:%M"),
        )

    def get_intraday_history(symbol: str, interval: str = "5min") -> list[dict[str, Any]]:
        start, end = intraday_session_window()
        payload = spy_scanner.tradier_get(
            "/markets/timesales",
            {
                "symbol": symbol,
                "interval": interval,
                "start": start,
                "end": end,
                "session_filter": "open",
            },
        )
        series = payload.get("series") or {}
        values = series.get("data") if isinstance(series, dict) else None
        if not values:
            return []
        return [values] if isinstance(values, dict) else list(values)

    spy_scanner.intraday_session_window = intraday_session_window
    spy_scanner.get_intraday_history = get_intraday_history
    spy_scanner._tradysquid_safe_intraday = True


def install_recovery_bridge(bridge: Any) -> None:
    """Show recovered diagnostics truthfully and close recovered auto-only batches."""
    if getattr(bridge, "_tradysquid_recovery_patch", False):
        return
    original_body: Callable[[dict[str, Any], int], str] = bridge._diagnostic_body
    original_add: Callable[[dict[str, Any]], dict[str, Any]] = bridge.add_or_update_diagnostic

    def diagnostic_body(report: dict[str, Any], sequence: int) -> str:
        body = original_body(report, sequence)
        status = str(report.get("status") or "").upper()
        if status not in RECOVERED:
            return body
        return body.replace(
            "**Status:** PENDING BATCH REVIEW", f"**Status:** {status}"
        ).replace(
            "**Next action:** Owner marks the shared batch upgrade-ready; maintainer reviews and implements the repair.",
            "**Next action:** No owner action. The incident recovered and remains in history.",
        )

    def close_recovered_batch() -> None:
        try:
            issue = bridge._find_open_batch()
            if not issue:
                return
            number = int(issue["number"])
            comments = bridge._request_comments(number)
            if not comments:
                return
            for comment in comments:
                body = str(comment.get("body") or "")
                if bridge._field(body, "Source", "OWNER REQUEST").upper() != "AUTOMATIC DIAGNOSTIC":
                    return
                status = bridge._field(body, "Status", "PENDING BATCH REVIEW").strip("*").upper()
                if status not in RECOVERED:
                    return
            bridge._request(
                "POST",
                f"/issues/{number}/comments",
                payload={"body": "## Automatic diagnostic batch recovered\n\nAll automatic requests recovered. No owner request was present."},
            )
            bridge._request(
                "PATCH",
                f"/issues/{number}",
                payload={
                    "state": "closed",
                    "title": f"[Tradysquids Upgrade Batch] RECOVERED · #{number}",
                },
            )
        except Exception:
            return

    def add_or_update(report: dict[str, Any]) -> dict[str, Any]:
        result = original_add(report)
        close_recovered_batch()
        return result

    bridge._diagnostic_body = diagnostic_body
    bridge.add_or_update_diagnostic = add_or_update
    bridge.REQUEST_TIMEOUT_SECONDS = 12
    bridge._tradysquid_recovery_patch = True


def install_diagnostic_policy(diagnostics: Any, review: Any) -> None:
    """Only persistent core failures may enter the repair queue."""
    if getattr(diagnostics, "_tradysquid_core_policy", False):
        return
    original_report = diagnostics._github_report
    original_actionable = review._actionable

    def ignored(record: dict[str, Any]) -> bool:
        key = str(record.get("signature_key") or "")
        component = str(record.get("component") or "").casefold()
        return (
            key in RETIRED_KEYS
            or component in {"network", "logs"}
            or key.startswith("incident-")
            or key in {"discord-connectivity", "github-fetch", "discord-required-channels"}
        )

    def escalation(record: dict[str, Any], force_upgrade: bool) -> bool:
        key = str(record.get("signature_key") or "")
        if ignored(record):
            return False
        if key in IMMEDIATE_CORE:
            return True
        return key.startswith(CORE_PREFIXES) and int(record.get("consecutive_failures") or 0) >= 3

    def report(record: dict[str, Any]) -> dict[str, Any]:
        value = dict(original_report(record))
        value.update(
            status=str(record.get("status") or "PENDING").upper(),
            recovery_time=str(record.get("recovery_time") or ""),
            resolution_commit=str(record.get("resolution_commit") or ""),
            verification_result=str(record.get("verification_result") or ""),
        )
        return value

    diagnostics._escalation_required = escalation
    diagnostics._github_report = report
    review._actionable = lambda record: False if ignored(record) else original_actionable(record)
    diagnostics._tradysquid_core_policy = True


def install_live_checks(diagnostics: Any) -> None:
    """Reuse existing channel and restart-loop checks without installing old self-tests."""
    if getattr(diagnostics, "_tradysquid_live_checks", False):
        return
    import diagnostic_startup_runtime as startup

    base_collect = diagnostics.collect_health_checks
    base_cycle = diagnostics.diagnostic_cycle_job

    def collect(connection: Any):
        checks, channels = base_collect(connection)
        checks.append(startup._restart_loop_check())
        return checks, channels

    def cycle(connection: Any) -> str:
        note = ""
        try:
            created = startup._ensure_required_owner_channels()
            if created:
                note = "; restored channels: " + ", ".join(created)
        except Exception as exc:
            note = f"; channel repair retrying: {type(exc).__name__}"
        return base_cycle(connection) + note

    diagnostics.collect_health_checks = collect
    diagnostics.diagnostic_cycle_job = cycle
    diagnostics._engine().JOBS = [
        replace(job, callback=cycle)
        if job.name == diagnostics.DIAGNOSTIC_JOB
        else job
        for job in diagnostics._engine().JOBS
    ]
    diagnostics._tradysquid_live_checks = True


def recover_retired_diagnostics(diagnostics: Any, bridge: Any) -> None:
    """Mark obsolete verifier/log records recovered and update their existing comments."""
    try:
        connection = diagnostics.connect_store()
    except Exception:
        return
    reports: list[dict[str, Any]] = []
    try:
        timestamp = diagnostics.iso_now()
        rows = [dict(row) for row in connection.execute("SELECT * FROM diagnostics").fetchall()]
        for row in rows:
            key = str(row.get("signature_key") or "")
            component = str(row.get("component") or "").casefold()
            if str(row.get("status") or "").upper() not in ACTIVE:
                continue
            if key not in RETIRED_KEYS and component != "logs":
                continue
            connection.execute(
                """
                UPDATE diagnostics SET status='RECOVERED', consecutive_failures=0,
                    last_seen=?, recovery_time=?, resolution_commit=?,
                    verification_result=?, automatic_retry='not needed'
                WHERE signature=?
                """,
                (
                    timestamp,
                    timestamp,
                    diagnostics._current_sha(),
                    "Removed obsolete verifier or generic log symptom from the active runtime.",
                    row["signature"],
                ),
            )
        connection.commit()
        reports = [
            diagnostics._github_report(dict(row))
            for row in connection.execute("SELECT * FROM diagnostics").fetchall()
            if row["github_request_number"]
            and str(row["status"] or "").upper() in RECOVERED
        ]
    except Exception:
        return
    finally:
        connection.close()

    for report in reports:
        try:
            bridge.add_or_update_diagnostic(report)
        except Exception:
            continue


def install_information_engine() -> None:
    """Install current feature jobs plus one nonblocking health layer."""
    import diagnostic_review_runtime as review
    import diagnostic_upgrade_system as diagnostics
    import github_upgrade_bridge as bridge
    import market_calendar_runtime
    import outbound_connectivity_runtime
    import scheduler_diagnostic_runtime
    import supervisor_diagnostic_runtime
    import upgrade_batch_44

    install_diagnostic_policy(diagnostics, review)
    upgrade_batch_44.install_engine()
    diagnostics.install()
    market_calendar_runtime.install()
    supervisor_diagnostic_runtime.install()
    scheduler_diagnostic_runtime.install()
    review.install()
    outbound_connectivity_runtime.install()
    dedupe_and_retire_jobs(upgrade_batch_44._engine())
    install_live_checks(diagnostics)
    threading.Thread(
        target=recover_retired_diagnostics,
        args=(diagnostics, bridge),
        name="retired-diagnostic-cleanup",
        daemon=True,
    ).start()


def validate() -> dict[str, Any]:
    return {
        "retired_jobs": sorted(RETIRED_JOBS),
        "single_supervisor": "run_supervisor_simple.py:8876",
        "update_seconds": 120,
        "provider_failures_open_code_repairs": False,
        "rollback_required": True,
    }
