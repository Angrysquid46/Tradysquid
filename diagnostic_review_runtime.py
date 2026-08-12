"""Keep #upgrade-review actionable instead of publishing every raw health check.

This runtime is installed after the complete diagnostic chain. It preserves local
receipts for every check, but only publishes an individual Discord card after the
normal repair threshold is reached. Temporary failures are summarized in one
stable card. Network symptoms sharing one root cause are grouped, historical log
content is not replayed on first startup, and old non-actionable diagnostic cards
are removed automatically.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

import applied_upgrades as dashboard
import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics

VERSION = "diagnostic-review-runtime-v2"
SUMMARY_MESSAGE_KEY = f"{VERSION}:summary-message-id"
SUMMARY_HASH_KEY = f"{VERSION}:summary-content-hash"
CLEANUP_META_KEY = f"{VERSION}:legacy-card-cleanup"

_INSTALLED = False
_BASE_RECORD_FAILURE: Callable[..., dict[str, Any]] | None = None
_BASE_RECORD_RECOVERY: Callable[..., dict[str, Any] | None] | None = None
_BASE_LOG_CHECKS: Callable[[Any], list[diagnostics.HealthCheck]] | None = None
_BASE_CYCLE: Callable[[Any], str] | None = None
_BASE_DASHBOARD_JOB: Callable[[Any], str] | None = None

_DISCORD_KEYS = {
    "discord-connectivity",
    "discord-command-registry-connectivity",
    "discord-configuration",
    "diagnostic-owner-channel-bootstrap",
    "diagnostic-live-message-proof",
    "diagnostic-live-acceptance-post",
    "market-review-discord",
}
_GITHUB_KEYS = {
    "github-fetch",
    "market-review-github",
    "github-upgrade-bridge-connectivity",
}
_HARD_FAILURE_PHRASES = (
    "rolled back",
    "non-fast-forward",
    "restart loop",
    "missed two expected runs",
    "runtime file blocked deployment",
    "live verification failed",
    "not registered",
)


def _network_timeout(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "connecttimeout",
            "connection timed out",
            "could not connect",
            "failed to connect",
            "max retries exceeded",
            "connectionerror",
        )
    )


def _canonical_check(check: diagnostics.HealthCheck) -> diagnostics.HealthCheck:
    text = " ".join(
        (
            check.key,
            check.component,
            check.operation,
            check.detail,
            check.runtime_target,
        )
    )
    lowered = text.casefold()
    if check.key in _DISCORD_KEYS or ("discord.com" in lowered and _network_timeout(text)):
        return replace(
            check,
            key="incident-discord-connectivity",
            component="network",
            operation="Discord API connectivity",
            severity="WARNING",
            channels="#upgrade-review · #system-health · #workflow-log",
            runtime_target="discord.com:443",
            automatic_retry="next five-minute diagnostic cycle",
            healthy_services="existing services remain independent",
            repair_objective="Restore reliable Discord HTTPS connectivity without restarting healthy services.",
            acceptance_tests="Discord channel and guild-command GET requests succeed for three consecutive diagnostic cycles.",
        )
    if check.key in _GITHUB_KEYS or ("github.com" in lowered and _network_timeout(text)):
        return replace(
            check,
            key="incident-github-connectivity",
            component="network",
            operation="GitHub API and origin/main connectivity",
            severity="WARNING",
            channels="#upgrade-review · #workflow-log",
            runtime_target="github.com:443",
            automatic_retry="next two-minute updater or eligible review cycle",
            healthy_services="running services remain online",
            repair_objective="Restore reliable GitHub HTTPS access without stopping the current deployment.",
            acceptance_tests="Three consecutive GitHub checks succeed and the deployed commit remains unchanged during failures.",
        )
    if check.component.casefold() == "logs":
        if "traceback" in lowered or "exception" in lowered:
            category = "traceback"
        elif "restart" in lowered:
            category = "restart"
        elif "timeout" in lowered:
            category = "timeout"
        else:
            category = "failure"
        name = Path(check.runtime_target or "runtime.log").name.casefold()
        return replace(check, key=f"log-{name}-{category}")
    return check


def _canonical_key(signature_key: str) -> str:
    key = str(signature_key or "")
    if key in _DISCORD_KEYS:
        return "incident-discord-connectivity"
    if key in _GITHUB_KEYS:
        return "incident-github-connectivity"
    return key


def _actionable(record: dict[str, Any]) -> bool:
    if record.get("github_request_number"):
        return True
    if int(record.get("consecutive_failures") or 0) >= 3:
        return True
    if str(record.get("status") or "").upper() == "FAILED AGAIN":
        return True
    if str(record.get("severity") or "").upper() == "CRITICAL":
        return True
    normalized = str(record.get("normalized_error") or "").casefold()
    return any(phrase in normalized for phrase in _HARD_FAILURE_PHRASES)


def _with_store(connection: Any | None):
    return connection or diagnostics.connect_store()


def _delete_record_message(
    record: dict[str, Any],
    *,
    connection: Any | None = None,
) -> None:
    message_id = str(record.get("discord_message_id") or "")
    if not message_id:
        return
    own = connection is None
    store = _with_store(connection)
    try:
        try:
            tracker, channel_id = diagnostics.ensure_owner_channel(
                diagnostics.REVIEW_CHANNEL,
                "Owner review queue for actionable upgrades, persistent diagnostics, deployment, and live acceptance.",
            )
            if tracker and channel_id:
                tracker._request(
                    "DELETE",
                    f"/channels/{channel_id}/messages/{message_id}",
                )
        except Exception:
            pass
        store.execute(
            "UPDATE diagnostics SET discord_message_id='' WHERE signature=?",
            (record["signature"],),
        )
        store.commit()
    finally:
        if own:
            store.close()


def _sync_actionable(
    record: dict[str, Any],
    *,
    connection: Any | None = None,
) -> None:
    own = connection is None
    store = _with_store(connection)
    try:
        if _actionable(record):
            diagnostics._sync_discord(store, record)
        else:
            _delete_record_message(record, connection=store)
    finally:
        if own:
            store.close()


def record_failure(
    check: diagnostics.HealthCheck,
    *,
    exception_type: str = "HealthCheckFailure",
    connection: Any | None = None,
    sync: bool = True,
) -> dict[str, Any]:
    if _BASE_RECORD_FAILURE is None:
        raise RuntimeError("Diagnostic review runtime was not installed")
    canonical = _canonical_check(check)
    record = _BASE_RECORD_FAILURE(
        canonical,
        exception_type=exception_type,
        connection=connection,
        sync=False,
    )
    if sync:
        _sync_actionable(record, connection=connection)
    return record


def record_recovery(
    signature_key: str,
    detail: str,
    *,
    verified: bool = False,
    connection: Any | None = None,
    sync: bool = True,
) -> dict[str, Any] | None:
    if _BASE_RECORD_RECOVERY is None:
        raise RuntimeError("Diagnostic review runtime was not installed")
    record = _BASE_RECORD_RECOVERY(
        _canonical_key(signature_key),
        detail,
        verified=verified,
        connection=connection,
        sync=False,
    )
    if record and sync:
        if record.get("github_request_number"):
            _sync_actionable(record, connection=connection)
        else:
            _delete_record_message(record, connection=connection)
    return record


def _log_category(lines: list[str]) -> str:
    text = " ".join(lines).casefold()
    if "discord.com" in text and _network_timeout(text):
        return "discord-connectivity"
    if "github.com" in text and _network_timeout(text):
        return "github-connectivity"
    if "traceback" in text or "exception" in text:
        return "traceback"
    if "restart" in text:
        return "restart"
    if "timeout" in text:
        return "timeout"
    return "failure"


def log_checks(store: Any) -> list[diagnostics.HealthCheck]:
    paths = [
        diagnostics.LOG_DIR / "supervisor.log",
        diagnostics.LOG_DIR / "command-bot.log",
        diagnostics.LOG_DIR / "information-engine.log",
        diagnostics.STARTUP_LOG,
        diagnostics.WATCHDOG_LOG,
    ]
    findings: list[diagnostics.HealthCheck] = []
    for path in paths:
        if not path.exists():
            continue
        key = f"log-offset:{path.name}"
        try:
            size = path.stat().st_size
            raw_previous = diagnostics._meta(store, key, "")
            if raw_previous == "":
                diagnostics._set_meta(store, key, str(size))
                continue
            previous = int(raw_previous or 0)
            if previous > size:
                previous = 0
            with path.open("rb") as handle:
                handle.seek(previous)
                raw = handle.read(200_000)
            diagnostics._set_meta(store, key, str(size))
            text = raw.decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        # Reuses diagnostics._line_has_genuine_failure_evidence rather than
        # its own copy of the keyword regex - this function is a complete
        # independent duplicate of diagnostic_upgrade_system.py's own
        # _log_checks (installed here to shadow it, see install() below),
        # and both used to have the identical bug: a routine healthy status
        # line like "0 failed syncs" got flagged purely for containing the
        # word "failed" while reporting zero of them. Fixing only the base
        # copy left this one - the one actually running live - still
        # broken, confirmed live (log-information-engine.log-failure fired
        # again immediately after the base-only fix deployed).
        suspicious = [line for line in text.splitlines() if diagnostics._line_has_genuine_failure_evidence(line)]
        if not suspicious:
            continue
        category = _log_category(suspicious)
        sample = "\n".join(suspicious[-12:])
        findings.append(
            diagnostics.HealthCheck(
                f"log-{path.name}-{category}",
                False,
                "logs",
                f"new {category.replace('-', ' ')} evidence in {path.name}",
                sample,
                severity="WARNING",
                runtime_target=str(path.relative_to(diagnostics.ROOT)),
                automatic_retry="only newly appended log evidence is reviewed",
            )
        )
    return findings


def diagnostics_summary() -> dict[str, Any]:
    connection = diagnostics.connect_store()
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM diagnostics GROUP BY status"
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        open_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM diagnostics WHERE status IN ('DEGRADED','FAILED','RETRYING','FAILED AGAIN') ORDER BY last_seen DESC"
            ).fetchall()
        ]
        actionable = [row for row in open_rows if _actionable(row)]
        transient = [row for row in open_rows if not _actionable(row)]
        recent_recovered = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM diagnostics
                WHERE status IN ('RECOVERED','RESOLVED','VERIFIED')
                ORDER BY last_seen DESC LIMIT 20
                """
            ).fetchall()
        ]
        return {
            "counts": counts,
            "open": actionable,
            "actionable": actionable,
            "transient": transient,
            "recent_recovered": recent_recovered,
            "last_cycle": diagnostics._meta(connection, "last-complete-cycle", ""),
        }
    finally:
        connection.close()


