"""Run the local information engine with always-on operations installed."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dynamic_universe
import ford_scan

# Register the always-on Discord destinations before the engine discovers
# channels. The underlying scanner remains read-only and cannot place orders.
ford_scan.CHANNEL_NAMES.setdefault("system_activity", "system-activity")
ford_scan.CHANNEL_NAMES.setdefault("automation_diagnostics", "automation-diagnostics")
for key in ("system_activity", "automation_diagnostics"):
    if key not in ford_scan.AUTOMATED_CHANNEL_KEYS:
        ford_scan.AUTOMATED_CHANNEL_KEYS.append(key)
ford_scan.SYSTEM_CHANNEL_KEYS.add("automation_diagnostics")

# Preserve the exact market-hours rotation so #system-activity can show what the
# scanner actually processed, not merely the next cursor position.
_ORIGINAL_NEXT_SCAN_BATCH = dynamic_universe.next_scan_batch
_ROTATION_STATE_PATH = Path(__file__).resolve().parent / "state" / "universe-scan-cursor.json"


def recorded_next_scan_batch(batch_size: int = 12, connection=None) -> list[str]:
    batch = _ORIGINAL_NEXT_SCAN_BATCH(batch_size=batch_size, connection=connection)
    try:
        payload = json.loads(_ROTATION_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    payload["last_batch"] = list(batch)
    payload["last_batch_at"] = dynamic_universe.now_iso()
    _ROTATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _ROTATION_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(_ROTATION_STATE_PATH)
    return batch


dynamic_universe.next_scan_batch = recorded_next_scan_batch

import always_on_operations  # noqa: E402
import local_information_engine as engine  # noqa: E402


PREMARKET_VISIBILITY_MINUTES = max(
    5, int(os.environ.get("PREMARKET_VISIBILITY_MINUTES", "15"))
)
PREMARKET_AFTER_HOURS_MINUTES = max(
    PREMARKET_VISIBILITY_MINUTES,
    int(os.environ.get("PREMARKET_AFTER_HOURS_MINUTES", "30")),
)
BREAKING_ALERT_HEARTBEAT_MINUTES = max(
    2, int(os.environ.get("BREAKING_ALERT_HEARTBEAT_MINUTES", "5"))
)
_VISIBILITY_INSTALLED = False


def _session_label(now: datetime, market_open: bool) -> str:
    if market_open:
        return "MARKET OPEN"
    if now.weekday() >= 5:
        return "WEEKEND RESEARCH"
    if 7 <= now.hour < 8 or (now.hour == 8 and now.minute < 25):
        return "PREMARKET"
    if now.hour < 7:
        return "OVERNIGHT PREPARATION"
    if now.hour >= 15:
        return "AFTER-HOURS REVIEW"
    return "MARKET CLOSED / NEXT-SESSION PREPARATION"


def _quote_change(quote: dict[str, Any]) -> float | None:
    for key in ("change_percentage", "change_pct", "percent_change"):
        value = ford_scan.as_float(quote.get(key))
        if value is not None:
            return value
    return None


def _provider_queue_counts() -> dict[str, int]:
    counts = {"PENDING": 0, "PROCESSING": 0, "DONE": 0, "ERROR": 0}
    try:
        connection = dynamic_universe.connect()
        try:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM provider_events GROUP BY status"
            ).fetchall()
        finally:
            connection.close()
    except Exception:
        return counts
    for row in rows:
        status = str(row["status"] or "").upper()
        if status in counts:
            counts[status] = int(row["count"] or 0)
    return counts


def _dashboard_due(
    connection,
    state_key: str,
    minutes: int,
    *,
    force: bool = False,
) -> bool:
    if force:
        return True
    raw = engine.get_state(connection, state_key)
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=engine.utc_now().tzinfo)
    except (TypeError, ValueError):
        return True
    return engine.utc_now() - last >= timedelta(minutes=minutes)


def _require_dashboard(
    connection,
    logical_channel: str,
    state_key: str,
    content: str,
) -> None:
    if not engine.upsert_dashboard(connection, logical_channel, state_key, content):
        raise RuntimeError(
            f"Discord dashboard update failed for {logical_channel}:{state_key}"
        )


def _latest_batch(kind: str) -> list[str]:
    observation = engine.latest_observation(kind) or {}
    payload = observation.get("payload") or {}
    return [str(item) for item in payload.get("batch") or []]


def premarket_visibility_job(connection) -> str:
    """Keep #premarket visibly current during every session, including weekends."""
    now = ford_scan.now_ct()
    market_open = bool(ford_scan.market_is_open_now()[0])
    session = _session_label(now, market_open)
    symbols = dynamic_universe.active_symbols()
    quotes: dict[str, dict[str, Any]] = {}
    quote_error = ""
    if symbols:
        try:
            quotes = ford_scan.get_quotes(symbols, include_greeks=False)
        except Exception as exc:
            quote_error = f"{type(exc).__name__}: {' '.join(str(exc).split())[:180]}"

    ranked = sorted(
        symbols,
        key=lambda symbol: abs(_quote_change(quotes.get(symbol) or {}) or 0.0),
        reverse=True,
    )
    queue = _provider_queue_counts()
    off_hours_batch = _latest_batch("off-hours-universe-screen")
    event_batch = _latest_batch("rotating-event-sweep")
    latest_off_hours = engine.latest_observation("off-hours-universe-screen")
    latest_events = engine.latest_observation("rotating-event-sweep")

    lines = [
        "## Tradysquids Session Preparation",
        f"**Session:** {session} · **Market:** {'OPEN' if market_open else 'CLOSED'}",
        f"**Active rotating universe:** {len(symbols)}/{dynamic_universe.max_active_symbols()} symbols",
        "### Current universe movement",
    ]
    visible = 0
    for symbol in ranked[:10]:
        quote = quotes.get(symbol) or {}
        price = ford_scan.as_float(quote.get("last"))
        change = _quote_change(quote)
        volume = int(ford_scan.as_float(quote.get("volume"), 0) or 0)
        if price is None and change is None and not volume:
            continue
        visible += 1
        change_text = "change unavailable" if change is None else f"{change:+.2f}%"
        lines.append(
            f"• **{symbol}** · {ford_scan.fmt_money(price)} · {change_text} · volume {volume:,}"
        )
    if visible == 0:
        lines.append(
            "No fresh quote movement was returned; the active universe and research "
            "receipts are still being checked."
        )
    if quote_error:
        lines.append(f"• Quote provider warning: `{quote_error}`")

    lines.extend(
        [
            "### Research and event receipts",
            (
                f"• Off-hours screen: {engine.data_age_text((latest_off_hours or {}).get('observed_at'))} ago"
                f" · last batch **{', '.join(off_hours_batch) or 'not recorded yet'}**"
            ),
            (
                f"• News/event sweep: {engine.data_age_text((latest_events or {}).get('observed_at'))} ago"
                f" · last batch **{', '.join(event_batch) or 'not recorded yet'}**"
            ),
            (
                f"• Provider event queue: pending **{queue['PENDING']}** · processing "
                f"**{queue['PROCESSING']}** · errors **{queue['ERROR']}**"
            ),
            "### Automatic behavior",
            (
                f"This live card refreshes every {PREMARKET_VISIBILITY_MINUTES} minutes "
                f"during active sessions and every {PREMARKET_AFTER_HOURS_MINUTES} minutes "
                "after hours and on weekends. The separate morning briefing still posts "
                "during its weekday premarket window."
            ),
            "Closed-market information uses last-known quotes and opens no paper trade.",
            f"Updated **{engine.iso_now()}**.",
        ]
    )
    payload = {
        "session": session,
        "market_open": market_open,
        "symbols": symbols,
        "ranked": ranked[:10],
        "queue": queue,
        "quote_error": quote_error,
        "updated_at": engine.iso_now(),
    }
    engine.store_observation(connection, "premarket-visibility", payload)
    _require_dashboard(
        connection,
        "premarket",
        "premarket-live-status",
        "\n".join(lines)[:5900],
    )
    return (
        f"{session.lower()} card refreshed; {len(symbols)} symbols; "
        f"{queue['PENDING']} provider events pending"
    )


