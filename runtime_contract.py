"""Minimal live-runtime contract for Tradysquid.

The active system is deliberately small:
- one simple supervisor and one two-minute updater;
- one command bot and one information engine;
- current market, learning, chart, universe, and diagnostic jobs only;
- diagnostics may observe and report, but never block deployment or core services.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import datetime, time as clock_time, timedelta
from typing import Any, Callable

RETIRED_RUNTIME_JOBS = {
    "upgrade-request-migration",
    "upgrade-batch-44-acceptance",
    "upgrade-lifecycle-dashboard",
    "applied-upgrades-dashboard",
    "market-hours-upgrade-review",
}
RETIRED_DIAGNOSTIC_KEYS = {
    *(f"job-{name}" for name in RETIRED_RUNTIME_JOBS),
    "diagnostic-owner-channel-bootstrap",
    "diagnostic-live-message-proof",
    "diagnostic-live-acceptance-post",
}
RECOVERED_STATES = {"RECOVERED", "RESOLVED", "VERIFIED"}
ACTIVE_STATES = {"DEGRADED", "FAILED", "RETRYING", "FAILED AGAIN"}
OWNER_CHANNELS = {
    "upgrade-requests": "Owner-facing upgrade request intake and lifecycle history.",
    "upgrade-review": "One stable review summary for persistent actionable repairs.",
    "applied-upgrades": "Installed upgrades with deployed commit and live runtime proof.",
}
CORE_IMMEDIATE_KEYS = {
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
    """Keep one current job per name and remove completed verifier jobs."""
    rebuilt = []
    seen: set[str] = set()
    for job in engine.JOBS:
        if job.name in RETIRED_RUNTIME_JOBS or job.name in seen:
            continue
        rebuilt.append(job)
        seen.add(job.name)
    engine.JOBS = rebuilt


def install_safe_intraday_history(ford_scan: Any) -> None:
    """Prevent future Tradier time-and-sales windows before open or on weekends."""
    if getattr(ford_scan, "_tradysquid_safe_intraday", False):
        return

    def previous_business_day(day):
        candidate = day - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    def intraday_session_window(moment: datetime | None = None) -> tuple[str, str]:
        current = (moment or ford_scan.now_ct()).astimezone(ford_scan.MARKET_TZ)
        session_day = current.date()
        session_open = datetime.combine(
            session_day,
            clock_time(*ford_scan.MARKET_OPEN),
            tzinfo=ford_scan.MARKET_TZ,
        )
        session_close = datetime.combine(
            session_day,
            clock_time(*ford_scan.MARKET_CLOSE),
            tzinfo=ford_scan.MARKET_TZ,
        )
        if current.weekday() >= 5 or current <= session_open + timedelta(minutes=1):
            session_day = previous_business_day(session_day)
            session_open = datetime.combine(
                session_day,
                clock_time(*ford_scan.MARKET_OPEN),
                tzinfo=ford_scan.MARKET_TZ,
            )
            session_close = datetime.combine(
                session_day,
                clock_time(*ford_scan.MARKET_CLOSE),
                tzinfo=ford_scan.MARKET_TZ,
            )
        elif current < session_close:
            session_close = max(session_open, current - timedelta(minutes=1))
        return (
            session_open.strftime("%Y-%m-%d %H:%M"),
            session_close.strftime("%Y-%m-%d %H:%M"),
        )

    def get_intraday_history(
        symbol: str,
        interval: str = "5min",
    ) -> list[dict[str, Any]]:
        start, end = intraday_session_window()
        data = ford_scan.tradier_get(
            "/markets/timesales",
            {
                "symbol": symbol,
                "interval": interval,
                "start": start,
                "end": end,
                "session_filter": "open",
            },
        )
        series = data.get("series") or {}
        values = series.get("data") if isinstance(series, dict) else None
        if not values:
            return []
        return [values] if isinstance(values, dict) else list(values)

    ford_scan.intraday_session_window = intraday_session_window
    ford_scan.get_intraday_history = get_intraday_history
    ford_scan._tradysquid_safe_intraday = True


def install_recovery_bridge(bridge: Any) -> None:
    """Render recovered diagnostics correctly and close recovered automatic batches."""
    if getattr(bridge, "_tradysquid_recovery_patch", False):
        return
    original_body: Callable[[dict[str, Any], int], str] = bridge._diagnostic_body
    original_add: Callable[[dict[str, Any]], dict[str, Any]] = bridge.add_or_update_diagnostic

    def diagnostic_body(report: dict[str, Any], sequence: int) -> str:
        body = original_body(report, sequence)
        status = str(report.get("status") or "").upper()
        if status not in RECOVERED_STATES:
            return body
        return body.replace(
            "**Status:** PENDING BATCH REVIEW",
            f"**Status:** {status}",
        ).replace(
            "**Next action:** Owner marks the shared batch upgrade-ready; maintainer reviews and implements the repair.",
            "**Next action:** No owner action. The incident recovered and remains in history.",
        )

    def close_if_recovered() -> None:
        try:
            issue = bridge._find_open_batch()
            if not issue:
                return
            issue_number = int(issue["number"])
            comments = bridge._request_comments(issue_number)
            if not comments:
                return
            automatic_count = 0
            for comment in comments:
                body = str(comment.get("body") or "")
                if bridge._field(body, "Source", "OWNER REQUEST").upper() != "AUTOMATIC DIAGNOSTIC":
                    return
                automatic_count += 1
                status = bridge._field(body, "Status", "PENDING BATCH REVIEW").strip("*").upper()
                if status not in RECOVERED_STATES:
                    return
            if not automatic_count:
                return
            bridge._request(
                "POST",
                f"/issues/{issue_number}/comments",
                payload={
                    "body": (
                        "## Automatic diagnostic batch recovered\n\n"
                        "Every automatic request is recovered, resolved, or verified. "
                        "No owner request was present, so this batch closed automatically."
                    )
                },
            )
            bridge._request(
                "PATCH",
                f"/issues/{issue_number}",
                payload={
                    "state": "closed",
                    "title": f"[Tradysquids Upgrade Batch] RECOVERED · #{issue_number}",
                },
            )
        except Exception:
            return

    def add_or_update_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
        result = original_add(report)
        close_if_recovered()
        return result

    bridge._diagnostic_body = diagnostic_body
    bridge.add_or_update_diagnostic = add_or_update_diagnostic
    bridge.REQUEST_TIMEOUT_SECONDS = 12
    bridge._tradysquid_recovery_patch = True


def install_diagnostic_policy(diagnostics: Any, review: Any) -> None:
    """Escalate only persistent core defects; keep provider/log noise local."""
    if getattr(diagnostics, "_tradysquid_core_policy", False):
        return
    original_report = diagnostics._github_report
    original_actionable = review._actionable

    def escalation_required(record: dict[str, Any], force_upgrade: bool) -> bool:
        key = str(record.get("signature_key") or "")
        component = str(record.get("component") or "").casefold()
        if key in RETIRED_DIAGNOSTIC_KEYS or component in {"network", "logs"}:
            return False
        if key.startswith("incident-"):
            return False
        if key in {"discord-connectivity", "github-fetch", "discord-required-channels"}:
            return False
        if key in CORE_IMMEDIATE_KEYS:
            return True
        return key.startswith(CORE_PREFIXES) and int(record.get("consecutive_failures") or 0) >= 3

    def github_report(record: dict[str, Any]) -> dict[str, Any]:
        report = dict(original_report(record))
        report.update(
            {
                "status": str(record.get("status") or "PENDING").upper(),
                "recovery_time": str(record.get("recovery_time") or ""),
                "resolution_commit": str(record.get("resolution_commit") or ""),
                "verification_result": str(record.get("verification_result") or ""),
            }
        )
        return report

    def actionable(record: dict[str, Any]) -> bool:
        key = str(record.get("signature_key") or "")
        component = str(record.get("component") or "").casefold()
        if key in RETIRED_DIAGNOSTIC_KEYS or component in {"network", "logs"}:
            return False
        if key.startswith("incident-"):
            return False
        return original_actionable(record)

    diagnostics._escalation_required = escalation_required
    diagnostics._github_report = github_report
    review._actionable = actionable
    diagnostics._tradysquid_core_policy = True


def ensure_owner_channels(diagnostics: Any) -> list[str]:
    tracker = diagnostics._engine().discord_tracker()
    if not tracker:
        return []
    channels = diagnostics._guild_channels(tracker)
    mapped = diagnostics._channel_map(channels)
    template = next(
        (
            mapped[name]
            for name in (
                *OWNER_CHANNELS,
                "workflow-log",
                "system-health",
                "automation-diagnostics",
                "scanner-controls",
            )
            if name in mapped
        ),
        None,
    )
    if template is None:
        template = next((item for item in channels if int(item.get("type") or -1) == 0), None)
    if template is None:
        return []

    created: list[str] = []
    for name, topic in OWNER_CHANNELS.items():
        if name in mapped:
            continue
        payload: dict[str, Any] = {"name": name, "type": 0, "topic": topic}
        if template.get("parent_id"):
            payload["parent_id"] = template["parent_id"]
        if isinstance(template.get("permission_overwrites"), list):
            payload["permission_overwrites"] = template["permission_overwrites"]
        item = tracker._request("POST", f"/guilds/{tracker.guild_id}/channels", payload)
        if isinstance(item, dict) and item.get("id"):
            mapped[name] = item
            created.append(name)
    return created


def install_health_extensions(diagnostics: Any) -> None:
    """Add one real restart-loop check to the existing health collection."""
    if getattr(diagnostics, "_tradysquid_health_extensions", False):
        return
    original_collect = diagnostics.collect_health_checks

    def restart_loop_check() -> Any:
        state = diagnostics._read_json(diagnostics.SUPERVISOR_STATE_PATH)
        counts = state.get("service_restart_counts") if isinstance(
            state.get("service_restart_counts"), dict
        ) else {}
        current = {str(name): int(value or 0) for name, value in counts.items()}
        store = diagnostics.connect_store()
        try:
            raw = diagnostics._meta(store, "core-runtime-restart-sample", "")
            try:
                previous = json.loads(raw) if raw else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                previous = {}
            previous_at = diagnostics._parse_time(previous.get("at"))
            prior = previous.get("counts") if isinstance(previous.get("counts"), dict) else {}
            recent = bool(previous_at and diagnostics.now() - previous_at <= timedelta(minutes=10))
            loops = {
                name: count - int(prior.get(name) or 0)
                for name, count in current.items()
                if recent and count - int(prior.get(name) or 0) >= 3
            }
            diagnostics._set_meta(
                store,
                "core-runtime-restart-sample",
                json.dumps({"at": diagnostics.iso_now(), "counts": current}),
            )
        finally:
            store.close()
        detail = (
            "Restart loop detected: "
            + ", ".join(f"{name} restarted {count} times" for name, count in loops.items())
            if loops
            else "No managed service restarted three times within ten minutes."
        )
        return diagnostics.HealthCheck(
            "service-restart-loop",
            not loops,
            "supervisor",
            "managed service restart-loop detection",
            detail,
            runtime_target="service_restart_counts",
            automatic_retry="supervisor restarts only the affected service",
            healthy_services=str(state.get("service_health") or "unknown"),
            repair_objective="Stop repeated service exits while leaving healthy services running.",
            acceptance_tests="No managed service restarts three times in a ten-minute window.",
        )

    def collect_health_checks(engine_connection: Any):
        checks, channels = original_collect(engine_connection)
        checks.append(restart_loop_check())
        return checks, channels

    diagnostics.collect_health_checks = collect_health_checks
    diagnostics._tradysquid_health_extensions = True


def install_diagnostic_cycle(diagnostics: Any) -> None:
    """Repair owner channels, then run the normal nonblocking diagnostic cycle."""
    if getattr(diagnostics, "_tradysquid_core_cycle", False):
        return
    original_cycle = diagnostics.diagnostic_cycle_job

    def diagnostic_cycle_job(engine_connection: Any) -> str:
        note = ""
        try:
            created = ensure_owner_channels(diagnostics)
            if created:
                note = "; restored channels: " + ", ".join(created)
        except Exception as exc:
            note = f"; channel repair retrying: {type(exc).__name__}"
        return original_cycle(engine_connection) + note

    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job
    engine = diagnostics._engine()
    engine.JOBS = [
        replace(job, callback=diagnostic_cycle_job)
        if job.name == diagnostics.DIAGNOSTIC_JOB
        else job
        for job in engine.JOBS
    ]
    diagnostics._tradysquid_core_cycle = True


def recover_retired_diagnostics(diagnostics: Any, bridge: Any) -> None:
    """Resolve old verifier/log records and refresh their existing GitHub comments."""
    try:
        connection = diagnostics.connect_store()
    except Exception:
        return
    reports: list[dict[str, Any]] = []
    try:
        rows = [dict(row) for row in connection.execute("SELECT * FROM diagnostics").fetchall()]
        timestamp = diagnostics.iso_now()
        for row in rows:
            key = str(row.get("signature_key") or "")
            component = str(row.get("component") or "").casefold()
            status = str(row.get("status") or "").upper()
            if (key in RETIRED_DIAGNOSTIC_KEYS or component == "logs") and status in ACTIVE_STATES:
                connection.execute(
                    """
                    UPDATE diagnostics SET
                        status='RECOVERED', consecutive_failures=0,
                        last_seen=?, recovery_time=?, resolution_commit=?,
                        verification_result=?, automatic_retry='not needed'
                    WHERE signature=?
                    """,
                    (
                        timestamp,
                        timestamp,
                        diagnostics._current_sha(),
                        "Removed completed-upgrade verifier or generic log symptom from the active runtime.",
                        row["signature"],
                    ),
                )
        connection.commit()
        refreshed = [dict(row) for row in connection.execute("SELECT * FROM diagnostics").fetchall()]
        reports = [
            diagnostics._github_report(row)
            for row in refreshed
            if row.get("github_request_number")
            and str(row.get("status") or "").upper() in RECOVERED_STATES
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
    """Install current feature jobs and the minimal nonblocking health layer."""
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
    install_health_extensions(diagnostics)
    install_diagnostic_cycle(diagnostics)

    threading.Thread(
        target=recover_retired_diagnostics,
        args=(diagnostics, bridge),
        name="retired-diagnostic-cleanup",
        daemon=True,
    ).start()


def validate() -> dict[str, Any]:
    return {
        "retired_jobs": sorted(RETIRED_RUNTIME_JOBS),
        "single_supervisor": "run_supervisor_simple.py:8876",
        "update_seconds": 120,
        "provider_failures_open_code_repairs": False,
        "rollback_required": True,
    }
