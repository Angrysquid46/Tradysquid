"""Tradysquid self-diagnostics, shared upgrade escalation, and live verification.

Diagnostics are runtime observers, never deployment gates. Persistent defects are
added to the same GitHub upgrade batch used by `/upgrade-add`; this module never
edits code, creates pull requests, merges, approves, deploys, or restarts healthy
services.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import time
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Any, Iterable

import market_data
import github_upgrade_bridge as bridge
import upgrade_batch_44

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "diagnostics.db"
SUPERVISOR_STATE_PATH = ROOT / "state" / "supervisor-state.json"
LOG_DIR = ROOT / "state" / "supervisor-logs"
WATCHDOG_LOG = ROOT / "state" / "supervisor-watchdog.log"
STARTUP_LOG = ROOT / "state" / "supervisor-startup.log"
REVIEW_CHANNEL = "upgrade-review"
REQUEST_CHANNEL = "upgrade-requests"
APPLIED_CHANNEL = "applied-upgrades"
DIAGNOSTIC_JOB = "self-diagnostics"
MARKET_REVIEW_JOB = "market-hours-upgrade-review"
VERSION = "diagnostic-upgrade-system-v1"
REVIEW_MESSAGE_KEY = f"{VERSION}:review-message-id"
REVIEW_HASH_KEY = f"{VERSION}:review-hash"
ACCEPTANCE_MESSAGE_KEY = f"{VERSION}:acceptance-message-id"
ACCEPTANCE_HASH_KEY = f"{VERSION}:acceptance-hash"
MARKET_REVIEW_LAST_KEY = f"{VERSION}:last-market-review"
INSTALLED_SHA_KEY = f"{VERSION}:installed-sha"

REQUIRED_CHANNELS = (
    REQUEST_CHANNEL,
    REVIEW_CHANNEL,
    APPLIED_CHANNEL,
    "workflow-log",
    "system-health",
    "system-activity",
)
CORE_PORTS = {
    "command-bot": 8080,
    "information-engine": 8765,
    "supervisor": 8876,
    "ngrok": 4040,
}
ACTIVE_FAILURE_STATES = {"DEGRADED", "FAILED", "RETRYING", "FAILED AGAIN"}
RECOVERED_STATES = {"RECOVERED", "RESOLVED", "VERIFIED"}
_INSTALLED = False


@dataclass(frozen=True)
class HealthCheck:
    key: str
    passed: bool
    component: str
    operation: str
    detail: str
    severity: str = "ERROR"
    channels: str = ""
    runtime_target: str = ""
    automatic_retry: str = "active"
    healthy_services: str = "unknown"
    repair_objective: str = "Repair the repeatable defect without restarting unrelated healthy services."
    acceptance_tests: str = "Reproduce the failure, deploy the repair, and require passing live verification."
    force_upgrade: bool = False


def _engine() -> Any:
    return upgrade_batch_44._engine()


def now() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return now().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now().tzinfo)
    return parsed


def connect_store() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS diagnostics (
            signature TEXT PRIMARY KEY,
            diagnostic_id TEXT NOT NULL,
            signature_key TEXT NOT NULL,
            severity TEXT NOT NULL,
            component TEXT NOT NULL,
            operation TEXT NOT NULL,
            exception_type TEXT NOT NULL DEFAULT '',
            normalized_error TEXT NOT NULL,
            channels TEXT NOT NULL DEFAULT '',
            runtime_target TEXT NOT NULL DEFAULT '',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            total_failures INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            deployed_commit TEXT NOT NULL DEFAULT '',
            last_working_commit TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            discord_message_id TEXT NOT NULL DEFAULT '',
            github_issue_number INTEGER,
            github_request_number INTEGER,
            github_comment_id INTEGER,
            github_sync_status TEXT NOT NULL DEFAULT '',
            recovery_time TEXT NOT NULL DEFAULT '',
            resolution_commit TEXT NOT NULL DEFAULT '',
            verification_result TEXT NOT NULL DEFAULT '',
            automatic_retry TEXT NOT NULL DEFAULT '',
            healthy_services TEXT NOT NULL DEFAULT '',
            steps_attempted TEXT NOT NULL DEFAULT '',
            repair_objective TEXT NOT NULL DEFAULT '',
            acceptance_tests TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS diagnostics_status_time
            ON diagnostics(status, last_seen DESC);
        CREATE TABLE IF NOT EXISTS diagnostic_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    return connection


def _meta(connection: sqlite3.Connection, key: str, default: str = "") -> str:
    row = connection.execute(
        "SELECT value FROM diagnostic_meta WHERE key=?", (key,)
    ).fetchone()
    return str(row["value"]) if row else default


def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO diagnostic_meta(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, value, iso_now()),
    )
    connection.commit()


def _current_sha() -> str:
    state = _read_json(SUPERVISOR_STATE_PATH)
    value = str(state.get("deployed_sha") or state.get("local_sha") or "").strip()
    if value:
        return value[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _configured_secrets() -> list[str]:
    names = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|WEBHOOK|AUTH)", re.I)
    return sorted(
        {
            value.strip()
            for key, value in os.environ.items()
            if names.search(key) and value and len(value.strip()) >= 6
        },
        key=len,
        reverse=True,
    )


def redact(value: Any) -> str:
    text = str(value or "")
    for secret in _configured_secrets():
        text = text.replace(secret, "[REDACTED]")
    patterns = (
        (r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
        (r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer [REDACTED]"),
        (r"(?i)bot\s+[A-Za-z0-9._~+\-/=]+", "Bot [REDACTED]"),
        (r"\bgithub_pat_[A-Za-z0-9_]+\b", "[REDACTED_GITHUB_TOKEN]"),
        (r"\bgh[opusr]_[A-Za-z0-9]+\b", "[REDACTED_GITHUB_TOKEN]"),
        (r"\bsk-(?:proj-)?[A-Za-z0-9_-]+\b", "[REDACTED_API_KEY]"),
        (r"https://discord(?:app)?\.com/api/webhooks/\d+/[^\s]+", "[REDACTED_DISCORD_WEBHOOK]"),
        (r"(?i)(token|secret|password|api[_ -]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def normalize_error(value: Any) -> str:
    text = redact(value)
    replacements = (
        (r"\b20\d{2}-\d{2}-\d{2}[T ][0-9:.+\-Z]+\b", "<timestamp>"),
        (r"\b0x[0-9a-fA-F]+\b", "<address>"),
        (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b", "<uuid>"),
        (r"(?i)request[_ -]?id[=: ]+[A-Za-z0-9_-]+", "request_id=<id>"),
        (r"(?i)line\s+\d+", "line <n>"),
        (r"[A-Za-z]:\\[^\n\r\t\"']*?Tradysquid-main", "<repo>"),
        (r"/home/[^\s]+/Tradysquid", "<repo>"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return " ".join(text.split())[:2000]


def diagnostic_signature(signature_key: str) -> str:
    stable = " ".join(str(signature_key or "unknown").casefold().split())
    return hashlib.sha256(f"tradysquid-diagnostic-v1|{stable}".encode()).hexdigest()


def diagnostic_id(signature: str) -> str:
    return f"DIA-{signature[:12].upper()}"


def _row(connection: sqlite3.Connection, signature: str) -> dict[str, Any] | None:
    item = connection.execute(
        "SELECT * FROM diagnostics WHERE signature=?", (signature,)
    ).fetchone()
    return dict(item) if item else None


def _safe_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)[:12000]


def _escalation_required(record: dict[str, Any], force_upgrade: bool) -> bool:
    if force_upgrade:
        return True
    if int(record.get("consecutive_failures") or 0) >= 3:
        return True
    normalized = str(record.get("normalized_error") or "").casefold()
    return any(
        phrase in normalized
        for phrase in (
            "rolled back",
            "non-fast-forward",
            "restart loop",
            "missed two expected runs",
            "runtime file blocked deployment",
            "live verification failed",
        )
    )


def _github_report(record: dict[str, Any]) -> dict[str, Any]:
    evidence = json.loads(str(record.get("evidence_json") or "{}"))
    return {
        "title": f"Repair {record['component']}: {record['operation']}",
        "signature": record["signature"],
        "diagnostic_id": record["diagnostic_id"],
        "severity": record["severity"],
        "component": record["component"],
        "operation": record["operation"],
        "channels": record.get("channels") or "",
        "runtime_target": record.get("runtime_target") or "",
        "first_seen": record["first_seen"],
        "last_seen": record["last_seen"],
        "consecutive_failures": record["consecutive_failures"],
        "total_failures": record["total_failures"],
        "deployed_commit": record.get("deployed_commit") or "",
        "last_working_commit": record.get("last_working_commit") or "",
        "automatic_retry": record.get("automatic_retry") or "",
        "healthy_services": record.get("healthy_services") or "",
        "evidence": redact(evidence.get("detail") or record.get("normalized_error") or ""),
        "steps_attempted": record.get("steps_attempted") or "",
        "repair_objective": record.get("repair_objective") or "",
        "acceptance_tests": record.get("acceptance_tests") or "",
    }


def _guild_channels(tracker: Any) -> list[dict[str, Any]]:
    payload = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    return [item for item in payload if isinstance(payload, list) and isinstance(item, dict)]


def _channel_map(channels: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name") or "").casefold(): item
        for item in channels
        if item.get("name") and item.get("id")
    }


def ensure_owner_channel(name: str, topic: str) -> tuple[Any | None, str]:
    tracker = _engine().discord_tracker()
    if not tracker:
        return None, ""
    channels = _guild_channels(tracker)
    mapped = _channel_map(channels)
    existing = mapped.get(name.casefold())
    if existing:
        return tracker, str(existing["id"])
    sibling = mapped.get(REQUEST_CHANNEL) or mapped.get(REVIEW_CHANNEL)
    payload: dict[str, Any] = {"name": name, "type": 0, "topic": topic[:1024]}
    if sibling:
        if sibling.get("parent_id"):
            payload["parent_id"] = sibling["parent_id"]
        if isinstance(sibling.get("permission_overwrites"), list):
            payload["permission_overwrites"] = sibling["permission_overwrites"]
    created = tracker._request("POST", f"/guilds/{tracker.guild_id}/channels", payload)
    return tracker, str((created or {}).get("id") or "")


def _render_record(record: dict[str, Any]) -> str:
    evidence = json.loads(str(record.get("evidence_json") or "{}"))
    icon = {
        "DEGRADED": "⚠️",
        "FAILED": "❌",
        "RETRYING": "🔄",
        "FAILED AGAIN": "❌",
        "RECOVERED": "✅",
        "RESOLVED": "✅",
        "VERIFIED": "✅",
    }.get(str(record.get("status") or ""), "ℹ️")
    return "\n".join(
        [
            f"## {icon} {record['diagnostic_id']} · {record['component']}",
            f"**Status:** {record['status']} · **Severity:** {record['severity']}",
            f"**Operation:** {record['operation']}",
            f"**Runtime target:** {record.get('runtime_target') or 'Not identified'}",
            f"**Affected channels:** {record.get('channels') or 'None identified'}",
            f"**First / latest:** {record['first_seen']} · {record['last_seen']}",
            f"**Failures:** {record['consecutive_failures']} consecutive · {record['total_failures']} total",
            f"**Commit:** `{record.get('deployed_commit') or 'unknown'}` · **last working:** `{record.get('last_working_commit') or 'unknown'}`",
            f"**Healthy services:** {record.get('healthy_services') or 'unknown'} · **automatic retry:** {record.get('automatic_retry') or 'unknown'}",
            "### Sanitized evidence",
            f"```text\n{redact(evidence.get('detail') or record.get('normalized_error') or '')[:900]}\n```",
            f"**Repair objective:** {record.get('repair_objective') or 'Identify and repair the defect.'}",
            f"**GitHub batch request:** #{record.get('github_issue_number') or 'pending'} / {record.get('github_request_number') or 'pending'}",
            f"**Next action:** {'Mark the shared batch upgrade-ready for maintainer review.' if record.get('github_request_number') else 'Automatic retries continue; persistent failures will enter the shared upgrade batch.'}",
            (
                f"**Recovery:** {record.get('recovery_time')} · {record.get('verification_result')}"
                if record.get("recovery_time")
                else ""
            ),
        ]
    )[:1900]


def _sync_discord(connection: sqlite3.Connection, record: dict[str, Any]) -> bool:
    try:
        tracker, channel_id = ensure_owner_channel(
            REVIEW_CHANNEL,
            "Owner review queue for upgrade requests, diagnostics, failures, recovery, and exact next actions.",
        )
        if not tracker or not channel_id:
            return False
        payload = {"content": _render_record(record), "allowed_mentions": {"parse": []}}
        message_id = str(record.get("discord_message_id") or "")
        if message_id:
            try:
                tracker._request(
                    "PATCH", f"/channels/{channel_id}/messages/{message_id}", payload
                )
                return True
            except Exception:
                message_id = ""
        created = tracker._request("POST", f"/channels/{channel_id}/messages", payload)
        message_id = str((created or {}).get("id") or "")
        if not message_id:
            return False
        connection.execute(
            "UPDATE diagnostics SET discord_message_id=? WHERE signature=?",
            (message_id, record["signature"]),
        )
        connection.commit()
        return True
    except Exception:
        return False


def record_failure(
    check: HealthCheck,
    *,
    exception_type: str = "HealthCheckFailure",
    connection: sqlite3.Connection | None = None,
    sync: bool = True,
) -> dict[str, Any]:
    own = connection is None
    connection = connection or connect_store()
    try:
        signature = diagnostic_signature(check.key)
        existing = _row(connection, signature)
        previous_status = str((existing or {}).get("status") or "")
        status = "FAILED AGAIN" if previous_status in RECOVERED_STATES else (
            "DEGRADED" if check.severity.upper() in {"INFO", "WARNING"} else "FAILED"
        )
        first_seen = str((existing or {}).get("first_seen") or iso_now())
        consecutive = int((existing or {}).get("consecutive_failures") or 0) + 1
        total = int((existing or {}).get("total_failures") or 0) + 1
        state = _read_json(SUPERVISOR_STATE_PATH)
        deployed = str(state.get("deployed_sha") or state.get("local_sha") or _current_sha())[:12]
        last_working = str(
            state.get("last_known_working_sha")
            or state.get("last_working_sha")
            or (existing or {}).get("last_working_commit")
            or ""
        )[:12]
        normalized = normalize_error(check.detail)
        evidence = _safe_json({"detail": redact(check.detail), "checked_at": iso_now()})
        values = {
            "signature": signature,
            "diagnostic_id": diagnostic_id(signature),
            "signature_key": check.key,
            "severity": check.severity.upper(),
            "component": check.component,
            "operation": check.operation,
            "exception_type": exception_type,
            "normalized_error": normalized,
            "channels": check.channels,
            "runtime_target": check.runtime_target,
            "first_seen": first_seen,
            "last_seen": iso_now(),
            "consecutive_failures": consecutive,
            "total_failures": total,
            "status": status,
            "deployed_commit": deployed,
            "last_working_commit": last_working,
            "evidence_json": evidence,
            "discord_message_id": str((existing or {}).get("discord_message_id") or ""),
            "github_issue_number": (existing or {}).get("github_issue_number"),
            "github_request_number": (existing or {}).get("github_request_number"),
            "github_comment_id": (existing or {}).get("github_comment_id"),
            "github_sync_status": str((existing or {}).get("github_sync_status") or ""),
            "recovery_time": "",
            "resolution_commit": "",
            "verification_result": "",
            "automatic_retry": check.automatic_retry,
            "healthy_services": check.healthy_services,
            "steps_attempted": "Repeated health checks and bounded automatic retry.",
            "repair_objective": check.repair_objective,
            "acceptance_tests": check.acceptance_tests,
        }
        columns = list(values)
        connection.execute(
            f"""
            INSERT INTO diagnostics({','.join(columns)})
            VALUES ({','.join('?' for _ in columns)})
            ON CONFLICT(signature) DO UPDATE SET
                severity=excluded.severity,
                component=excluded.component,
                operation=excluded.operation,
                exception_type=excluded.exception_type,
                normalized_error=excluded.normalized_error,
                channels=excluded.channels,
                runtime_target=excluded.runtime_target,
                last_seen=excluded.last_seen,
                consecutive_failures=excluded.consecutive_failures,
                total_failures=excluded.total_failures,
                status=excluded.status,
                deployed_commit=excluded.deployed_commit,
                last_working_commit=excluded.last_working_commit,
                evidence_json=excluded.evidence_json,
                recovery_time='',
                resolution_commit='',
                verification_result='',
                automatic_retry=excluded.automatic_retry,
                healthy_services=excluded.healthy_services,
                steps_attempted=excluded.steps_attempted,
                repair_objective=excluded.repair_objective,
                acceptance_tests=excluded.acceptance_tests
            """,
            tuple(values[column] for column in columns),
        )
        connection.commit()
        record = _row(connection, signature) or values

        if _escalation_required(record, check.force_upgrade):
            try:
                result = bridge.add_or_update_diagnostic(_github_report(record))
                connection.execute(
                    """
                    UPDATE diagnostics SET
                        github_issue_number=?, github_request_number=?,
                        github_comment_id=?, github_sync_status='OK'
                    WHERE signature=?
                    """,
                    (
                        result.get("issue_number"),
                        result.get("request_number"),
                        result.get("comment_id"),
                        signature,
                    ),
                )
                connection.commit()
                record = _row(connection, signature) or record
            except Exception as exc:
                connection.execute(
                    "UPDATE diagnostics SET github_sync_status=? WHERE signature=?",
                    (f"FAILED: {normalize_error(exc)[:300]}", signature),
                )
                connection.commit()
                record = _row(connection, signature) or record
        if sync:
            _sync_discord(connection, record)
        return record
    finally:
        if own:
            connection.close()


def record_recovery(
    signature_key: str,
    detail: str,
    *,
    verified: bool = False,
    connection: sqlite3.Connection | None = None,
    sync: bool = True,
) -> dict[str, Any] | None:
    own = connection is None
    connection = connection or connect_store()
    try:
        signature = diagnostic_signature(signature_key)
        existing = _row(connection, signature)
        if not existing or str(existing.get("status")) not in ACTIVE_FAILURE_STATES:
            return existing
        status = "VERIFIED" if verified else "RECOVERED"
        timestamp = iso_now()
        connection.execute(
            """
            UPDATE diagnostics SET
                status=?, consecutive_failures=0, last_seen=?, recovery_time=?,
                resolution_commit=?, verification_result=?, automatic_retry='not needed'
            WHERE signature=?
            """,
            (status, timestamp, timestamp, _current_sha(), redact(detail)[:1000], signature),
        )
        connection.commit()
        record = _row(connection, signature)
        if record and record.get("github_request_number"):
            try:
                bridge.add_or_update_diagnostic(_github_report(record))
            except Exception:
                pass
        if record and sync:
            _sync_discord(connection, record)
        return record
    finally:
        if own:
            connection.close()


def _tcp_open(port: int, *, attempts: int = 3, retry_delay: float = 0.5) -> bool:
    """The supervisor's own lock port (tradysquid_supervisor.py's
    acquire_instance_lock) is a pure single-instance mutex with a
    deliberately tiny listen(1) backlog - it never calls accept(), so at
    most one probe's connection can sit in that backlog at a time.
    Confirmed live: this system has several independent, uncoordinated
    probers of that same port (this 5-minute diagnostic cycle, the
    2-minute Startup-folder watchdog loop, etc.), so a probe that loses
    the race for that single slot gets a genuine (if transient) OSError
    even though the service is completely healthy - not a bug in this
    check's logic, a real backlog race between multiple health-checkers.
    A short retry absorbs that without masking an actually-down service,
    which would fail every attempt, not just the first."""
    for attempt in range(attempts):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            if attempt < attempts - 1:
                time.sleep(retry_delay)
    return False


def _run_git(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return result.returncode, (result.stdout or result.stderr or "").strip()


def _watchdog_check() -> HealthCheck:
    if os.name != "nt":
        return HealthCheck(
            "watchdog-platform",
            True,
            "watchdog",
            "scheduled watchdog",
            "Windows watchdog validation is not applicable on this platform.",
            severity="INFO",
        )
    script = """
$tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {$_.TaskName -match 'Tradysquid'}
if (-not $tasks) { exit 2 }
$tasks | ForEach-Object {
  $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue
  Write-Output ("{0}|{1}|{2}" -f $_.TaskName,$_.State,$info.LastTaskResult)
}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return HealthCheck(
            "watchdog-task",
            False,
            "watchdog",
            "scheduled watchdog",
            f"Watchdog inspection failed: {exc}",
            runtime_target="ENSURE-SUPERVISOR.ps1",
        )
    output = (result.stdout or result.stderr or "").strip()
    return HealthCheck(
        "watchdog-task",
        result.returncode == 0 and bool(output),
        "watchdog",
        "scheduled watchdog",
        output or "No Tradysquid watchdog task was found.",
        runtime_target="ENSURE-SUPERVISOR.ps1",
        acceptance_tests="Scheduled watchdog exists, last result is healthy, and stale heartbeat recovery is controlled.",
    )


def _supervisor_checks(state: dict[str, Any]) -> list[HealthCheck]:
    heartbeat = _parse_time(state.get("supervisor_heartbeat_at"))
    fresh = bool(heartbeat and now() - heartbeat <= timedelta(minutes=5))
    mode = str(state.get("supervisor_mode") or "UNKNOWN")
    services = state.get("service_health") if isinstance(state.get("service_health"), dict) else {}
    healthy_summary = ", ".join(f"{key}={value}" for key, value in services.items()) or "unknown"
    return [
        HealthCheck(
            "supervisor-heartbeat",
            fresh,
            "supervisor",
            "heartbeat freshness",
            f"heartbeat={state.get('supervisor_heartbeat_at', 'missing')}; mode={mode}",
            runtime_target="run_supervisor_simple.py",
            healthy_services=healthy_summary,
            acceptance_tests="Supervisor heartbeat is newer than five minutes and only one health-lock owner exists.",
        ),
        HealthCheck(
            "supervisor-mode",
            mode == "SIMPLE_TWO_MINUTE_UPDATER",
            "supervisor",
            "active entrypoint",
            f"Expected SIMPLE_TWO_MINUTE_UPDATER, found {mode}.",
            runtime_target="START-SUPERVISOR.cmd → run_supervisor_simple.py",
            healthy_services=healthy_summary,
            force_upgrade=bool(mode and mode != "SIMPLE_TWO_MINUTE_UPDATER"),
        ),
        _watchdog_check(),
    ]


