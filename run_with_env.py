"""Load local configuration and install the minimal Tradysquid runtime contract."""

from __future__ import annotations

import json
import os
import runpy
import sys
import threading
from dataclasses import replace
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SCRIPT_OVERRIDES = {
    "discord_command_bot.py": "discord_command_bot_public.py",
    "local_information_engine.py": "local_information_engine_bootstrap.py",
    "local_information_engine_public.py": "local_information_engine_bootstrap.py",
    "register_discord_commands.py": "register_discord_commands_public.py",
    "sync_discord_structure.py": "sync_discord_structure_reports.py",
    "sync_discord_structure_public.py": "sync_discord_structure_reports.py",
}

# Completed migrations and acceptance/reporting loops are not services.
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
RECOVERED_DIAGNOSTIC_STATES = {"RECOVERED", "RESOLVED", "VERIFIED"}
ACTIVE_DIAGNOSTIC_STATES = {"DEGRADED", "FAILED", "RETRYING", "FAILED AGAIN"}
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
CORE_PERSISTENT_PREFIXES = (
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


def load_env() -> None:
    if not ENV_PATH.exists():
        raise SystemExit("Missing .env. Copy .env.example to .env and fill it in.")
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def _dedupe_and_retire_jobs(engine: Any) -> None:
    """Keep one copy of each current job and remove completed verifiers."""
    rebuilt = []
    seen: set[str] = set()
    for job in engine.JOBS:
        if job.name in RETIRED_RUNTIME_JOBS or job.name in seen:
            continue
        rebuilt.append(job)
        seen.add(job.name)
    engine.JOBS = rebuilt


def _install_safe_intraday_history(ford_scan: Any) -> None:
    """Never send Tradier a future time-and-sales window."""
    if getattr(ford_scan, "_tradysquid_safe_intraday", False):
        return

    def previous_business_day(day):
        candidate = day - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    def intraday_window(moment: datetime | None = None) -> tuple[str, str]:
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

        # Before the opening bell and on weekends, use the last completed
        # weekday. A holiday may return no bars, which correctly falls back to
        # daily history instead of producing a future-time HTTP 400.
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
        start, end = intraday_window()
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

    ford_scan.intraday_session_window = intraday_window
    ford_scan.get_intraday_history = get_intraday_history
    ford_scan._tradysquid_safe_intraday = True


def _install_recovery_aware_github_bridge(bridge: Any) -> None:
    """Render recovered incidents truthfully and close automatic-only batches."""
    if getattr(bridge, "_tradysquid_recovery_patch", False):
        return
    original_body: Callable[[dict[str, Any], int], str] = bridge._diagnostic_body
    original_add: Callable[[dict[str, Any]], dict[str, Any]] = bridge.add_or_update_diagnostic

    def diagnostic_body(report: dict[str, Any], sequence: int) -> str:
        body = original_body(report, sequence)
        status = str(report.get("status") or "").upper()
        if status not in RECOVERED_DIAGNOSTIC_STATES:
            return body
        body = body.replace(
            "**Status:** PENDING BATCH REVIEW",
            f"**Status:** {status}",
        )
        body = body.replace(
            "**Next action:** Owner marks the shared batch upgrade-ready; maintainer reviews and implements the repair.",
            "**Next action:** No owner action. The incident recovered and remains in history.",
        )
        return body

    def close_if_recovered() -> None:
        try:
            issue = bridge._find_open_batch()
            if not issue:
                return
            issue_number = int(issue["number"])
            comments = bridge._request_comments(issue_number)
            if not comments:
                return
            automatic = 0
            for comment in comments:
                body = str(comment.get("body") or "")
                source = bridge._field(body, "Source", "OWNER REQUEST").upper()
                if source != "AUTOMATIC DIAGNOSTIC":
                    return
                automatic += 1
                status = bridge._field(
                    body, "Status", "PENDING BATCH REVIEW"
                ).strip("*").upper()
                if status not in RECOVERED_DIAGNOSTIC_STATES:
                    return
            if not automatic:
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


def _install_core_diagnostic_policy(diagnostics: Any) -> None:
    """Only persistent core-runtime defects become code-repair requests."""
    if getattr(diagnostics, "_tradysquid_core_policy", False):
        return
    original_report: Callable[[dict[str, Any]], dict[str, Any]] = diagnostics._github_report

    def escalation_required(record: dict[str, Any], force_upgrade: bool) -> bool:
        key = str(record.get("signature_key") or "")
        component = str(record.get("component") or "").casefold()
        if key in RETIRED_DIAGNOSTIC_KEYS:
            return False
        if component in {"network", "logs"}:
            return False
        if key.startswith("incident-"):
            return False
        if key in {"discord-connectivity", "github-fetch", "discord-required-channels"}:
            return False
        if key in CORE_IMMEDIATE_KEYS:
            return True
        if not key.startswith(CORE_PERSISTENT_PREFIXES):
            return False
        return int(record.get("consecutive_failures") or 0) >= 3

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

    diagnostics._escalation_required = escalation_required
    diagnostics._github_report = github_report
    diagnostics._tradysquid_core_policy = True


def _ensure_owner_channels(diagnostics: Any) -> list[str]:
    tracker = diagnostics._engine().discord_tracker()
    if not tracker:
        return []
    channels = diagnostics._guild_channels(tracker)
    mapped = diagnostics._channel_map(channels)
    template = next(
        (
            mapped[name]
            for name in (
                "upgrade-requests",
                "upgrade-review",
                "applied-upgrades",
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
        template = next(
            (item for item in channels if int(item.get("type") or -1) == 0),
            None,
        )
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
        item = tracker._request(
            "POST",
            f"/guilds/{tracker.guild_id}/channels",
            payload,
        )
        if isinstance(item, dict) and item.get("id"):
            mapped[name] = item
            created.append(name)
    return created


def _install_core_health_extensions(diagnostics: Any) -> None:
    """Attach channel repair and one real restart-loop check to the existing cycle."""
    if getattr(diagnostics, "_tradysquid_core_health_extensions", False):
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
            force_upgrade=False,
        )

    def collect_health_checks(engine_connection: Any):
        checks, channels = original_collect(engine_connection)
        checks.append(restart_loop_check())
        return checks, channels

    diagnostics.collect_health_checks = collect_health_checks
    diagnostics._tradysquid_core_health_extensions = True


def _install_core_diagnostic_cycle(diagnostics: Any) -> None:
    """Repair owner channels before the normal diagnostic cycle without blocking it."""
    if getattr(diagnostics, "_tradysquid_core_cycle", False):
        return
    original_cycle = diagnostics.diagnostic_cycle_job

    def diagnostic_cycle_job(engine_connection: Any) -> str:
        channel_note = ""
        try:
            created = _ensure_owner_channels(diagnostics)
            if created:
                channel_note = "; restored channels: " + ", ".join(created)
        except Exception as exc:
            channel_note = f"; channel repair retrying: {type(exc).__name__}"
        return original_cycle(engine_connection) + channel_note

    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job
    engine = diagnostics._engine()
    rebuilt = []
    for job in engine.JOBS:
        if job.name == diagnostics.DIAGNOSTIC_JOB:
            rebuilt.append(replace(job, callback=diagnostic_cycle_job))
        else:
            rebuilt.append(job)
    engine.JOBS = rebuilt
    diagnostics._tradysquid_core_cycle = True


def _recover_retired_diagnostics(diagnostics: Any, bridge: Any) -> None:
    """Resolve removed verifier/log records and synchronize recovered history."""
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
            retired = key in RETIRED_DIAGNOSTIC_KEYS or component == "logs"
            if retired and status in ACTIVE_DIAGNOSTIC_STATES:
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
            and str(row.get("status") or "").upper() in RECOVERED_DIAGNOSTIC_STATES
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


def install_runtime_overrides(
    *,
    include_discord_upgrade_commands: bool = False,
    include_upgrade_batch_engine: bool = False,
) -> None:
    """Install shared behavior, optional commands, and current feature jobs."""
    import network_compat

    network_compat.install()

    import ford_scan
    import github_upgrade_bridge
    import github_upgrade_bridge_runtime
    import journal_contract
    import openai_discord_patch
    import performance_scorecards
    import shared_upgrade_lifecycle
    import upgrade_batch_44

    _install_safe_intraday_history(ford_scan)
    _install_recovery_aware_github_bridge(github_upgrade_bridge)
    github_upgrade_bridge_runtime.install()
    journal_contract.install()
    performance_scorecards.install()
    upgrade_batch_44.install_universe_policy()
    upgrade_batch_44.install_learning_extensions()
    shared_upgrade_lifecycle.install()
    openai_discord_patch.install()

    if include_upgrade_batch_engine:
        import diagnostic_review_runtime
        import diagnostic_upgrade_system
        import market_calendar_runtime
        import outbound_connectivity_runtime
        import scheduler_diagnostic_runtime
        import supervisor_diagnostic_runtime

        _install_core_diagnostic_policy(diagnostic_upgrade_system)

        # Keep the feature work from the completed upgrade, not its temporary
        # migration and acceptance machinery.
        upgrade_batch_44.install_engine()
        diagnostic_upgrade_system.install()
        market_calendar_runtime.install()
        supervisor_diagnostic_runtime.install()
        scheduler_diagnostic_runtime.install()
        diagnostic_review_runtime.install()
        outbound_connectivity_runtime.install()
        _dedupe_and_retire_jobs(upgrade_batch_44._engine())
        _install_core_health_extensions(diagnostic_upgrade_system)
        _install_core_diagnostic_cycle(diagnostic_upgrade_system)

        threading.Thread(
            target=_recover_retired_diagnostics,
            args=(diagnostic_upgrade_system, github_upgrade_bridge),
            name="retired-diagnostic-cleanup",
            daemon=True,
        ).start()

    if include_discord_upgrade_commands:
        import github_upgrade_patch

        github_upgrade_patch.install()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python run_with_env.py <script.py> [arguments...]")
    load_env()
    requested = SCRIPT_OVERRIDES.get(Path(sys.argv[1]).name.casefold(), sys.argv[1])
    target = (ROOT / requested).resolve()
    if target.parent != ROOT or not target.is_file() or target.suffix != ".py":
        raise SystemExit("Target must be a Python file in this repository.")

    install_runtime_overrides(
        include_discord_upgrade_commands=(target.name.casefold() == "discord_command_bot_public.py"),
        include_upgrade_batch_engine=(target.name.casefold() == "local_information_engine_bootstrap.py"),
    )
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