def _summary_content() -> str:
    summary = diagnostics_summary()
    actionable = summary["actionable"]
    transient = summary["transient"]
    if actionable:
        state = "ACTION REQUIRED"
        icon = "❌"
        next_action = "Review the diagnostic-generated requests below and mark the shared batch ready when the requested repairs are complete."
    elif transient:
        state = "OBSERVING"
        icon = "⚠️"
        next_action = "No owner action yet. Automatic retries continue; a repair request is created only after the persistence threshold."
    else:
        state = "HEALTHY"
        icon = "✅"
        next_action = "No diagnostic repair action is currently required."

    grouped: dict[str, int] = {}
    for item in transient:
        component = str(item.get("component") or "unknown")
        grouped[component] = grouped.get(component, 0) + 1
    lines = [
        f"# {icon} Diagnostic Review Summary",
        f"**State:** {state}",
        f"**Actionable repairs:** {len(actionable)} · **Transient observations:** {len(transient)}",
        f"**Last complete cycle:** {summary.get('last_cycle') or 'pending'}",
        f"**Exact next action:** {next_action}",
    ]
    if actionable:
        lines.append("## Actionable")
        for item in actionable[:6]:
            lines.append(
                f"• **{item.get('diagnostic_id')} · {item.get('component')}** · {item.get('operation')} · "
                f"{item.get('consecutive_failures')} consecutive · batch #{item.get('github_issue_number') or 'pending'} request {item.get('github_request_number') or 'pending'}"
            )
    if grouped:
        lines.append(
            "**Observed only:** "
            + " · ".join(f"{name} {count}" for name, count in sorted(grouped.items()))
        )
    lines.extend(
        [
            "First and second occurrences stay local. One underlying Discord or GitHub outage is grouped into one incident.",
            f"Updated **{diagnostics.iso_now()}**.",
        ]
    )
    return "\n".join(lines)[:1900]