def _payload_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        text = " ".join(str(payload or "").split())
        return text[:400] or "No additional payload details."
    preferred = (
        "message",
        "reason",
        "action",
        "side",
        "interval",
        "timeframe",
        "price",
        "close",
        "volume",
        "timestamp",
        "time",
    )
    parts: list[str] = []
    for key in preferred:
        if key not in payload:
            continue
        value = " ".join(str(payload.get(key) or "").split())
        if value:
            parts.append(f"{key}={value[:120]}")
    if not parts:
        parts = [
            f"{key}={' '.join(str(value).split())[:100]}"
            for key, value in list(payload.items())[:4]
        ]
    return " · ".join(parts)[:500] or "No additional payload details."


def _provider_alert_text(event: dict[str, Any]) -> str:
    symbol = str(event.get("symbol") or "UNKNOWN").upper()
    event_type = str(event.get("event_type") or "provider-event").replace("_", " ")
    provider = str(event.get("provider") or "unknown")
    priority = int(event.get("priority") or 0)
    return "\n".join(
        [
            "## Breaking Provider Alert",
            f"**{symbol} · {event_type.upper()}**",
            f"Provider **{provider}** · priority **{priority}**",
            f"**Details:** {_payload_summary(event.get('payload'))}",
            f"Received **{event.get('received_at') or engine.iso_now()}**.",
            "The ticker was moved forward in the research universe. This event is "
            "informational and is not an automatic trade entry.",
        ]
    )


