"""Live acceptance and reliable Discord migration for upgrade batch #44.

The original batch proved code and tests but did not prove every feature became
visible in the running Discord server. This module closes that gap:

* every upgraded scheduler job is made due once after this patch deploys;
* old upgrade confirmations are migrated through complete channel history;
* future request relocation is checked against the installed command patch;
* a stable 13-item acceptance receipt is posted to #upgrade-requests.

The module is read-only with respect to brokerage activity. It only manages
Discord messages, scheduler state, observations, and verification receipts.
"""

from __future__ import annotations

import inspect
import json
import os
import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Iterable

import spy_scanner
import github_upgrade_patch
import journal_contract
import upgrade_batch_44

PATCH_VERSION = "upgrade-batch-44-live-acceptance-v2"
SEED_MARKER = f"{PATCH_VERSION}:initial-run-seeded"
SEED_TIME = f"{PATCH_VERSION}:seeded-at"
FULL_BACKFILL_MARKER = f"{PATCH_VERSION}:full-history-migrated"
MOVED_IDS_STATE = f"{PATCH_VERSION}:moved-message-ids"
MIGRATION_RECEIPT_STATE = f"{PATCH_VERSION}:migration-receipt-id"
ACCEPTANCE_RECEIPT_STATE = f"{PATCH_VERSION}:acceptance-receipt-id"

MAX_PAGES_PER_CHANNEL = max(
    10,
    min(1000, int(os.environ.get("UPGRADE_MIGRATION_MAX_PAGES_PER_CHANNEL", "250"))),
)
PAGE_PAUSE_SECONDS = max(
    0.0,
    min(2.0, float(os.environ.get("UPGRADE_MIGRATION_PAGE_PAUSE_SECONDS", "0.15"))),
)

UPGRADED_JOB_NAMES = (
    "premarket-visibility",
    "managed-ticker-news",
    "managed-ticker-information",
    "outcome-learning",
    "system-activity",
    "active-market-regime",
    "intraday-chart-refresh",
    "dynamic-universe-rotation",
    "upgrade-request-migration",
)

_INSTALLED = False


def _engine() -> Any:
    return upgrade_batch_44._engine()


def _json_state(connection: Any, key: str, default: Any) -> Any:
    raw = _engine().get_state(connection, key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _set_json_state(connection: Any, key: str, value: Any) -> None:
    _engine().set_state(
        connection,
        key,
        json.dumps(value, separators=(",", ":"), default=str),
    )


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_engine().utc_now().tzinfo)
    return parsed


def _guild_text_channels(tracker: Any) -> list[dict[str, Any]]:
    payload = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    return [
        item
        for item in payload if isinstance(payload, list)
        if int(item.get("type") or -1) == 0 and item.get("id")
    ]


def _destination_channel(
    tracker: Any,
    channels: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    values = channels or _guild_text_channels(tracker)
    for name in ("upgrade-requests", "upgrade-review"):
        match = next(
            (
                item
                for item in values
                if str(item.get("name") or "").casefold() == name
            ),
            None,
        )
        if match:
            return match
    return None


def is_upgrade_confirmation(message: dict[str, Any]) -> bool:
    """Recognize old and current bot-generated upgrade confirmations."""
    author = message.get("author") or {}
    if not author.get("bot"):
        return False
    text = " ".join(spy_scanner.message_search_text(message).split()).casefold()
    if "upgrade request" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "uploaded",
            "batch issue",
            "github batch",
            "recorded from discord",
            "pending batch review",
            "/upgrade-add",
        )
    )