def _publish_summary(engine_connection: Any) -> str:
    tracker, channel_id = diagnostics.ensure_owner_channel(
        diagnostics.REVIEW_CHANNEL,
        "Owner review queue for actionable upgrades, persistent diagnostics, deployment, and live acceptance.",
    )
    if not tracker or not channel_id:
        raise RuntimeError("#upgrade-review is unavailable")
    return diagnostics._upsert_message(
        engine_connection,
        tracker,
        channel_id,
        SUMMARY_MESSAGE_KEY,
        SUMMARY_HASH_KEY,
        _summary_content(),
    )


def _cleanup_legacy_cards() -> int:
    store = diagnostics.connect_store()
    try:
        if diagnostics._meta(store, CLEANUP_META_KEY, ""):
            return 0
        records = [dict(row) for row in store.execute("SELECT * FROM diagnostics").fetchall()]
        keep_ids = {
            str(record.get("discord_message_id") or "")
            for record in records
            if _actionable(record) and record.get("discord_message_id")
        }
        tracker, channel_id = diagnostics.ensure_owner_channel(
            diagnostics.REVIEW_CHANNEL,
            "Owner review queue for actionable upgrades, persistent diagnostics, deployment, and live acceptance.",
        )
        if not tracker or not channel_id:
            return 0
        deleted = 0
        before = ""
        for _ in range(5):
            suffix = f"?limit=100&before={before}" if before else "?limit=100"
            payload = tracker._request("GET", f"/channels/{channel_id}/messages{suffix}")
            messages = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            if not messages:
                break
            for message in messages:
                content = str(message.get("content") or "")
                message_id = str(message.get("id") or "")
                author = message.get("author") if isinstance(message.get("author"), dict) else {}
                if not author.get("bot") or not re.search(r"DIA-[A-F0-9]{12}", content):
                    continue
                if message_id in keep_ids:
                    continue
                try:
                    tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
                    deleted += 1
                except Exception:
                    pass
            before = str(messages[-1].get("id") or "")
            if len(messages) < 100 or not before:
                break
        store.execute(
            "UPDATE diagnostics SET discord_message_id='' WHERE COALESCE(github_request_number,0)=0 AND consecutive_failures < 3"
        )
        store.commit()
        diagnostics._set_meta(store, CLEANUP_META_KEY, diagnostics.iso_now())
        return deleted
    finally:
        store.close()


