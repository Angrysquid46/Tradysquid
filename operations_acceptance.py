"""Acceptance checks for visible always-on Discord operations.

The Windows installer runs this only after the supervisor recovery test passes.
It verifies the scheduler heartbeat, registered jobs, recent job receipts,
required Discord channels, visible dashboard cards, and closed-market research.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import always_on_operations as operations
import ford_scan
import local_information_engine as engine


ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "state" / "operations-acceptance.json"
TIMEOUT_SECONDS = 360
REQUIRED_JOBS = {
    "scheduler-diagnostics",
    "system-activity",
    "automatic-self-repair",
    "off-hours-universe-screen",
    "rotating-event-sweep",
}
REQUIRED_CHANNELS = {
    "system-activity": "Always-On Tradysquids Activity",
    "automation-diagnostics": "Automation Diagnostics and Self-Repair",
    "regular-calls": "Regular Call Performance",
    "regular-puts": "Regular Put Performance",
    "swing-calls": "Swing Call Performance",
    "swing-puts": "Swing Put Performance",
    "bull-put-spreads": "Bull Put Spread Performance",
    "bear-call-spreads": "Bear Call Spread Performance",
}


class OperationsAcceptanceFailure(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(REPORT_PATH)


def latest_job(connection, name: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def recent_receipt(row: dict[str, Any] | None, max_age_minutes: int) -> bool:
    if not row or str(row.get("status") or "") not in {"OK", "RUNNING"}:
        return False
    value = str(row.get("finished_at") or row.get("started_at") or "")
    age = operations.age_seconds(value)
    return age is not None and age <= max_age_minutes * 60


def discord_channels_and_cards() -> dict[str, Any]:
    tracker = ford_scan.DiscordTracker(ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID)
    if not tracker.enabled:
        raise OperationsAcceptanceFailure("Discord bot token and guild ID are required.")
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    by_name = {
        str(item.get("name") or "").casefold(): item
        for item in channels
        if item.get("type") == 0
    }
    result: dict[str, Any] = {}
    for name, expected_title in REQUIRED_CHANNELS.items():
        channel = by_name.get(name.casefold())
        if not channel:
            raise OperationsAcceptanceFailure(f"Discord channel #{name} is missing.")
        messages = tracker._request("GET", f"/channels/{channel['id']}/messages?limit=30")
        bot_messages = [
            message
            for message in messages
            if (message.get("author") or {}).get("bot") or message.get("webhook_id")
        ]
        matching = next(
            (
                message
                for message in bot_messages
                if expected_title.casefold() in ford_scan.message_search_text(message).casefold()
            ),
            None,
        )
        if not matching:
            raise OperationsAcceptanceFailure(
                f"#{name} exists but does not contain the expected live `{expected_title}` card."
            )
        result[name] = {
            "channel_id": str(channel["id"]),
            "message_id": str(matching.get("id") or ""),
        }
    return result


def trade_journals() -> dict[str, Any]:
    """Verify every recorded trade has one usable, learning-backed Discord journal."""
    tracker = ford_scan.DiscordTracker(ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID)
    if not tracker.enabled:
        raise OperationsAcceptanceFailure("Discord bot token and guild ID are required.")
    rows = ford_scan.read_log()
    missing_threads = [row.get("trade_id") or "unknown" for row in rows if not row.get("discord_thread_id")]
    if missing_threads:
        raise OperationsAcceptanceFailure(
            f"{len(missing_threads)} trades are missing Discord journal threads: "
            + ", ".join(missing_threads[:8])
        )
    thread_ids = [str(row["discord_thread_id"]) for row in rows]
    if len(thread_ids) != len(set(thread_ids)):
        raise OperationsAcceptanceFailure(
            "Multiple trades share the same Discord journal thread."
        )

    closed_count = 0
    for row in rows:
        trade_id = row.get("trade_id") or "unknown"
        messages = tracker._request(
            "GET", f"/channels/{row['discord_thread_id']}/messages?limit=100"
        )
        combined = "\n".join(ford_scan.message_search_text(message) for message in messages)
        if "Applied Learning Center Analysis" not in combined:
            raise OperationsAcceptanceFailure(
                f"Trade {trade_id} journal is missing applied Learning Center analysis."
            )
        if str(row.get("outcome") or "").upper() in {"WIN", "LOSS", "FLAT"}:
            closed_count += 1
            if "Post-Trade Learning" not in combined:
                raise OperationsAcceptanceFailure(
                    f"Closed trade {trade_id} journal is missing its post-trade learning review."
                )
    return {
        "trade_count": len(rows),
        "closed_trade_count": closed_count,
        "all_have_unique_journals": True,
        "all_apply_learning_center": True,
        "all_closed_have_reviews": True,
    }


def operations_ready() -> tuple[bool, dict[str, Any]]:
    operations.install()
    registered = {job.name for job in engine.JOBS}
    missing_jobs = sorted(REQUIRED_JOBS - registered)
    connection = engine.connect_db()
    try:
        receipts = {name: latest_job(connection, name) for name in REQUIRED_JOBS}
        diagnostics = latest_job(connection, "scheduler-diagnostics")
        activity = latest_job(connection, "system-activity")
        repair = latest_job(connection, "automatic-self-repair")
        off_hours = latest_job(connection, "off-hours-universe-screen")
        events = latest_job(connection, "rotating-event-sweep")
        off_hours_observation = engine.latest_observation("off-hours-universe-screen")
        event_observation = engine.latest_observation("rotating-event-sweep")
    finally:
        connection.close()

    market_open = operations.market_open_now()
    core_ok = (
        recent_receipt(diagnostics, 15)
        and recent_receipt(activity, 15)
        and recent_receipt(repair, 15)
    )
    event_ok = recent_receipt(events, operations.EVENT_SWEEP_MINUTES + 15) and bool(
        event_observation
    )
    if market_open:
        off_hours_ok = recent_receipt(
            off_hours, operations.OFF_HOURS_SCREEN_MINUTES + 15
        )
    else:
        off_hours_ok = recent_receipt(
            off_hours, operations.OFF_HOURS_SCREEN_MINUTES + 15
        ) and bool(off_hours_observation)
    heartbeat_ok = operations.heartbeat_healthy(12)
    ready = not missing_jobs and core_ok and event_ok and off_hours_ok and heartbeat_ok
    return ready, {
        "registered_jobs": sorted(registered.intersection(REQUIRED_JOBS)),
        "missing_jobs": missing_jobs,
        "heartbeat_healthy": heartbeat_ok,
        "market_open": market_open,
        "receipts": receipts,
        "off_hours_observation": (off_hours_observation or {}).get("observed_at"),
        "event_observation": (event_observation or {}).get("observed_at"),
    }


def post_report(message: str) -> None:
    try:
        tracker = ford_scan.DiscordTracker(ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID)
        channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
        channel = next(
            (
                item
                for item in channels
                if item.get("type") == 0
                and str(item.get("name") or "").casefold() == "system-health"
            ),
            None,
        )
        if channel:
            title = message.splitlines()[0].strip("# *✅❌ ")
            tracker.upsert_singleton_message(
                str(channel["id"]), message[:1900], title
            )
    except Exception:
        pass


def run_acceptance() -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": 1,
        "status": "RUNNING",
        "started_at": now_iso(),
        "checks": {},
    }
    write_report(report)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    latest_detail: dict[str, Any] = {}
    latest_error = ""
    while time.monotonic() < deadline:
        try:
            ready, detail = operations_ready()
            latest_detail = detail
            if ready:
                cards = discord_channels_and_cards()
                journals = trade_journals()
                report["checks"]["operations"] = detail
                report["checks"]["discord_cards"] = cards
                report["checks"]["trade_journals"] = journals
                report["status"] = "PASSED"
                report["completed_at"] = now_iso()
                write_report(report)
                post_report(
                    "✅ **Tradysquids always-on operations acceptance PASSED**\n"
                    "• scheduler heartbeat is fresh\n"
                    "• interval diagnostics and self-repair are firing\n"
                    "• #system-activity contains a live receipt card\n"
                    "• #automation-diagnostics contains the fault ledger\n"
                    "• rotating event sweep produced a receipt\n"
                    "• closed-market research is active when the market is closed"
                )
                return report
        except Exception as exc:
            latest_error = f"{type(exc).__name__}: {exc}"
        time.sleep(5)
    raise OperationsAcceptanceFailure(
        "Always-on operations did not become fully visible before timeout. "
        f"Last detail={latest_detail}; last error={latest_error or 'none'}."
    )


def main() -> int:
    try:
        report = run_acceptance()
    except Exception as exc:
        report = {
            "version": 1,
            "status": "FAILED",
            "completed_at": now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_report(report)
        post_report(
            "❌ **Tradysquids always-on operations acceptance FAILED**\n"
            f"```{str(exc)[:1400]}```\n"
            "The installation is not considered complete."
        )
        print(report["error"], file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