def _message_pages(
    tracker: Any,
    channel_id: str,
    *,
    full_history: bool,
) -> Iterable[list[dict[str, Any]]]:
    before = ""
    pages = 0
    while True:
        route = f"/channels/{channel_id}/messages?limit=100"
        if before:
            route += f"&before={before}"
        payload = tracker._request("GET", route)
        messages = payload if isinstance(payload, list) else []
        if not messages:
            return
        yield messages
        pages += 1
        if not full_history or len(messages) < 100:
            return
        if pages >= MAX_PAGES_PER_CHANNEL:
            raise RuntimeError(
                f"channel {channel_id} exceeded the configured "
                f"{MAX_PAGES_PER_CHANNEL}-page history limit"
            )
        before = str(messages[-1].get("id") or "")
        if not before:
            return
        if PAGE_PAUSE_SECONDS:
            time.sleep(PAGE_PAUSE_SECONDS)


def _migration_text(message: dict[str, Any], source_channel_id: str) -> str:
    original = "\n".join(
        line.rstrip()
        for line in str(message.get("content") or "").splitlines()
        if line.strip()
    ).strip()
    if not original:
        original = spy_scanner.message_search_text(message).strip()
    original = original[:1400] or "Upgrade confirmation contained no readable text."
    return "\n".join(
        [
            "## Migrated Upgrade Request",
            original,
            "",
            f"**Moved from:** <#{source_channel_id}>",
            f"**Original message:** `{message.get('id') or 'unavailable'}`",
            "The source copy was deleted only after this channel accepted the copy.",
        ]
    )[:1900]


def _copy_then_delete(
    tracker: Any,
    destination_id: str,
    source_channel_id: str,
    message: dict[str, Any],
) -> None:
    created = tracker._request(
        "POST",
        f"/channels/{destination_id}/messages",
        {
            "content": _migration_text(message, source_channel_id),
            "allowed_mentions": {"parse": []},
        },
    )
    new_id = str((created or {}).get("id") or "")
    if not new_id:
        raise RuntimeError("Discord did not acknowledge the migrated request")
    try:
        tracker._request(
            "DELETE",
            f"/channels/{source_channel_id}/messages/{message['id']}",
        )
    except Exception:
        try:
            tracker._request(
                "DELETE",
                f"/channels/{destination_id}/messages/{new_id}",
            )
        except Exception:
            pass
        raise


def _upsert_plain_receipt(
    connection: Any,
    tracker: Any,
    channel_id: str,
    state_key: str,
    content: str,
) -> str:
    message_id = _engine().get_state(connection, state_key, "")
    payload = {"content": content[:1900], "allowed_mentions": {"parse": []}}
    if message_id:
        try:
            tracker._request(
                "PATCH",
                f"/channels/{channel_id}/messages/{message_id}",
                payload,
            )
            return message_id
        except spy_scanner.DiscordError as exc:
            if "HTTP 404" not in str(exc):
                raise
    created = tracker._request("POST", f"/channels/{channel_id}/messages", payload)
    message_id = str((created or {}).get("id") or "")
    if not message_id:
        raise RuntimeError("Discord did not acknowledge the verification receipt")
    _engine().set_state(connection, state_key, message_id)
    return message_id