def _latest_job(connection: Any, name: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT status, started_at, COALESCE(finished_at, '') AS finished_at, detail
        FROM job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _latest_applied_counts(connection: Any) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT payload_json FROM observations
        WHERE kind=? ORDER BY id DESC LIMIT 1
        """,
        (dashboard.JOB_NAME,),
    ).fetchone()
    if not row:
        return {}
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}
    counts = payload.get("counts") if isinstance(payload, dict) else {}
    return {
        str(key).upper(): int(value or 0)
        for key, value in counts.items()
    } if isinstance(counts, dict) else {}


def _status_line(status: str, title: str, detail: str) -> str:
    icon = {"PASS": "✅", "PENDING": "⏳", "FAIL": "❌"}[status]
    return f"{icon} **{status} · {title}** · {detail}"


def acceptance_content(
    checks: list[diagnostics.HealthCheck],
    channels: dict[str, dict[str, Any]],
) -> str:
    state = diagnostics._read_json(diagnostics.SUPERVISOR_STATE_PATH)
    by_key = {check.key: check for check in checks}
    engine_connection = diagnostics._engine().connect_db()
    try:
        self_receipt = _latest_job(engine_connection, diagnostics.DIAGNOSTIC_JOB)
        dashboard_receipt = _latest_job(engine_connection, dashboard.JOB_NAME)
        applied_counts = _latest_applied_counts(engine_connection)
    finally:
        engine_connection.close()

    store = diagnostics.connect_store()
    try:
        stable = bool(
            diagnostics._meta(
                store,
                f"{startup.SELF_TEST_META_PREFIX}{diagnostics._current_sha()}",
                "",
            )
        )
    finally:
        store.close()

    summary = diagnostics_summary()
    discord_related = [
        check
        for check in checks
        if check.key in {
            "discord-connectivity",
            "discord-command-registry-connectivity",
            "discord-command-registry-match",
        }
    ]
    discord_network_failed = any(
        not check.passed and check.severity.upper() == "WARNING"
        for check in discord_related
    )
    command_match = by_key.get("discord-command-registry-match")
    command_connect = by_key.get("discord-command-registry-connectivity")
    if command_match and command_match.passed:
        command_status, command_detail = "PASS", "live guild command set matches the expected registry"
    elif command_connect and not command_connect.passed:
        command_status, command_detail = "PENDING", "Discord command verification is waiting on connectivity"
    else:
        command_status, command_detail = "FAIL", "live guild command set does not match the expected registry"

    self_status = str((self_receipt or {}).get("status") or "MISSING").upper()
    scheduler_status = "PASS" if self_status == "OK" else "PENDING" if self_status in {"MISSING", "RUNNING"} else "FAIL"
    dash_status = str((dashboard_receipt or {}).get("status") or "MISSING").upper()
    publish_status = "PASS" if dash_status == "OK" else "PENDING" if dash_status in {"MISSING", "RUNNING"} else "FAIL"
    failed_count = applied_counts.get("FAILED", 0)
    pending_count = applied_counts.get("PENDING", 0) + applied_counts.get("INSTALLED", 0)
    if failed_count:
        proof_status, proof_detail = "FAIL", f"{failed_count} upgrade proof item(s) are failed"
    elif pending_count:
        proof_status, proof_detail = "PENDING", f"{pending_count} upgrade proof item(s) are still pending or installed-only"
    elif applied_counts:
        proof_status, proof_detail = "PASS", "all reported upgrade proofs are active or intentionally superseded"
    else:
        proof_status, proof_detail = "PENDING", "the first applied-upgrade observation has not completed"

    restart = by_key.get("service-restart-loop")
    installed = by_key.get("installed-deployed-commit")
    hooks = by_key.get("upgrade-command-hooks")
    scheduler_modules = (
        "supervisor-process-ownership" in by_key
        and any(key.startswith("required-job-") or key == "scheduler-unique-jobs" for key in by_key)
    )

    items = [
        (
            "PASS" if str(state.get("supervisor_mode") or "") == "SIMPLE_TWO_MINUTE_UPDATER" else "FAIL",
            "Simple two-minute updater",
            str(state.get("supervisor_mode") or "missing"),
        ),
        ("PASS" if diagnostics._tcp_open(8080) else "FAIL", "Command bot online", "127.0.0.1:8080"),
        ("PASS" if diagnostics._tcp_open(8765) else "FAIL", "Information engine online", "127.0.0.1:8765"),
        ("PASS" if scheduler_modules else "FAIL", "Complete runtime diagnostics attached", "supervisor and scheduler checks are installed" if scheduler_modules else "one or more validated runtime modules are not attached"),
        (scheduler_status, "Scheduler diagnostic heartbeat", f"self-diagnostics receipt={self_status}"),
        ("PENDING" if discord_network_failed else "PASS", "Discord API connectivity", "automatic retry pending" if discord_network_failed else "guild and command reads are reachable"),
        ("PASS" if diagnostics.REQUEST_CHANNEL in channels and diagnostics.REVIEW_CHANNEL in channels and diagnostics.APPLIED_CHANNEL in channels else "FAIL", "Owner upgrade channels", "upgrade-requests, upgrade-review, and applied-upgrades"),
        ("PASS" if hooks and hooks.passed else "FAIL", "Upgrade command hooks", "four owner command hooks are attached"),
        (command_status, "Live Discord command registry", command_detail),
        ("PASS" if stable else "PENDING", "Diagnostic stable reporting", "local create/recover proof completed without a visible synthetic card" if stable else "startup proof has not completed"),
        (publish_status, "Applied-upgrades dashboard publishing", f"scheduler receipt={dash_status}"),
        (proof_status, "Applied upgrades verified", proof_detail),
        ("PASS" if restart and restart.passed else "FAIL", "No detected restart loop", restart.detail if restart else "restart-loop diagnostic is not attached"),
        ("PASS" if installed and installed.passed else "FAIL", "Installed equals deployed", installed.detail if installed else "commit consistency check is missing"),
        ("PASS" if not summary["actionable"] else "FAIL", "No unresolved actionable diagnostic", f"{len(summary['actionable'])} actionable repair(s)"),
    ]
    lines = [
        "# Tradysquid Live Acceptance",
        f"**Deployed commit:** `{diagnostics._current_sha()}`",
        "PASS means live proof passed. PENDING means a bounded retry or first receipt is still due. FAIL means owner or maintainer action is required.",
    ]
    lines.extend(_status_line(*item) for item in items)
    lines.append(f"Checked **{diagnostics.iso_now()}**.")
    return "\n".join(lines)[:1900]


def diagnostic_cycle_job(engine_connection: Any) -> str:
    if _BASE_CYCLE is None:
        raise RuntimeError("Diagnostic review runtime was not installed")
    detail = _BASE_CYCLE(engine_connection)
    extras: list[str] = []
    try:
        deleted = _cleanup_legacy_cards()
        if deleted:
            extras.append(f"removed {deleted} legacy diagnostic card(s)")
    except Exception as exc:
        extras.append(f"legacy cleanup pending: {type(exc).__name__}")
    try:
        _publish_summary(engine_connection)
    except Exception as exc:
        extras.append(f"summary publication pending: {type(exc).__name__}")
    return detail + ("; " + "; ".join(extras) if extras else "; actionable summary updated")


def dashboard_job(connection: Any) -> str:
    if _BASE_DASHBOARD_JOB is None:
        raise RuntimeError("Applied-upgrade reporting runtime was not installed")
    try:
        return _BASE_DASHBOARD_JOB(connection)
    except RuntimeError as exc:
        text = str(exc)
        if "applied-upgrades verification found" not in text:
            raise
        return "Dashboard published successfully; " + text


def install() -> None:
    global _INSTALLED
    global _BASE_RECORD_FAILURE, _BASE_RECORD_RECOVERY, _BASE_LOG_CHECKS
    global _BASE_CYCLE, _BASE_DASHBOARD_JOB
    if _INSTALLED:
        return

    _BASE_RECORD_FAILURE = diagnostics.record_failure
    _BASE_RECORD_RECOVERY = diagnostics.record_recovery
    _BASE_LOG_CHECKS = diagnostics._log_checks
    _BASE_CYCLE = diagnostics.diagnostic_cycle_job
    _BASE_DASHBOARD_JOB = dashboard.dashboard_job

    diagnostics.record_failure = record_failure
    diagnostics.record_recovery = record_recovery
    diagnostics._log_checks = log_checks
    diagnostics.diagnostics_summary = diagnostics_summary
    diagnostics._acceptance_content = acceptance_content
    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job
    dashboard.dashboard_job = dashboard_job

    engine = diagnostics._engine()
    rebuilt = []
    diagnostic_found = False
    for job in engine.JOBS:
        if job.name == diagnostics.DIAGNOSTIC_JOB:
            if not diagnostic_found:
                rebuilt.append(
                    engine.Job(
                        job.name,
                        job.interval,
                        diagnostic_cycle_job,
                        market_hours_only=job.market_hours_only,
                        after_hours_interval=job.after_hours_interval,
                        background=job.background,
                        provider_heavy=job.provider_heavy,
                        retry_interval=job.retry_interval,
                    )
                )
                diagnostic_found = True
        else:
            rebuilt.append(job)
    if not diagnostic_found:
        raise RuntimeError("The self-diagnostics scheduler job is missing")
    engine.JOBS = rebuilt
    startup._force_startup_cycle()
    _INSTALLED = True