def _alert_recorded(connection, alert_key: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM alerts WHERE alert_key=? LIMIT 1",
        (alert_key,),
    ).fetchone()
    return bool(row)


def _requeue_provider_event(event_id: int, detail: str) -> None:
    retry_at = (datetime.now().astimezone() + timedelta(minutes=1)).isoformat(
        timespec="seconds"
    )
    connection = dynamic_universe.connect()
    try:
        connection.execute(
            """
            UPDATE provider_events
            SET status='PENDING', available_at=?, processed_at=NULL, error=?
            WHERE id=?
            """,
            (retry_at, detail[:1000], int(event_id)),
        )
        connection.commit()
    finally:
        connection.close()


def _breaking_alerts_status_card(processed: int, failures: list[str]) -> str:
    queue = _provider_queue_counts()
    latest = engine.latest_observation("provider-event-latest")
    latest_payload = (latest or {}).get("payload") or {}
    lines = [
        "## Tradysquids Breaking Alerts Status",
        (
            f"Provider queue checked · processed this pass **{processed}** · pending "
            f"**{queue['PENDING']}** · processing **{queue['PROCESSING']}** · errors "
            f"**{queue['ERROR']}**"
        ),
        "### Latest qualifying provider event",
    ]
    if latest_payload:
        lines.append(
            f"**{latest_payload.get('symbol', 'UNKNOWN')} · "
            f"{str(latest_payload.get('event_type') or 'event').replace('_', ' ')}** · "
            f"{latest_payload.get('provider', 'unknown')} · "
            f"{latest_payload.get('received_at') or (latest or {}).get('observed_at')}"
        )
        lines.append(
            f"Details: {_payload_summary(latest_payload.get('payload'))}"
        )
    else:
        lines.append(
            "No qualifying provider event has been recorded yet. The queue is still "
            "checked every 15 seconds."
        )
    if failures:
        lines.extend(
            [
                "### Delivery failures",
                *[f"• {item}" for item in failures[:8]],
            ]
        )
    else:
        lines.append(
            "No provider-event delivery failure is currently recorded. Individual "
            "alerts appear above this status card when they arrive."
        )
    lines.append(f"Heartbeat **{engine.iso_now()}**.")
    return "\n".join(lines)[:5900]