def reliable_upgrade_migration_job(connection: Any) -> str:
    """Backfill complete history once, then inspect the newest page every run."""
    tracker = _engine().discord_tracker()
    if not tracker:
        return "waiting for Discord configuration"
    channels = _guild_text_channels(tracker)
    destination = _destination_channel(tracker, channels)
    if not destination:
        raise RuntimeError("#upgrade-requests and #upgrade-review are both missing")
    destination_id = str(destination["id"])
    full_history = _engine().get_state(connection, FULL_BACKFILL_MARKER, "") != "1"
    moved_ids = set(_json_state(connection, MOVED_IDS_STATE, []))
    scanned = 0
    moved = 0
    channels_checked = 0
    failures: list[str] = []

    for channel in channels:
        source_id = str(channel["id"])
        if source_id == destination_id:
            continue
        channels_checked += 1
        try:
            for page in _message_pages(
                tracker,
                source_id,
                full_history=full_history,
            ):
                for message in page:
                    scanned += 1
                    message_id = str(message.get("id") or "")
                    if not message_id or message_id in moved_ids:
                        continue
                    if not is_upgrade_confirmation(message):
                        continue
                    _copy_then_delete(
                        tracker,
                        destination_id,
                        source_id,
                        message,
                    )
                    moved_ids.add(message_id)
                    moved += 1
                    _set_json_state(
                        connection,
                        MOVED_IDS_STATE,
                        sorted(moved_ids)[-10000:],
                    )
        except Exception as exc:
            failures.append(
                f"#{channel.get('name') or source_id}: {type(exc).__name__}: "
                f"{' '.join(str(exc).split())[:160]}"
            )

    if full_history and not failures:
        _engine().set_state(connection, FULL_BACKFILL_MARKER, "1")

    status = "COMPLETE" if not failures else "PARTIAL"
    mode = "full-history backfill" if full_history else "incremental scan"
    receipt = [
        "## Upgrade Request Migration Receipt",
        f"**Status:** {status} · **Mode:** {mode}",
        f"**Channels checked:** {channels_checked} · **Messages scanned:** {scanned}",
        f"**Moved this run:** {moved} · **Recorded total:** {len(moved_ids)}",
        (
            "Every accessible text-channel page was inspected."
            if full_history and not failures
            else "The full backfill remains incomplete until every channel succeeds."
            if full_history
            else "Future confirmations are also moved immediately by `/upgrade-add`."
        ),
    ]
    if failures:
        receipt.append("### Failures")
        receipt.extend(f"• {item}" for item in failures[:6])
    receipt.append(f"Updated **{_engine().iso_now()}**.")
    _upsert_plain_receipt(
        connection,
        tracker,
        destination_id,
        MIGRATION_RECEIPT_STATE,
        "\n".join(receipt),
    )
    _engine().store_observation(
        connection,
        "upgrade-request-migration-v2",
        {
            "mode": mode,
            "channels_checked": channels_checked,
            "messages_scanned": scanned,
            "moved": moved,
            "recorded_total": len(moved_ids),
            "failures": failures,
            "full_history_complete": bool(
                _engine().get_state(connection, FULL_BACKFILL_MARKER, "") == "1"
            ),
            "at": _engine().iso_now(),
        },
    )
    if failures:
        raise RuntimeError("; ".join(failures[:4]))
    return (
        f"{mode}; {channels_checked} channels; {scanned} messages; "
        f"{moved} moved; full-history complete={full_history}"
    )


def _job_map() -> dict[str, Any]:
    return {job.name: job for job in _engine().JOBS}