def _service_checks(state: dict[str, Any]) -> list[HealthCheck]:
    services = state.get("service_health") if isinstance(state.get("service_health"), dict) else {}
    results: list[HealthCheck] = []
    for name, port in CORE_PORTS.items():
        open_now = _tcp_open(port)
        optional = name == "ngrok" and not any(
            (ROOT / candidate).exists() for candidate in ("ngrok.exe",)
        )
        passed = open_now or optional
        results.append(
            HealthCheck(
                f"service-{name}",
                passed,
                name,
                f"health port {port}",
                f"port {port} {'is listening' if open_now else 'is not listening'}; supervisor state={services.get(name, 'unknown')}",
                severity="WARNING" if optional else "ERROR",
                runtime_target=f"127.0.0.1:{port}",
                automatic_retry="supervisor retries the affected service",
                healthy_services=str(services),
                repair_objective=f"Restore {name} without restarting unrelated healthy services.",
            )
        )
    return results


def _meaningfully_dirty(raw_status: str) -> str:
    """Runtime-mutable files (docs/index.html, the chart images,
    config/scanner.json, state/**) constantly drift on a live-running
    system and are already explicitly allowlisted as safe-to-be-dirty in
    the real deploy logic (tradysquid_supervisor.runtime_mutable) - this
    check was flagging them anyway, alarming on something that never
    actually blocks a deploy. Filter them out before deciding."""
    import tradysquid_supervisor as supervisor

    kept_lines = []
    for line in raw_status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if not supervisor.runtime_mutable(path.replace("\\", "/")):
            kept_lines.append(line)
    return "\n".join(kept_lines)


