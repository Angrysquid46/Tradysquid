"""Canonicalize and deduplicate diagnostic findings before local storage.

#upgrade-review was retired along with the rest of the old upgrade-batch
Discord system; this runtime no longer publishes anything there. It keeps
the local classification/dedup logic (grouping shared-root-cause network
symptoms, canonical log categories) that other live modules' retry and
escalation decisions still depend on.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics

VERSION = "diagnostic-review-runtime-v2"

_INSTALLED = False
_BASE_RECORD_FAILURE: Callable[..., dict[str, Any]] | None = None
_BASE_RECORD_RECOVERY: Callable[..., dict[str, Any] | None] | None = None
_BASE_LOG_CHECKS: Callable[[Any], list[diagnostics.HealthCheck]] | None = None
_BASE_CYCLE: Callable[[Any], str] | None = None

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
    # sync/connection kept in the signature for call-site compatibility;
    # Discord posting was removed with #upgrade-review's retirement, so
    # there is nothing left to sync - local tracking (_BASE_RECORD_FAILURE)
    # still runs, which is what other live modules' retry/escalation logic
    # actually depends on.
    return _BASE_RECORD_FAILURE(
        canonical,
        exception_type=exception_type,
        connection=connection,
        sync=False,
    )


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
    return _BASE_RECORD_RECOVERY(
        _canonical_key(signature_key),
        detail,
        verified=verified,
        connection=connection,
        sync=False,
    )


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


def diagnostic_cycle_job(engine_connection: Any) -> str:
    if _BASE_CYCLE is None:
        raise RuntimeError("Diagnostic review runtime was not installed")
    return _BASE_CYCLE(engine_connection)


def install() -> None:
    global _INSTALLED
    global _BASE_RECORD_FAILURE, _BASE_RECORD_RECOVERY, _BASE_LOG_CHECKS
    global _BASE_CYCLE
    if _INSTALLED:
        return

    _BASE_RECORD_FAILURE = diagnostics.record_failure
    _BASE_RECORD_RECOVERY = diagnostics.record_recovery
    _BASE_LOG_CHECKS = diagnostics._log_checks
    _BASE_CYCLE = diagnostics.diagnostic_cycle_job

    diagnostics.record_failure = record_failure
    diagnostics.record_recovery = record_recovery
    diagnostics._log_checks = log_checks
    diagnostics.diagnostics_summary = diagnostics_summary
    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job

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