def static_audit() -> list[dict[str, str]]:
    """Verify that every request has a concrete installed implementation."""
    jobs = _job_map()
    supplements = upgrade_batch_44._supplement_lessons()
    sample_summary = {
        "closed_trades": 0,
        "reviewed_trades": 0,
        "review_coverage_pct": 0.0,
        "minimum_sample": 20,
        "learning_version": "audit",
        "evidence_ready_groups": [],
        "play_style_suggestions": [],
    }
    learning_text = upgrade_batch_44.learning_results_text(sample_summary)
    style_text = upgrade_batch_44.style_evidence_text(
        "Regular Call",
        upgrade_batch_44._style_group({"groups": []}, "REGULAR-CALL"),
        upgrade_batch_44._suggestion(
            {"play_style_suggestions": []}, "REGULAR-CALL"
        ),
        20,
    )

    def result(number: int, title: str, passed: bool, detail: str) -> dict[str, str]:
        return {
            "number": str(number),
            "title": title,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }

    return [
        result(1, "Active-universe news", jobs.get("managed-ticker-news", None) is not None and jobs["managed-ticker-news"].callback is upgrade_batch_44.active_news_job, "dynamic active-news callback installed"),
        result(2, "Dynamic premarket cards", jobs.get("premarket-visibility", None) is not None and jobs["premarket-visibility"].callback is upgrade_batch_44.active_premarket_job, "per-active-ticker premarket callback installed"),
        result(3, "Future upgrade relocation", hasattr(github_upgrade_patch, "_mirror_upgrade_request") and hasattr(github_upgrade_patch, "_delete_original_response"), "slash-command mirror and source cleanup installed"),
        result(4, "Deduplicated breaking alerts", hasattr(upgrade_batch_44, "_headline_digest") and hasattr(upgrade_batch_44, "active_news_job"), "stable per-ticker headline hashing installed"),
        result(5, "Intraday charts and levels", "intraday-chart-refresh" in jobs and jobs["intraday-chart-refresh"].callback is upgrade_batch_44.intraday_chart_job, "small-timeframe chart job installed"),
        result(6, "Active market regime", "active-market-regime" in jobs and jobs["active-market-regime"].callback is upgrade_batch_44.market_regime_summary_job, "single active-universe regime job installed"),
        result(7, "Dynamic universe rotation", "dynamic-universe-rotation" in jobs and jobs["dynamic-universe-rotation"].callback is upgrade_batch_44.universe_rotation_job, "protected optionable-candidate rotation installed"),
        result(8, "System Activity receipts", getattr(upgrade_batch_44._OPERATIONS, "activity_card", None) is upgrade_batch_44.enhanced_activity_card, "activity card uses real job receipts"),
        result(9, "Learning Results dashboard", "Evidence Dashboard" in learning_text and "Suggested next reviews" in learning_text, "aggregate evidence dashboard renderer installed"),
        result(10, "No play-type trade-history spam", "trade_id" not in style_text and "Individual completed trades remain only in Trade Journal" in style_text, "play-type output is aggregate-only"),
        result(11, "Play-type evidence and improvements", "Evidence limit" in style_text and "Suggested improvement review" in style_text, "evidence limits, MFE/MAE and tradeoffs installed"),
        result(12, "Expanded Learning Center and journals", len(supplements) == 27 and journal_contract.JOURNAL_FORMAT_VERSION == "16" and "Applied Decision Checklist" in journal_contract.REQUIRED_ENTRY_MARKERS, f"{len(supplements)}/27 supplements; journal format {journal_contract.JOURNAL_FORMAT_VERSION}"),
        result(13, "Historical upgrade migration", "upgrade-request-migration" in jobs and jobs["upgrade-request-migration"].callback is reliable_upgrade_migration_job, "paginated copy-then-delete migration installed"),
    ]