def _git_checks(state: dict[str, Any]) -> list[HealthCheck]:
    branch_code, branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    status_code, raw_dirty = _run_git("status", "--porcelain", "--untracked-files=no")
    dirty = _meaningfully_dirty(raw_dirty) if status_code == 0 else raw_dirty
    fetch_status = str(state.get("last_fetch_status") or "UNKNOWN").upper()
    fetch_detail = str(state.get("last_fetch_detail") or "")
    local = str(state.get("local_sha") or _current_sha())[:12]
    deployed = str(state.get("deployed_sha") or "")[:12]
    remote = str(state.get("last_remote_sha") or "")[:12]
    checks = [
        HealthCheck(
            "git-main-branch",
            branch_code == 0 and branch == "main",
            "updater",
            "current Git branch",
            f"branch={branch or 'unknown'}",
            runtime_target="Git checkout",
            force_upgrade=branch_code == 0 and branch not in {"", "main"},
        ),
        HealthCheck(
            "git-tracked-cleanliness",
            status_code == 0 and not dirty,
            "updater",
            "tracked working-tree cleanliness",
            dirty or "Tracked source files are clean.",
            runtime_target="git status --porcelain --untracked-files=no",
            repair_objective="Remove generated files from tracking or preserve intentional source changes before deployment.",
            force_upgrade=bool(dirty),
        ),
        HealthCheck(
            "github-fetch",
            fetch_status in {"OK", "UNKNOWN"},
            "updater",
            "two-minute origin/main fetch",
            f"status={fetch_status}; mode={state.get('last_fetch_mode', 'unknown')}; {fetch_detail}",
            severity="WARNING",
            channels="#workflow-log and #upgrade-review",
            runtime_target="run_supervisor_simple.fetch_remote_sha",
            automatic_retry="next two-minute updater interval",
            acceptance_tests="One temporary timeout remains DEGRADED; repeated failures update one report and recover without service restart.",
        ),
        HealthCheck(
            "installed-deployed-commit",
            bool(local and deployed and local == deployed),
            "updater",
            "installed commit consistency",
            f"local={local or 'unknown'}; deployed={deployed or 'unknown'}; remote={remote or 'unknown'}",
            runtime_target="supervisor-state.json",
        ),
    ]
    update_status = str(state.get("last_update_status") or "").upper()
    if update_status in {"ROLLED_BACK", "VALIDATION_FAILED", "MERGE_FAILED"}:
        checks.append(
            HealthCheck(
                "deployment-rollback",
                False,
                "updater",
                "deployment validation and rollback",
                f"status={update_status}; {state.get('last_update_detail', '')}",
                runtime_target="tradysquid_supervisor.deploy_if_needed",
                force_upgrade=True,
                acceptance_tests="Repair passes focused tests, installs by fast-forward, restarts once, and passes live acceptance.",
            )
        )
    return checks


