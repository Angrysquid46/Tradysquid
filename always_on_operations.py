"""Always-on scheduler diagnostics, self-repair, and off-hours research.

This module extends the local information engine without adding brokerage-order
capability. It keeps visible Discord activity alive around the clock, verifies
that scheduled jobs actually fire, retries failed or overdue jobs, records every
repair attempt, and runs read-only rotating-universe research while markets are
closed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import dynamic_universe
import ford_scan
import local_information_engine as engine


ROOT = Path(__file__).resolve().parent
HEARTBEAT_PATH = ROOT / "state" / "operations-heartbeat.json"
DIAGNOSTIC_MINUTES = max(2, int(os.environ.get("OPERATIONS_DIAGNOSTIC_MINUTES", "5")))
OFF_HOURS_SCREEN_MINUTES = max(15, int(os.environ.get("OFF_HOURS_SCREEN_MINUTES", "30")))
OFF_HOURS_BATCH_SIZE = max(2, min(12, int(os.environ.get("OFF_HOURS_SCREEN_BATCH", "6"))))
EVENT_SWEEP_MINUTES = max(30, int(os.environ.get("EVENT_SWEEP_MINUTES", "60")))
EVENT_BATCH_SIZE = max(2, min(12, int(os.environ.get("EVENT_SWEEP_BATCH", "6"))))
REPAIR_LIMIT_PER_RUN = max(1, min(8, int(os.environ.get("REPAIR_LIMIT_PER_RUN", "4"))))
REPAIR_LIMIT_PER_HOUR = max(1, min(12, int(os.environ.get("REPAIR_LIMIT_PER_HOUR", "3"))))
STALE_RUNNING_MINUTES = max(10, int(os.environ.get("STALE_RUNNING_MINUTES", "20")))
OPERATIONS_JOB_NAMES = {
    "scheduler-diagnostics",
    "system-activity",
    "automatic-self-repair",
    "off-hours-universe-screen",
    "rotating-event-sweep",
}
_INSTALLED = False


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS repair_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_job TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            trigger_status TEXT NOT NULL,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS repair_actions_job_time
            ON repair_actions(target_job, detected_at DESC);

        CREATE TABLE IF NOT EXISTS diagnostic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            job_name TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS diagnostic_events_time
            ON diagnostic_events(observed_at DESC);
        """
    )
    connection.commit()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=engine.utc_now().tzinfo)
    return parsed


def age_seconds(value: str | None, now: datetime | None = None) -> float | None:
    parsed = parse_time(value)
    if not parsed:
        return None
    return max(0.0, ((now or engine.utc_now()) - parsed).total_seconds())