def visible_provider_event_job(connection) -> str:
    """Process provider events and make #breaking-alerts visibly truthful."""
    events = dynamic_universe.claim_events(limit=25)
    completed = 0
    failures: list[str] = []

    for event in events:
        event_id = int(event["id"])
        try:
            dynamic_universe.upsert_candidates(
                [
                    dynamic_universe.Candidate(
                        event["symbol"],
                        event["provider"],
                        score=100 + float(event["priority"]),
                        reason=f"{event['provider']} {event['event_type']}",
                        ttl_minutes=240,
                    )
                ]
            )
            payload = {
                "id": event_id,
                "event_key": event.get("event_key"),
                "symbol": event["symbol"],
                "provider": event["provider"],
                "event_type": event["event_type"],
                "priority": event["priority"],
                "received_at": event.get("received_at"),
                "payload": event.get("payload"),
            }
            engine.store_observation(
                connection,
                f"provider-event:{event['provider']}",
                payload,
            )
            engine.store_observation(connection, "provider-event-latest", payload)

            alert_key = f"provider-event:{event.get('event_key') or event_id}"
            sent = engine.publish_change_only(
                connection,
                alert_key,
                _provider_alert_text(event),
                logical_channel="breaking_alerts",
                minimum_minutes=0,
            )
            if not sent and not _alert_recorded(connection, alert_key):
                detail = "Discord did not acknowledge the breaking-alert message"
                _requeue_provider_event(event_id, detail)
                failures.append(f"{event['symbol']}:{detail}")
                continue

            dynamic_universe.complete_event(event_id)
            completed += 1
        except Exception as exc:
            detail = f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}"
            dynamic_universe.complete_event(event_id, error=detail)
            failures.append(f"{event.get('symbol', 'UNKNOWN')}:{detail}")

    heartbeat_key = "breaking-alerts-heartbeat-at"
    if _dashboard_due(
        connection,
        heartbeat_key,
        BREAKING_ALERT_HEARTBEAT_MINUTES,
        force=bool(events or failures),
    ):
        _require_dashboard(
            connection,
            "breaking_alerts",
            "breaking-alerts-status",
            _breaking_alerts_status_card(completed, failures),
        )
        engine.set_state(connection, heartbeat_key, engine.iso_now())

    if failures:
        raise RuntimeError("provider-event delivery failed: " + ", ".join(failures))
    return f"{completed}/{len(events)} provider events processed; breaking-alerts heartbeat current"


def _clone_job(job, callback):
    return engine.Job(
        job.name,
        job.interval,
        callback,
        market_hours_only=job.market_hours_only,
        after_hours_interval=job.after_hours_interval,
        background=job.background,
        provider_heavy=job.provider_heavy,
        retry_interval=job.retry_interval,
    )


def install_market_intelligence_visibility() -> None:
    global _VISIBILITY_INSTALLED
    if _VISIBILITY_INSTALLED:
        return

    replaced = False
    jobs = []
    for job in engine.JOBS:
        if job.name == "provider-event-queue":
            jobs.append(_clone_job(job, visible_provider_event_job))
            replaced = True
        else:
            jobs.append(job)
    if not replaced:
        raise RuntimeError("provider-event-queue job is missing")

    if not any(job.name == "premarket-visibility" for job in jobs):
        jobs.append(
            engine.Job(
                "premarket-visibility",
                timedelta(minutes=PREMARKET_VISIBILITY_MINUTES),
                premarket_visibility_job,
                after_hours_interval=timedelta(
                    minutes=PREMARKET_AFTER_HOURS_MINUTES
                ),
                background=True,
                provider_heavy=True,
                retry_interval=timedelta(minutes=2),
            )
        )
    engine.JOBS = jobs
    _VISIBILITY_INSTALLED = True


# Diagnostics and the repair worker itself are protected by the supervisor
# heartbeat. Visible activity jobs remain eligible for targeted repair if they
# fail, stall, or miss an interval.
always_on_operations.OPERATIONS_JOB_NAMES = {
    "scheduler-diagnostics",
    "automatic-self-repair",
}
always_on_operations.install()
install_market_intelligence_visibility()


def validate_visibility_installation() -> None:
    jobs = {job.name: job for job in engine.JOBS}
    if "premarket-visibility" not in jobs:
        raise RuntimeError("premarket visibility job was not installed")
    if jobs.get("provider-event-queue") is None:
        raise RuntimeError("provider event queue job is missing")
    if jobs["provider-event-queue"].callback is not visible_provider_event_job:
        raise RuntimeError("provider event Discord routing was not installed")


validate_visibility_installation()


if __name__ == "__main__":
    raise SystemExit(engine.main())