def _discord_checks() -> tuple[list[HealthCheck], dict[str, dict[str, Any]]]:
    tracker = _engine().discord_tracker()
    if not tracker:
        return [
            HealthCheck(
                "discord-configuration",
                False,
                "Discord",
                "bot configuration",
                "Discord tracker is unavailable or credentials are not configured.",
                channels="#upgrade-review",
                runtime_target="DiscordTracker",
            )
        ], {}
    try:
        channels = _channel_map(_guild_channels(tracker))
    except Exception as exc:
        return [
            HealthCheck(
                "discord-connectivity",
                False,
                "Discord",
                "guild channel API",
                f"{type(exc).__name__}: {exc}",
                channels="#upgrade-review",
                runtime_target="GET /guilds/{guild}/channels",
                severity="WARNING",
                automatic_retry="next five-minute diagnostic cycle",
            )
        ], {}
    missing = [name for name in REQUIRED_CHANNELS if name not in channels]
    hooks = False
    try:
        hooks = all(
            marker in (ROOT / "github_upgrade_patch.py").read_text(encoding="utf-8")
            for marker in ("upgrade-add", "upgrade-list", "upgrade-ready", "upgrade-cancel")
        )
    except OSError:
        hooks = False
    return [
        HealthCheck(
            "discord-connectivity",
            True,
            "Discord",
            "guild channel API",
            f"Connected; {len(channels)} channels visible.",
            channels="#upgrade-review",
            runtime_target="DiscordTracker",
        ),
        HealthCheck(
            "discord-required-channels",
            not missing,
            "Discord",
            "required owner and verification channels",
            "All required channels exist." if not missing else "Missing: " + ", ".join(f"#{item}" for item in missing),
            channels=" · ".join(f"#{item}" for item in REQUIRED_CHANNELS),
            runtime_target="feature-owned channel bootstrap",
            force_upgrade=bool(missing),
            acceptance_tests="Missing channels are created idempotently and a Discord timeout never blocks deployment.",
        ),
        HealthCheck(
            "upgrade-command-hooks",
            hooks,
            "upgrade bridge",
            "owner command hooks",
            "All four owner upgrade command markers are installed." if hooks else "One or more upgrade command hooks are missing.",
            channels="#upgrade-requests and #upgrade-review",
            runtime_target="github_upgrade_patch.install",
            force_upgrade=not hooks,
        ),
    ], channels