def age_text(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def interval_text(seconds: float) -> str:
    seconds = max(1, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        hours = seconds / 3600
        return f"{hours:g}h"
    return f"{seconds / 86400:g}d"


def latest_runs(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT jr.*
        FROM job_runs jr
        JOIN (
            SELECT job_name, MAX(id) AS latest_id
            FROM job_runs
            GROUP BY job_name
        ) latest ON latest.latest_id = jr.id
        """
    ).fetchall()
    return {str(row["job_name"]): dict(row) for row in rows}


def market_open_now() -> bool:
    try:
        return bool(ford_scan.market_is_open_now()[0])
    except Exception:
        return False


def expected_interval(job: engine.Job, market_open: bool, failed: bool = False) -> timedelta:
    if failed and job.retry_interval:
        return job.retry_interval
    if not market_open and job.after_hours_interval:
        return job.after_hours_interval
    return job.interval


def startup_age(connection: sqlite3.Connection, now: datetime) -> float:
    value = engine.get_state(connection, "operations-started-at")
    parsed = parse_time(value)
    if not parsed:
        engine.set_state(connection, "operations-started-at", now.isoformat())
        return 0.0
    return max(0.0, (now - parsed).total_seconds())


def job_health_rows(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    ensure_schema(connection)
    current = now or engine.utc_now()
    market_open = market_open_now()
    startup_seconds = startup_age(connection, current)
    runs = latest_runs(connection)
    rows: list[dict[str, Any]] = []

    for job in engine.JOBS:
        run = runs.get(job.name)
        raw_status = str((run or {}).get("status") or "NEVER")
        timestamp = str((run or {}).get("finished_at") or (run or {}).get("started_at") or "")
        elapsed = age_seconds(timestamp, current)
        failed = raw_status in {"ERROR", "INTERRUPTED"}
        interval = expected_interval(job, market_open, failed=failed)
        expected = max(1.0, interval.total_seconds())
        overdue_after = expected + max(60.0, expected * 0.50)
        stale_after = max(STALE_RUNNING_MINUTES * 60.0, expected * 2.0)
        detail = str((run or {}).get("detail") or "")[:500]

        if job.market_hours_only and not market_open:
            status = "PAUSED"
            reason = "market closed; trading job intentionally paused"
            if failed:
                status = "FAILED_WAITING_FOR_MARKET"
                reason = detail or "last market-hours attempt failed"
        elif raw_status == "RUNNING":
            if elapsed is not None and elapsed > stale_after:
                status = "STALE"
                reason = f"running for {age_text(elapsed)} without completion"
            else:
                status = "RUNNING"
                reason = "currently executing"
        elif raw_status in {"ERROR", "INTERRUPTED"}:
            status = "FAILED"
            reason = detail or raw_status.lower()
        elif raw_status == "NEVER":
            if startup_seconds < 600:
                status = "STARTING"
                reason = "engine startup grace period"
            else:
                status = "NEVER"
                reason = "no completed run is recorded"
        elif elapsed is not None and elapsed > overdue_after:
            status = "OVERDUE"
            reason = f"last receipt {age_text(elapsed)} ago; expected every {interval_text(expected)}"
        else:
            status = "OK"
            reason = detail or "completed on schedule"

        rows.append(
            {
                "job": job,
                "name": job.name,
                "status": status,
                "raw_status": raw_status,
                "age_seconds": elapsed,
                "age": age_text(elapsed),
                "expected_seconds": expected,
                "expected": interval_text(expected),
                "detail": detail,
                "reason": reason,
                "run_id": int((run or {}).get("id") or 0),
                "started_at": str((run or {}).get("started_at") or ""),
                "finished_at": str((run or {}).get("finished_at") or ""),
                "market_hours_only": bool(job.market_hours_only),
            }
        )
    return rows


def health_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "healthy": 0,
        "running": 0,
        "paused": 0,
        "starting": 0,
        "attention": 0,
    }
    for row in rows:
        status = row["status"]
        if status == "OK":
            counts["healthy"] += 1
        elif status == "RUNNING":
            counts["running"] += 1
        elif status in {"PAUSED", "FAILED_WAITING_FOR_MARKET"}:
            counts["paused"] += 1
            if status.startswith("FAILED"):
                counts["attention"] += 1
        elif status == "STARTING":
            counts["starting"] += 1
        else:
            counts["attention"] += 1
    return counts


def status_icon(status: str) -> str:
    return {
        "OK": "✅",
        "RUNNING": "🔄",
        "PAUSED": "⏸️",
        "STARTING": "🟡",
        "FAILED_WAITING_FOR_MARKET": "⚠️",
        "FAILED": "❌",
        "OVERDUE": "⏰",
        "STALE": "🛑",
        "NEVER": "❔",
    }.get(status, "⚠️")


def recent_repairs(connection: sqlite3.Connection, limit: int = 8) -> list[dict[str, Any]]:
    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT * FROM repair_actions
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(limit, 25)),),
    ).fetchall()
    return [dict(row) for row in rows]


def write_operations_heartbeat(
    rows: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": engine.iso_now(),
        "scheduler": "ONLINE",
        "jobs": len(rows),
        "counts": counts,
        "attention": [
            {
                "name": row["name"],
                "status": row["status"],
                "reason": row["reason"],
            }
            for row in rows
            if row["status"] not in {"OK", "RUNNING", "PAUSED", "STARTING"}
        ][:20],
    }
    temporary = HEARTBEAT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(HEARTBEAT_PATH)


def diagnostics_card(
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    repairs: list[dict[str, Any]],
) -> str:
    attention = [
        row
        for row in rows
        if row["status"] not in {"OK", "RUNNING", "PAUSED", "STARTING"}
    ]
    lines = [
        "## Automation Diagnostics and Self-Repair",
        (
            f"**Healthy {counts['healthy']}** · running {counts['running']} · "
            f"paused {counts['paused']} · starting {counts['starting']} · "
            f"needs attention **{counts['attention']}**"
        ),
        f"Scheduler heartbeat **{engine.iso_now()}** · market **{'OPEN' if market_open_now() else 'CLOSED'}**",
        "### What did not fire properly",
    ]
    if attention:
        for row in attention[:12]:
            lines.append(
                f"{status_icon(row['status'])} **{row['name']}** · {row['status']} · "
                f"last {row['age']} ago · expected {row['expected']} · {row['reason'][:220]}"
            )
    else:
        lines.append("✅ No missed, failed, stale, or overdue interval is currently detected.")

    lines.append("### Latest automatic repair actions")
    if repairs:
        for item in repairs[:8]:
            lines.append(
                f"• **{item['target_job']}** · {item['trigger_status']} → "
                f"{item['result']} · {item['detected_at']} · {str(item['detail'])[:180]}"
            )
    else:
        lines.append("No repair action has been required since this ledger was created.")

    lines.extend(
        [
            "### Recovery contract",
            "A repair counts only after the target job records a successful receipt. Repeated failures remain visible and are retried within bounded limits instead of being hidden behind a green process light.",
        ]
    )
    return "\n".join(lines)[:5900]


def activity_card(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> str:
    active = dynamic_universe.initialize()
    scan_cursor_path = ROOT / "state" / "universe-scan-cursor.json"
    try:
        cursor_state = json.loads(scan_cursor_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        cursor_state = {}
    latest_off_hours = engine.latest_observation("off-hours-universe-screen")
    latest_events = engine.latest_observation("rotating-event-sweep")
    latest_positions = engine.latest_observation("position-tracker")
    stream_payload = (latest_positions or {}).get("payload") or {}
    stream_state = str(stream_payload.get("stream") or "unknown")
    stream_error = str(stream_payload.get("stream_error") or "")
    if stream_state == "connected":
        stream_line = "🟢 **Live position stream:** connected - positions are checked as each price tick arrives, not on a timer."
    elif stream_state == "fallback":
        stream_line = (
            "🟡 **Live position stream:** not connected right now - falling back to the "
            "1-minute safety check only." + (f" ({stream_error})" if stream_error else "")
        )
    else:
        stream_line = "⚪ **Live position stream:** status not available yet."
    core_names = {
        "provider-event-queue",
        "position-tracker",
        "full-options-scan",
        "off-hours-universe-screen",
        "managed-ticker-information",
        "managed-ticker-news",
        "rotating-event-sweep",
        "dynamic-universe-refresh",
        "discord-reporting",
        "health-snapshot",
    }
    selected = [row for row in rows if row["name"] in core_names]
    lines = [
        "## Always-On Tradysquids Activity",
        f"**Market:** {'OPEN · trade scanner enabled' if market_open_now() else 'CLOSED · research-only screening enabled'}",
        stream_line,
        f"**Active universe:** {len(active)}/{dynamic_universe.max_active_symbols()} symbols",
        f"**Last live scanner rotation:** {', '.join(cursor_state.get('last_batch') or []) or 'not recorded yet'}",
        f"**Last off-hours research batch:** {', '.join(((latest_off_hours or {}).get('payload') or {}).get('batch') or []) or 'not recorded yet'}",
        "### Interval receipts",
    ]
    for row in selected:
        lines.append(
            f"{status_icon(row['status'])} **{row['name']}** · {row['status']} · "
            f"{row['age']} ago · interval {row['expected']}"
        )
    lines.extend(
        [
            "### Current background work",
            (
                f"Off-hours screen: {engine.data_age_text((latest_off_hours or {}).get('observed_at'))} ago · "
                f"event sweep: {engine.data_age_text((latest_events or {}).get('observed_at'))} ago"
            ),
            "When markets are closed, TradeBot keeps rotating through the stock universe, refreshing charts and research context, checking events and headlines, reviewing outcomes, and validating every scheduler interval. No paper position is opened or closed outside permitted market logic.",
            f"Updated **{engine.iso_now()}**.",
        ]
    )
    return "\n".join(lines)[:5900]


def scheduler_diagnostics_job(connection: sqlite3.Connection) -> str:
    rows = job_health_rows(connection)
    counts = health_counts(rows)
    ensure_schema(connection)
    for row in rows:
        if row["status"] in {"FAILED", "OVERDUE", "STALE", "NEVER", "FAILED_WAITING_FOR_MARKET"}:
            connection.execute(
                "INSERT INTO diagnostic_events(observed_at, job_name, status, detail) VALUES (?, ?, ?, ?)",
                (engine.iso_now(), row["name"], row["status"], row["reason"][:500]),
            )
    connection.execute(
        "DELETE FROM diagnostic_events WHERE id IN (SELECT id FROM diagnostic_events ORDER BY id DESC LIMIT -1 OFFSET 1000)"
    )
    connection.commit()
    write_operations_heartbeat(rows, counts)
    repairs = recent_repairs(connection)
    engine.store_observation(
        connection,
        "automation-diagnostics",
        {
            "counts": counts,
            "attention": [
                {"job": row["name"], "status": row["status"], "reason": row["reason"]}
                for row in rows
                if row["status"] not in {"OK", "RUNNING", "PAUSED", "STARTING"}
            ],
        },
    )
    engine.upsert_dashboard(
        connection,
        "automation_diagnostics",
        "automation-diagnostics",
        diagnostics_card(rows, counts, repairs),
    )
    engine.upsert_dashboard(
        connection,
        "status",
        "scheduler-integrity",
        "\n".join(
            [
                "## Scheduler Integrity",
                f"Healthy **{counts['healthy']}** · running **{counts['running']}** · paused **{counts['paused']}** · needs attention **{counts['attention']}**",
                "Failures and missed intervals are listed with repair attempts in #automation-diagnostics.",
                f"Verified {engine.iso_now()}.",
            ]
        ),
    )
    return (
        f"{len(rows)} jobs checked; {counts['attention']} need attention; "
        f"{len(repairs)} repair records available"
    )


def system_activity_job(connection: sqlite3.Connection) -> str:
    rows = job_health_rows(connection)
    content = activity_card(connection, rows)
    engine.upsert_dashboard(
        connection,
        "system_activity",
        "always-on-activity",
        content,
    )
    return f"activity receipt refreshed for {len(rows)} scheduled jobs"


def separate_rotation_batch(
    connection: sqlite3.Connection,
    key: str,
    size: int,
) -> list[str]:
    symbols = dynamic_universe.initialize()
    if not symbols:
        return []
    state_key = f"rotation:{key}:cursor"
    try:
        cursor = int(engine.get_state(connection, state_key, "0"))
    except ValueError:
        cursor = 0
    size = max(1, min(size, len(symbols), 12))
    batch = [symbols[(cursor + index) % len(symbols)] for index in range(size)]
    engine.set_state(connection, state_key, str((cursor + size) % len(symbols)))
    engine.set_state(connection, f"rotation:{key}:last-batch", json.dumps(batch))
    return batch


def snapshot_score(snapshot: dict[str, Any]) -> float:
    score = float(snapshot.get("evidence_score") or 0)
    relative_volume = ford_scan.as_float(snapshot.get("relative_volume"), 0.0) or 0.0
    change = abs(ford_scan.as_float(snapshot.get("change_pct"), 0.0) or 0.0)
    if snapshot.get("qualified"):
        score += 20
    score += min(relative_volume, 3.0) * 5
    score += min(change, 10.0)
    return round(score, 1)


def option_reference(symbol: str, side: str) -> str:
    try:
        rows = engine.ranked_option_chain(side, limit=1, symbol=symbol)
    except Exception as exc:
        return f"{side}: unavailable ({type(exc).__name__})"
    if not rows:
        return f"{side}: no contract returned"
    item = rows[0]
    return (
        f"{side} `{item.get('symbol')}` · Δ {ford_scan.as_float(item.get('delta'), 0) or 0:.2f} · "
        f"IV {(ford_scan.as_float(item.get('iv'), 0) or 0) * 100:.0f}% · "
        f"width {(ford_scan.as_float(item.get('width_pct'), 0) or 0) * 100:.0f}% · "
        f"{'liquid' if item.get('liquidity_pass') else 'fails liquidity'}"
    )


def off_hours_universe_screen_job(connection: sqlite3.Connection) -> str:
    if market_open_now():
        return "market open; live options scanner owns the rotation"
    batch = separate_rotation_batch(
        connection,
        "off-hours-screen",
        OFF_HOURS_BATCH_SIZE,
    )
    if not batch:
        raise RuntimeError("rotating universe is empty")
    completed: list[dict[str, Any]] = []
    failed: list[str] = []
    for symbol in batch:
        try:
            snapshot = engine.market_snapshot(symbol)
            completed.append(
                {
                    "symbol": symbol,
                    "price": snapshot.get("price"),
                    "change_pct": snapshot.get("change_pct"),
                    "regime": snapshot.get("regime"),
                    "qualified": snapshot.get("qualified"),
                    "reason": snapshot.get("reason"),
                    "rsi14": snapshot.get("rsi14"),
                    "support20": snapshot.get("support20"),
                    "resistance20": snapshot.get("resistance20"),
                    "relative_volume": snapshot.get("relative_volume"),
                    "score": snapshot_score(snapshot),
                }
            )
        except Exception as exc:
            detail = " ".join(str(exc).split())[:240] or "no detail"
            failed.append(f"{symbol}:{type(exc).__name__}:{detail}")
        time.sleep(0.35)
    completed.sort(key=lambda item: float(item.get("score") or 0), reverse=True)

    lines = [
        "## Off-Hours Rotating Universe Screen",
        f"**Research-only batch:** {', '.join(batch)}",
        "The market is closed. This pass ranks closing/last-known evidence and opens no paper position.",
        "### Ranked observations",
    ]
    for item in completed:
        lines.append(
            f"• **{item['symbol']}** · {ford_scan.fmt_money(item.get('price'))} · "
            f"score {item.get('score')} · {item.get('regime')} · RSI {item.get('rsi14')} · "
            f"support {ford_scan.fmt_money(item.get('support20'))} · "
            f"resistance {ford_scan.fmt_money(item.get('resistance20'))}"
        )
    if failed:
        lines.extend(["### Data failures", *[f"• {item}" for item in failed]])
    if completed:
        lines.append("### Closing-chain study references")
        for item in completed[:2]:
            symbol = str(item["symbol"])
            lines.append(f"• **{symbol}:** {option_reference(symbol, 'call')} | {option_reference(symbol, 'put')}")
    lines.extend(
        [
            "### Next use",
            "These observations feed member education, next-session preparation, event review, and the visible universe ledger. Live entry rules are evaluated only by the market-hours scanner.",
            f"Completed {engine.iso_now()}.",
        ]
    )
    payload = {
        "batch": batch,
        "completed": completed,
        "failed": failed,
        "observed_at": engine.iso_now(),
    }
    engine.store_observation(connection, "off-hours-universe-screen", payload)
    engine.upsert_dashboard(
        connection,
        "scanner_feed",
        "off-hours-universe-screen",
        "\n".join(lines),
    )
    universe_lines = [
        "## Rotating Universe Status",
        f"Active **{len(dynamic_universe.active_symbols())}/{dynamic_universe.max_active_symbols()}**",
        f"Current off-hours batch: **{', '.join(batch)}**",
        f"Completed: **{', '.join(item['symbol'] for item in completed) or 'none'}**",
        f"Failures: **{', '.join(failed) or 'none'}**",
        f"Next batch advances automatically in {OFF_HOURS_SCREEN_MINUTES} minutes while markets remain closed.",
    ]
    engine.upsert_dashboard(
        connection,
        "universe_watch",
        "rotating-universe-status",
        "\n".join(universe_lines),
    )
    if failed and not completed:
        raise RuntimeError("off-hours batch failed: " + ", ".join(failed))
    return f"screened {len(completed)}/{len(batch)} symbols; {len(failed)} data failures"


def rotating_event_sweep_job(connection: sqlite3.Connection) -> str:
    batch = separate_rotation_batch(connection, "event-sweep", EVENT_BATCH_SIZE)
    if not batch:
        raise RuntimeError("rotating universe is empty")
    results: dict[str, list[dict[str, str]]] = {}
    failed: list[str] = []
    for symbol in batch:
        try:
            results[symbol] = engine.fetch_ticker_news(symbol, limit=4)
        except Exception as exc:
            detail = " ".join(str(exc).split())[:240] or "no detail"
            failed.append(f"{symbol}:{type(exc).__name__}:{detail}")
        time.sleep(0.35)
    lines = [
        "## Rotating News and Event Sweep",
        f"**Universe batch:** {', '.join(batch)}",
        "Headlines are checked around the clock, including weekends and off-hours. Verify the original source before treating anything as material.",
    ]
    for symbol in batch:
        items = results.get(symbol) or []
        lines.append(f"### {symbol}")
        if items:
            lines.extend(f"• [{item['title']}]({item['url']})" for item in items[:4])
        else:
            lines.append("No current matching headline was returned in this sweep.")
    if failed:
        lines.extend(["### Provider failures", *[f"• {item}" for item in failed]])
    lines.append(f"Checked {engine.iso_now()}; the next batch rotates automatically.")
    engine.store_observation(
        connection,
        "rotating-event-sweep",
        {"batch": batch, "results": results, "failed": failed},
    )
    engine.upsert_dashboard(
        connection,
        "news_events",
        "rotating-event-sweep",
        "\n".join(lines),
    )
    if failed and not results:
        raise RuntimeError("event sweep failed: " + ", ".join(failed))
    return f"checked events for {len(results)}/{len(batch)} symbols; {len(failed)} failures"


def repair_attempts_last_hour(connection: sqlite3.Connection, job_name: str) -> int:
    cutoff = (engine.utc_now() - timedelta(hours=1)).isoformat()
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM repair_actions WHERE target_job=? AND detected_at>=? AND action='RESTART_JOB'",
        (job_name, cutoff),
    ).fetchone()
    return int(row["count"] if row else 0)


def record_repair(
    connection: sqlite3.Connection,
    *,
    target_job: str,
    trigger: str,
    action: str,
    result: str,
    detail: str,
) -> None:
    ensure_schema(connection)
    connection.execute(
        "INSERT INTO repair_actions(target_job, detected_at, trigger_status, action, result, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (target_job, engine.iso_now(), trigger, action, result, detail[:800]),
    )
    connection.execute(
        "DELETE FROM repair_actions WHERE id IN (SELECT id FROM repair_actions ORDER BY id DESC LIMIT -1 OFFSET 1000)"
    )
    connection.commit()


def automatic_self_repair_job(connection: sqlite3.Connection) -> str:
    rows = job_health_rows(connection)
    by_name = {job.name: job for job in engine.JOBS}
    candidates = [
        row
        for row in rows
        if row["name"] not in OPERATIONS_JOB_NAMES
        and row["status"] in {"FAILED", "OVERDUE", "STALE", "NEVER"}
    ]
    repaired: list[str] = []
    escalated: list[str] = []
    skipped: list[str] = []

    for row in candidates[:REPAIR_LIMIT_PER_RUN]:
        job = by_name[row["name"]]
        if job.market_hours_only and not market_open_now():
            skipped.append(f"{job.name}:market closed")
            continue
        required_delay = max(
            60.0,
            (job.retry_interval or timedelta(minutes=DIAGNOSTIC_MINUTES)).total_seconds(),
        )
        if row["status"] == "FAILED" and (row["age_seconds"] or 0) < required_delay:
            skipped.append(f"{job.name}:retry cooldown")
            continue
        attempts = repair_attempts_last_hour(connection, job.name)
        if attempts >= REPAIR_LIMIT_PER_HOUR:
            record_repair(
                connection,
                target_job=job.name,
                trigger=row["status"],
                action="ESCALATE",
                result="RETRY_LIMIT",
                detail=f"{attempts} automatic restarts in the last hour; failure remains visible",
            )
            escalated.append(job.name)
            continue
        if row["status"] == "STALE" and row["run_id"]:
            connection.execute(
                "UPDATE job_runs SET finished_at=?, status='INTERRUPTED', detail=? WHERE id=? AND status='RUNNING'",
                (engine.iso_now(), "Automatic diagnostics ended a stale RUNNING receipt", row["run_id"]),
            )
            connection.commit()
        started = engine.start_background_job(job)
        record_repair(
            connection,
            target_job=job.name,
            trigger=row["status"],
            action="RESTART_JOB",
            result="STARTED" if started else "ALREADY_RUNNING",
            detail=row["reason"],
        )
        if started:
            repaired.append(job.name)
        else:
            skipped.append(f"{job.name}:already running")

    return (
        f"started repairs for {', '.join(repaired) if repaired else 'none'}; "
        f"escalated {', '.join(escalated) if escalated else 'none'}; "
        f"skipped {', '.join(skipped) if skipped else 'none'}"
    )


def heartbeat_healthy(max_age_minutes: int = 12) -> bool:
    try:
        payload = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    age = age_seconds(str(payload.get("updated_at") or ""))
    return age is not None and age <= max(2, max_age_minutes) * 60


def operations_status_summary() -> str:
    connection = engine.connect_db()
    try:
        rows = job_health_rows(connection)
        counts = health_counts(rows)
        attention = [
            row for row in rows
            if row["status"] not in {"OK", "RUNNING", "PAUSED", "STARTING"}
        ]
    finally:
        connection.close()
    lines = [
        "## Automation",
        f"Scheduler heartbeat: **{'HEALTHY' if heartbeat_healthy() else 'STALE'}**",
        f"Jobs healthy {counts['healthy']} · running {counts['running']} · paused {counts['paused']} · needs attention {counts['attention']}",
    ]
    if attention:
        lines.append(
            "Attention: " + ", ".join(f"{row['name']} ({row['status']})" for row in attention[:5])
        )
    else:
        lines.append("No missed or failed interval is currently detected.")
    return "\n".join(lines)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    existing = {job.name for job in engine.JOBS}
    diagnostics = engine.Job(
        "scheduler-diagnostics",
        timedelta(minutes=DIAGNOSTIC_MINUTES),
        scheduler_diagnostics_job,
        retry_interval=timedelta(minutes=2),
    )
    activity = engine.Job(
        "system-activity",
        timedelta(minutes=DIAGNOSTIC_MINUTES),
        system_activity_job,
        retry_interval=timedelta(minutes=2),
    )
    off_hours = engine.Job(
        "off-hours-universe-screen",
        timedelta(minutes=OFF_HOURS_SCREEN_MINUTES),
        off_hours_universe_screen_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=10),
    )
    events = engine.Job(
        "rotating-event-sweep",
        timedelta(minutes=EVENT_SWEEP_MINUTES),
        rotating_event_sweep_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=15),
    )
    repair = engine.Job(
        "automatic-self-repair",
        timedelta(minutes=DIAGNOSTIC_MINUTES),
        automatic_self_repair_job,
        retry_interval=timedelta(minutes=2),
    )
    prefix = [job for job in (diagnostics, activity) if job.name not in existing]
    suffix = [job for job in (off_hours, events, repair) if job.name not in existing]
    engine.JOBS = [*prefix, *engine.JOBS, *suffix]
    _INSTALLED = True


if __name__ == "__main__":
    install()
    connection = engine.connect_db()
    try:
        rows = job_health_rows(connection)
        counts = health_counts(rows)
        print(json.dumps({"jobs": len(rows), "counts": counts}, indent=2))
    finally:
        connection.close()