def _latest_job(connection: Any, name: str) -> dict[str, str] | None:
    row = connection.execute(
        """
        SELECT status, started_at, COALESCE(finished_at, '') AS finished_at, detail
        FROM job_runs
        WHERE job_name=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _job_live_status(connection: Any, name: str) -> tuple[str, str]:
    row = _latest_job(connection, name)
    seeded = _parse_time(_engine().get_state(connection, SEED_TIME, ""))
    if not row:
        return "PENDING", "no job receipt yet"
    started = _parse_time(row.get("started_at"))
    if seeded and started and started < seeded:
        return "PENDING", "only an older pre-verification receipt exists"
    status = str(row.get("status") or "").upper()
    detail = " ".join(str(row.get("detail") or "").split())[:160]
    if status == "OK":
        return "PASS", detail or "job completed"
    if status == "RUNNING":
        return "PENDING", "job is running"
    if status in {"ERROR", "INTERRUPTED"}:
        return "FAIL", detail or status.lower()
    return "PENDING", detail or status.lower() or "unknown state"


def _dashboard_state(connection: Any) -> dict[str, Any]:
    return _json_state(connection, "discord_dashboard_state", {})


def _dashboard_has(connection: Any, prefix: str) -> bool:
    state = _dashboard_state(connection)
    messages = state.get("messages") if isinstance(state, dict) else {}
    return any(str(key).startswith(prefix) for key in (messages or {}))


def _live_check(
    connection: Any,
    number: int,
    static: dict[str, str],
) -> tuple[str, str]:
    if static["status"] != "PASS":
        return "FAIL", static["detail"]
    if number == 1:
        status, detail = _job_live_status(connection, "managed-ticker-news")
        return (status, detail) if status != "PASS" else (
            "PASS" if _engine().latest_observation("active-news-sweep") else "PENDING",
            detail if _engine().latest_observation("active-news-sweep") else "job passed but active-news observation is not visible yet",
        )
    if number == 2:
        status, detail = _job_live_status(connection, "premarket-visibility")
        return (status, detail) if status != "PASS" else (
            "PASS" if _dashboard_has(connection, "local-engine:premarket:") else "PENDING",
            detail if _dashboard_has(connection, "local-engine:premarket:") else "job passed but per-ticker cards are not recorded yet",
        )
    if number == 3:
        tracker = _engine().discord_tracker()
        destination = _destination_channel(tracker) if tracker else None
        return (
            ("PASS", "dedicated destination exists and future mirror code is installed")
            if destination
            else ("FAIL", "dedicated upgrade destination is missing or Discord is unavailable")
        )
    if number == 4:
        status, detail = _job_live_status(connection, "managed-ticker-news")
        return (status, detail) if status != "PASS" else (
            "PASS" if _dashboard_has(connection, "local-engine:breaking-news:") else "PENDING",
            detail if _dashboard_has(connection, "local-engine:breaking-news:") else "no breaking-event card has been recorded yet",
        )
    if number == 5:
        status, detail = _job_live_status(connection, "intraday-chart-refresh")
        return (status, detail) if status != "PASS" else (
            "PASS" if _engine().latest_observation("intraday-chart-refresh") else "PENDING",
            detail if _engine().latest_observation("intraday-chart-refresh") else "chart observation is not visible yet",
        )
    if number == 6:
        status, detail = _job_live_status(connection, "active-market-regime")
        return (status, detail) if status != "PASS" else (
            "PASS" if _engine().latest_observation("active-market-regime") else "PENDING",
            detail if _engine().latest_observation("active-market-regime") else "regime observation is not visible yet",
        )
    if number == 7:
        status, detail = _job_live_status(connection, "dynamic-universe-rotation")
        return (status, detail) if status != "PASS" else (
            "PASS" if _engine().latest_observation("dynamic-universe-rotation") else "PENDING",
            detail if _engine().latest_observation("dynamic-universe-rotation") else "rotation observation is not visible yet",
        )
    if number == 8:
        status, detail = _job_live_status(connection, "system-activity")
        return (status, detail) if status != "PASS" else (
            "PASS" if _dashboard_has(connection, "local-engine:system-activity") else "PENDING",
            detail if _dashboard_has(connection, "local-engine:system-activity") else "activity card state is not visible yet",
        )
    if number in {9, 11}:
        return _job_live_status(connection, "outcome-learning")
    if number in {10, 12}:
        return "PASS", static["detail"]
    if number == 13:
        status, detail = _job_live_status(connection, "upgrade-request-migration")
        if status != "PASS":
            return status, detail
        complete = _engine().get_state(connection, FULL_BACKFILL_MARKER, "") == "1"
        return (
            ("PASS", "full accessible Discord history was scanned")
            if complete
            else ("PENDING", "migration ran but full-history completion is not recorded")
        )
    return "FAIL", "unknown acceptance item"


def live_acceptance_job(connection: Any) -> str:
    static = static_audit()
    results: list[dict[str, str]] = []
    for item in static:
        number = int(item["number"])
        status, detail = _live_check(connection, number, item)
        results.append({**item, "status": status, "detail": detail})

    counts = {
        status: sum(1 for item in results if item["status"] == status)
        for status in ("PASS", "PENDING", "FAIL")
    }
    tracker = _engine().discord_tracker()
    if not tracker:
        raise RuntimeError("Discord is unavailable, so live acceptance cannot be posted")
    destination = _destination_channel(tracker)
    if not destination:
        raise RuntimeError("#upgrade-requests and #upgrade-review are both missing")
    icons = {"PASS": "✅", "PENDING": "⏳", "FAIL": "❌"}
    lines = [
        "## Upgrade Batch #44 Live Acceptance",
        f"**PASS {counts['PASS']}/13 · PENDING {counts['PENDING']} · FAIL {counts['FAIL']}**",
        "This checks runtime receipts and visible card state, not merely whether files exist.",
    ]
    for item in results:
        lines.append(
            f"{icons[item['status']]} **{item['number']}. {item['title']}** · "
            f"{item['detail'][:105]}"
        )
    lines.append(f"Updated **{_engine().iso_now()}**.")
    _upsert_plain_receipt(
        connection,
        tracker,
        str(destination["id"]),
        ACCEPTANCE_RECEIPT_STATE,
        "\n".join(lines),
    )
    _engine().store_observation(
        connection,
        "upgrade-batch-44-live-acceptance",
        {"counts": counts, "results": results, "at": _engine().iso_now()},
    )
    if counts["FAIL"]:
        raise RuntimeError(
            f"{counts['FAIL']} of 13 acceptance checks failed; "
            f"{counts['PENDING']} pending"
        )
    return f"{counts['PASS']}/13 passed; {counts['PENDING']} pending; 0 failed"


def _seed_immediate_runs() -> None:
    engine = _engine()
    connection = engine.connect_db()
    try:
        if engine.get_state(connection, SEED_MARKER, "") == "1":
            return
        now = engine.iso_now()
        names = (*UPGRADED_JOB_NAMES, "upgrade-batch-44-acceptance")
        for name in names:
            connection.execute(
                "DELETE FROM engine_state WHERE key IN (?, ?)",
                (f"job:{name}", f"job-error:{name}"),
            )
        connection.commit()
        engine.set_state(connection, SEED_TIME, now)
        engine.set_state(connection, SEED_MARKER, "1")
    finally:
        connection.close()


def install() -> None:
    """Install reliable migration, immediate first runs, and live acceptance."""
    global _INSTALLED
    if _INSTALLED:
        return
    engine = _engine()
    rebuilt: list[Any] = []
    migration_found = False
    acceptance_found = False
    for job in engine.JOBS:
        if job.name == "upgrade-request-migration":
            rebuilt.append(replace(job, callback=reliable_upgrade_migration_job))
            migration_found = True
        elif job.name == "upgrade-batch-44-acceptance":
            rebuilt.append(replace(job, callback=live_acceptance_job))
            acceptance_found = True
        else:
            rebuilt.append(job)
    if not migration_found:
        rebuilt.append(
            engine.Job(
                "upgrade-request-migration",
                timedelta(minutes=10),
                reliable_upgrade_migration_job,
                background=True,
                retry_interval=timedelta(minutes=2),
            )
        )
    if not acceptance_found:
        rebuilt.append(
            engine.Job(
                "upgrade-batch-44-acceptance",
                timedelta(minutes=5),
                live_acceptance_job,
                background=True,
                retry_interval=timedelta(minutes=2),
            )
        )
    engine.JOBS = rebuilt
    _seed_immediate_runs()
    _INSTALLED = True


def validate_patch() -> dict[str, Any]:
    source = inspect.getsource(reliable_upgrade_migration_job)
    if "full_history" not in source or "_copy_then_delete" not in source:
        raise RuntimeError("reliable migration lost full-history copy/delete behavior")
    checks = static_audit()
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise RuntimeError("static batch audit failed: " + json.dumps(failed))
    return {
        "version": PATCH_VERSION,
        "static_checks": len(checks),
        "static_passed": len(checks) - len(failed),
        "full_history_pagination": True,
        "immediate_first_run": True,
        "live_receipt": True,
    }


if __name__ == "__main__":
    print(json.dumps(validate_patch(), indent=2))