def _job_checks(engine_connection: sqlite3.Connection) -> list[HealthCheck]:
    jobs = list(_engine().JOBS)
    names = [job.name for job in jobs]
    results: list[HealthCheck] = []
    duplicates = sorted({name for name in names if names.count(name) > 1})
    results.append(
        HealthCheck(
            "scheduler-unique-jobs",
            not duplicates,
            "scheduler",
            "unique job registration",
            "Every job is registered once." if not duplicates else "Duplicate jobs: " + ", ".join(duplicates),
            runtime_target="local_information_engine.JOBS",
            force_upgrade=bool(duplicates),
        )
    )
    current = now()
    for job in jobs:
        row = engine_connection.execute(
            """
            SELECT status, started_at, COALESCE(finished_at, '') AS finished_at, detail
            FROM job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1
            """,
            (job.name,),
        ).fetchone()
        if not row:
            results.append(
                HealthCheck(
                    f"job-{job.name}",
                    False,
                    "scheduler",
                    f"job {job.name}",
                    "No scheduler receipt exists yet.",
                    severity="WARNING",
                    runtime_target=job.name,
                    automatic_retry="job remains scheduled",
                )
            )
            continue
        payload = dict(row)
        status = str(payload.get("status") or "").upper()
        started = _parse_time(payload.get("started_at"))
        finished = _parse_time(payload.get("finished_at"))
        interval = job.interval
        if job.after_hours_interval and not market_data.market_is_open_now()[0]:
            interval = job.after_hours_interval
        overdue = bool(finished and current - finished > max(interval * 2, timedelta(minutes=15)))
        stuck = bool(status == "RUNNING" and started and current - started > max(interval * 2, timedelta(minutes=20)))
        passed = status == "OK" and not overdue and not stuck
        detail = (
            f"status={status}; started={payload.get('started_at')}; finished={payload.get('finished_at') or 'pending'}; "
            f"expected interval={int(interval.total_seconds())}s; overdue={overdue}; stuck={stuck}; "
            f"detail={payload.get('detail', '')}"
        )
        force = stuck or status in {"ERROR", "INTERRUPTED"} and "applied-upgrades" in job.name
        results.append(
            HealthCheck(
                f"job-{job.name}",
                passed,
                "scheduler",
                f"job {job.name}",
                detail,
                severity="ERROR" if status in {"ERROR", "INTERRUPTED"} or stuck else "WARNING",
                runtime_target=job.name,
                automatic_retry="retry interval or next scheduled interval",
                force_upgrade=force,
                repair_objective=f"Restore {job.name} receipts and prevent missed or stuck runs.",
                acceptance_tests=f"{job.name} registers once, completes on schedule, and records a fresh OK receipt.",
            )
        )
    return results


_LOG_FAILURE_KEYWORDS = re.compile(
    r"(?i)(traceback|exception|\berror\b|failed|timeout|restart loop|rolled back)"
)
_ZERO_COUNT_QUALIFIER = re.compile(r"\b0\s*$")


def _line_has_genuine_failure_evidence(line: str) -> bool:
    """A routine status line reporting "0 failed syncs" or "0 errors" is
    healthy evidence, not failure evidence - confirmed live: this flagged
    log-information-engine.log-failure DEGRADED with 27 consecutive
    failures whose own evidence read "trade-intelligence-health: OK ·
    0 failed syncs", stuck that way because every future healthy status
    line kept re-triggering the same naive keyword match. Only count a
    keyword match as genuine evidence when it isn't immediately preceded
    by a literal zero count of that same thing."""
    for match in _LOG_FAILURE_KEYWORDS.finditer(line):
        if not _ZERO_COUNT_QUALIFIER.search(line[: match.start()]):
            return True
    return False


def _log_checks(store: sqlite3.Connection) -> list[HealthCheck]:
    paths = [
        LOG_DIR / "supervisor.log",
        LOG_DIR / "command-bot.log",
        LOG_DIR / "information-engine.log",
        STARTUP_LOG,
        WATCHDOG_LOG,
    ]
    findings: list[HealthCheck] = []
    for path in paths:
        if not path.exists():
            continue
        key = f"log-offset:{path.name}"
        try:
            size = path.stat().st_size
            previous = int(_meta(store, key, "0") or 0)
            if previous > size:
                previous = 0
            with path.open("rb") as handle:
                handle.seek(previous)
                raw = handle.read(200_000)
            _set_meta(store, key, str(size))
            text = raw.decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        suspicious = [line for line in text.splitlines() if _line_has_genuine_failure_evidence(line)]
        if not suspicious:
            continue
        sample = "\n".join(suspicious[-12:])
        findings.append(
            HealthCheck(
                f"log-{path.name}-{hashlib.sha256(normalize_error(sample).encode()).hexdigest()[:12]}",
                False,
                "logs",
                f"new failure evidence in {path.name}",
                sample,
                severity="WARNING",
                runtime_target=str(path.relative_to(ROOT)),
                automatic_retry="diagnostic log cursor prevents old evidence from being counted again",
            )
        )
    return findings


def collect_health_checks(engine_connection: sqlite3.Connection) -> tuple[list[HealthCheck], dict[str, dict[str, Any]]]:
    state = _read_json(SUPERVISOR_STATE_PATH)
    checks = [*_supervisor_checks(state), *_service_checks(state), *_git_checks(state)]
    discord, channels = _discord_checks()
    checks.extend(discord)
    checks.extend(_job_checks(engine_connection))
    store = connect_store()
    try:
        checks.extend(_log_checks(store))
    finally:
        store.close()
    return checks, channels


def _upsert_message(
    engine_connection: sqlite3.Connection,
    tracker: Any,
    channel_id: str,
    state_key: str,
    hash_key: str,
    content: str,
) -> str:
    digest = hashlib.sha256(content.encode()).hexdigest()
    previous = _engine().get_state(engine_connection, hash_key, "")
    message_id = _engine().get_state(engine_connection, state_key, "")
    if message_id and previous == digest:
        return message_id
    payload = {"content": content[:1900], "allowed_mentions": {"parse": []}}
    if message_id:
        try:
            tracker._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
            _engine().set_state(engine_connection, hash_key, digest)
            return message_id
        except Exception:
            message_id = ""
    created = tracker._request("POST", f"/channels/{channel_id}/messages", payload)
    message_id = str((created or {}).get("id") or "")
    if not message_id:
        raise RuntimeError("Discord did not acknowledge the stable diagnostic card")
    _engine().set_state(engine_connection, state_key, message_id)
    _engine().set_state(engine_connection, hash_key, digest)
    return message_id


def _acceptance_content(checks: list[HealthCheck], channels: dict[str, dict[str, Any]]) -> str:
    state = _read_json(SUPERVISOR_STATE_PATH)
    selected = [
        ("Simple two-minute updater", str(state.get("supervisor_mode") or "") == "SIMPLE_TWO_MINUTE_UPDATER", str(state.get("supervisor_mode") or "missing")),
        ("Command bot online", _tcp_open(8080), "127.0.0.1:8080"),
        ("Information engine online", _tcp_open(8765), "127.0.0.1:8765"),
        ("Scheduler heartbeat", any(check.key.startswith("job-") and check.passed for check in checks), "fresh job receipts available"),
        ("ngrok online when configured", _tcp_open(4040) or not (ROOT / "ngrok.exe").exists(), "127.0.0.1:4040"),
        ("#upgrade-requests", REQUEST_CHANNEL in channels, REQUEST_CHANNEL),
        ("#upgrade-review", REVIEW_CHANNEL in channels, REVIEW_CHANNEL),
        ("#applied-upgrades", APPLIED_CHANNEL in channels, APPLIED_CHANNEL),
        ("Upgrade command hooks", next((check.passed for check in checks if check.key == "upgrade-command-hooks"), False), "four owner commands"),
        ("Diagnostic stable reporting", REVIEW_CHANNEL in channels, "deduplicated message IDs stored locally"),
        ("Applied-upgrade runtime proof", next((check.passed for check in checks if check.key == "job-applied-upgrades-dashboard"), False), "scheduler receipt"),
        ("No detected restart loop", not any("restart loop" in check.detail.casefold() and not check.passed for check in checks), "recent logs"),
        ("Installed equals deployed", next((check.passed for check in checks if check.key == "installed-deployed-commit"), False), "supervisor state"),
    ]
    icons = {True: "PASS", False: "FAIL"}
    lines = [
        "# Tradysquid Live Acceptance",
        f"**Deployed commit:** `{_current_sha()}`",
        "Each item is reported separately. Repository tests alone are not treated as live proof.",
    ]
    lines.extend(
        f"{'✅' if passed else '❌'} **{icons[passed]} · {title}** · {detail}"
        for title, passed, detail in selected
    )
    lines.append(f"Checked **{iso_now()}**.")
    return "\n".join(lines)[:1900]


def _post_live_acceptance(
    engine_connection: sqlite3.Connection,
    checks: list[HealthCheck],
    channels: dict[str, dict[str, Any]],
) -> None:
    tracker, channel_id = ensure_owner_channel(
        REVIEW_CHANNEL,
        "Owner review queue for upgrades, diagnostics, deployment, and live acceptance.",
    )
    if not tracker or not channel_id:
        return
    _upsert_message(
        engine_connection,
        tracker,
        channel_id,
        ACCEPTANCE_MESSAGE_KEY,
        ACCEPTANCE_HASH_KEY,
        _acceptance_content(checks, channels),
    )


def diagnostic_cycle_job(engine_connection: sqlite3.Connection) -> str:
    checks, channels = collect_health_checks(engine_connection)
    store = connect_store()
    failed = 0
    recovered = 0
    try:
        for check in checks:
            if check.passed:
                if record_recovery(check.key, check.detail, connection=store):
                    recovered += 1
            else:
                record_failure(check, connection=store)
                failed += 1
        _set_meta(store, "last-complete-cycle", iso_now())
    finally:
        store.close()
    _post_live_acceptance(engine_connection, checks, channels)
    _engine().store_observation(
        engine_connection,
        DIAGNOSTIC_JOB,
        {
            "checks": len(checks),
            "failed": failed,
            "recovered": recovered,
            "commit": _current_sha(),
            "at": iso_now(),
        },
    )
    return f"{len(checks)} checks; {failed} failing; {recovered} recovered"


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (occurrence - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    final = date(year, month, monthrange(year, month)[1])
    return final - timedelta(days=(final.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def fallback_market_session(day: date) -> tuple[clock_time, clock_time] | None:
    """NYSE-rule fallback used only when the configured market calendar is unavailable."""
    if day.weekday() >= 5:
        return None
    year = day.year
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    if day in holidays:
        return None
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    early_close = day == thanksgiving + timedelta(days=1)
    early_close = early_close or (day.month == 12 and day.day == 24)
    early_close = early_close or (day.month == 7 and day.day == 3)
    return clock_time(8, 30), clock_time(12 if early_close else 15, 0)


def _calendar_days(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value: Any = payload
    for key in ("calendar", "days", "day"):
        if isinstance(value, dict) and key in value:
            value = value[key]
    if isinstance(value, dict):
        value = [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _parse_clock(value: Any, default: clock_time) -> clock_time:
    text = str(value or "")
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return default
    return clock_time(int(match.group(1)), int(match.group(2)))


def official_market_session(
    moment: datetime | None = None,
    *,
    calendar_payload: dict[str, Any] | None = None,
) -> tuple[datetime, datetime] | None:
    moment = (moment or datetime.now(market_data.MARKET_TZ)).astimezone(market_data.MARKET_TZ)
    payload = calendar_payload
    if payload is None:
        try:
            payload = market_data.tradier_get(
                "/markets/calendar",
                {"month": moment.month, "year": moment.year},
            )
        except Exception:
            payload = None
    if payload:
        for item in _calendar_days(payload):
            if str(item.get("date") or "") != moment.date().isoformat():
                continue
            status = str(item.get("status") or "").casefold()
            if status not in {"open", "early-close", "early_close"}:
                return None
            open_data = item.get("open") if isinstance(item.get("open"), dict) else {}
            start = _parse_clock(open_data.get("start") or item.get("open_time"), clock_time(8, 30))
            end = _parse_clock(open_data.get("end") or item.get("close_time"), clock_time(15, 0))
            return (
                datetime.combine(moment.date(), start, tzinfo=market_data.MARKET_TZ),
                datetime.combine(moment.date(), end, tzinfo=market_data.MARKET_TZ),
            )
    fallback = fallback_market_session(moment.date())
    if not fallback:
        return None
    return (
        datetime.combine(moment.date(), fallback[0], tzinfo=market_data.MARKET_TZ),
        datetime.combine(moment.date(), fallback[1], tzinfo=market_data.MARKET_TZ),
    )


def market_review_due(
    engine_connection: sqlite3.Connection,
    moment: datetime | None = None,
    *,
    calendar_payload: dict[str, Any] | None = None,
) -> bool:
    moment = (moment or datetime.now(market_data.MARKET_TZ)).astimezone(market_data.MARKET_TZ)
    session = official_market_session(moment, calendar_payload=calendar_payload)
    if not session or not (session[0] <= moment <= session[1]):
        return False
    last = _parse_time(_engine().get_state(engine_connection, MARKET_REVIEW_LAST_KEY, ""))
    return not last or moment - last.astimezone(market_data.MARKET_TZ) >= timedelta(hours=2)


def _age(value: str) -> str:
    parsed = _parse_time(value)
    if not parsed:
        return "unknown age"
    delta = max(timedelta(), now() - parsed)
    hours = int(delta.total_seconds() // 3600)
    return f"{hours}h" if hours else f"{int(delta.total_seconds() // 60)}m"


def _queue_content(
    status: dict[str, Any],
    pulls: list[dict[str, Any]],
    state: dict[str, Any],
) -> str:
    lines = [
        "# Upgrade Review Queue",
        f"**Shared batch:** #{status.get('issue_number') or 'none'} · {status.get('state', 'NONE')} · {status.get('request_count', 0)} request(s)",
    ]
    for request in status.get("requests") or []:
        lines.append(
            f"• **Request {request.get('request_number')} · {request.get('source')} · {request.get('status')}** "
            f"· {_age(str(request.get('updated_at') or ''))} · {request.get('summary')} · **Next:** {request.get('next_action')}"
        )
    for pull in pulls:
        lines.append(
            f"• **PR #{pull['number']} · CI {pull['ci_state']}** · {_age(pull['updated_at'])} · "
            f"{pull['title']} · **Next:** {pull['next_action']}"
        )
    remote = str(state.get("last_remote_sha") or "")[:12]
    deployed = str(state.get("deployed_sha") or "")[:12]
    if remote and deployed and remote != deployed:
        lines.append(
            f"• **DEPLOYMENT PENDING** · remote `{remote}` / deployed `{deployed}` · **Next:** leave the two-minute updater running."
        )
    lines.append(f"Reviewed **{iso_now()}**. Unchanged and empty queues are not reposted.")
    return "\n".join(lines)[:1900]


def market_upgrade_review_job(engine_connection: sqlite3.Connection) -> str:
    moment = datetime.now(market_data.MARKET_TZ)
    if not market_review_due(engine_connection, moment):
        return "outside official market session or two-hour review is not due"
    try:
        status = bridge.batch_status()
        pulls = bridge.pull_request_queue()
    except Exception as exc:
        record_failure(
            HealthCheck(
                "market-review-github",
                False,
                "upgrade review",
                "GitHub queue review",
                f"{type(exc).__name__}: {exc}",
                severity="WARNING",
                channels="#upgrade-review",
                runtime_target=MARKET_REVIEW_JOB,
                automatic_retry="next eligible market-hours review",
            )
        )
        raise
    state = _read_json(SUPERVISOR_STATE_PATH)
    remote = str(state.get("last_remote_sha") or "")[:12]
    deployed = str(state.get("deployed_sha") or "")[:12]
    has_queue = bool(status.get("request_count") or pulls or (remote and deployed and remote != deployed))
    _engine().set_state(engine_connection, MARKET_REVIEW_LAST_KEY, moment.isoformat())
    if not has_queue:
        return "upgrade review queue is empty; no Discord message posted"
    tracker, channel_id = ensure_owner_channel(
        REVIEW_CHANNEL,
        "Owner review queue for upgrades, diagnostics, deployment, and live acceptance.",
    )
    if not tracker or not channel_id:
        raise RuntimeError("#upgrade-review is unavailable")
    content = _queue_content(status, pulls, state)
    _upsert_message(
        engine_connection,
        tracker,
        channel_id,
        REVIEW_MESSAGE_KEY,
        REVIEW_HASH_KEY,
        content,
    )
    _engine().store_observation(
        engine_connection,
        MARKET_REVIEW_JOB,
        {
            "batch": status,
            "pulls": pulls,
            "remote": remote,
            "deployed": deployed,
            "at": iso_now(),
        },
    )
    return f"{status.get('request_count', 0)} request(s); {len(pulls)} pull request(s)"


def diagnostics_summary() -> dict[str, Any]:
    connection = connect_store()
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM diagnostics GROUP BY status"
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        open_rows = connection.execute(
            "SELECT * FROM diagnostics WHERE status IN ('DEGRADED','FAILED','RETRYING','FAILED AGAIN') ORDER BY last_seen DESC"
        ).fetchall()
        return {
            "counts": counts,
            "open": [dict(row) for row in open_rows],
            "last_cycle": _meta(connection, "last-complete-cycle", ""),
        }
    finally:
        connection.close()


def _seed_immediate_runs() -> None:
    engine = _engine()
    connection = engine.connect_db()
    try:
        sha = _current_sha()
        installed = engine.get_state(connection, INSTALLED_SHA_KEY, "")
        if installed == sha:
            return
        for name in (DIAGNOSTIC_JOB, MARKET_REVIEW_JOB):
            connection.execute(
                "DELETE FROM engine_state WHERE key IN (?, ?)",
                (f"job:{name}", f"job-error:{name}"),
            )
        connection.commit()
        engine.set_state(connection, INSTALLED_SHA_KEY, sha)
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    engine = _engine()
    callbacks = {
        DIAGNOSTIC_JOB: engine.Job(
            DIAGNOSTIC_JOB,
            timedelta(minutes=5),
            diagnostic_cycle_job,
            background=True,
            retry_interval=timedelta(minutes=2),
        ),
        MARKET_REVIEW_JOB: engine.Job(
            MARKET_REVIEW_JOB,
            timedelta(hours=2),
            market_upgrade_review_job,
            background=True,
            retry_interval=timedelta(minutes=15),
        ),
    }
    rebuilt = []
    seen: set[str] = set()
    for job in engine.JOBS:
        if job.name in callbacks:
            if job.name not in seen:
                rebuilt.append(callbacks[job.name])
                seen.add(job.name)
        else:
            rebuilt.append(job)
    for name, job in callbacks.items():
        if name not in seen:
            rebuilt.append(job)
    engine.JOBS = rebuilt
    _seed_immediate_runs()
    _INSTALLED = True


def validate() -> dict[str, Any]:
    return {
        "version": VERSION,
        "shared_diagnostic_batch": callable(bridge.add_or_update_diagnostic),
        "lightweight_minutes": 5,
        "market_review_hours": 2,
        "stable_discord_reports": True,
        "secret_redaction": True,
        "deployment_gate": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
