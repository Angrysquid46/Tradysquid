"""Reconcile Discord performance reports against the complete canonical trade ledger.

The legacy report path calculated historical close dates and then discarded them,
so only today's daily recap and the week derived from that one date were refreshed.
It also relied only on per-trade acknowledgement changes to rebuild strategy cards,
which meant a reporting-code deployment could leave stale Discord totals in place.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

import ford_scan


REPORT_VERSION = "performance-ledger-v2"
RECENT_BUSINESS_DAYS = 15
MAX_HISTORICAL_DAILY_DATES = 45
MAX_WEEKLY_REPORTS = 12
_INSTALLED = False

_ORIGINAL_CLOSED_ROWS = ford_scan.closed_rows
_ORIGINAL_FORMAT_DAILY_RECAP = ford_scan.format_daily_recap
_ORIGINAL_FORMAT_WEEKLY_REPORT = ford_scan.format_weekly_report
_ORIGINAL_FORMAT_STRATEGY_BREAKDOWN = ford_scan.format_strategy_breakdown
_ORIGINAL_FORMAT_PERFORMANCE_STATS = ford_scan.format_performance_stats


def effective_closed_at(row: dict[str, Any]) -> datetime | None:
    """Return the best recorded close timestamp without inventing market facts."""
    for key in ("closed_at", "last_evaluated_at", "timestamp"):
        parsed = ford_scan.parse_iso(str(row.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def rows_closed_on(
    rows: list[dict[str, str]], target_date: date
) -> list[dict[str, str]]:
    return [
        row
        for row in _ORIGINAL_CLOSED_ROWS(rows)
        if (closed_at := effective_closed_at(row)) is not None
        and closed_at.date() == target_date
    ]


def rows_closed_between(
    rows: list[dict[str, str]], start_date: date, end_date: date
) -> list[dict[str, str]]:
    return [
        row
        for row in _ORIGINAL_CLOSED_ROWS(rows)
        if (closed_at := effective_closed_at(row)) is not None
        and start_date <= closed_at.date() <= end_date
    ]


def _insert_after_heading(content: str, additions: list[str]) -> str:
    lines = content.splitlines()
    if not lines:
        return "\n".join(additions)[:2000]
    insert_at = 1
    if len(lines) > 1 and not lines[1].startswith("### "):
        insert_at = 2
    updated = lines[:insert_at] + additions + lines[insert_at:]
    return "\n".join(updated)[:2000]


def _week_window(today: date) -> tuple[date, date]:
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return monday, min(today, friday)


def format_daily_recap(
    rows: list[dict[str, str]],
    report_date: date,
    *,
    market_open: bool,
) -> str:
    completed = rows_closed_on(rows, report_date)
    content = _ORIGINAL_FORMAT_DAILY_RECAP(
        rows, report_date, market_open=market_open
    )
    additions = [
        f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades for this date."
    ]
    if len(completed) > 8:
        additions.append(
            f"The card lists the latest 8 trades; totals include all **{len(completed)}**."
        )
    return _insert_after_heading(content, additions)


def format_weekly_report(
    rows: list[dict[str, str]], report_date: date, *, final: bool = False
) -> str:
    monday = report_date - timedelta(days=report_date.weekday())
    completed = rows_closed_between(rows, monday, report_date)
    content = _ORIGINAL_FORMAT_WEEKLY_REPORT(rows, report_date, final=final)
    day_counts = []
    cursor = monday
    while cursor <= report_date:
        day_counts.append(f"{cursor.strftime('%a')} {len(rows_closed_on(rows, cursor))}")
        cursor += timedelta(days=1)
    return _insert_after_heading(
        content,
        [
            f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades for this week.",
            "**Daily reconciliation:** " + " · ".join(day_counts),
        ],
    )


def format_strategy_breakdown(rows: list[dict[str, str]]) -> str:
    completed = _ORIGINAL_CLOSED_ROWS(rows)
    today = ford_scan.now_ct().date()
    week_start, week_end = _week_window(today)
    this_week = rows_closed_between(rows, week_start, week_end)
    metrics = ford_scan.result_metrics(this_week)

    grouped_count = 0
    groups: dict[str, int] = {}
    for row in completed:
        label = (
            f"{str(row.get('play_type') or 'PLAY').upper()} "
            f"{str(row.get('call_or_put') or '').upper()}"
        ).strip()
        groups[label] = groups.get(label, 0) + 1
        grouped_count += 1
    if grouped_count != len(completed):
        raise RuntimeError(
            "Strategy reconciliation lost canonical trades: "
            f"grouped={grouped_count}, canonical={len(completed)}"
        )

    content = _ORIGINAL_FORMAT_STRATEGY_BREAKDOWN(rows)
    return _insert_after_heading(
        content,
        [
            f"**Canonical ledger coverage:** **{grouped_count}/{len(completed)}** closed trades across **{len(groups)}** strategy groups.",
            (
                f"**Current week {week_start.strftime('%m/%d')}–{week_end.strftime('%m/%d')}:** "
                f"**{len(this_week)} trades** · {int(metrics['wins'])}W / "
                f"{int(metrics['losses'])}L / {int(metrics['scratches'])}S · "
                f"net **{ford_scan.fmt_metric_money(metrics, 'total_pnl')}**"
            ),
        ],
    )


def format_performance_stats(rows: list[dict[str, str]]) -> str:
    completed = _ORIGINAL_CLOSED_ROWS(rows)
    today = ford_scan.now_ct().date()
    week_start, week_end = _week_window(today)
    this_week = rows_closed_between(rows, week_start, week_end)
    content = _ORIGINAL_FORMAT_PERFORMANCE_STATS(rows)
    return _insert_after_heading(
        content,
        [
            f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades.",
            f"**Current week:** **{len(this_week)}** closed trades accounted for.",
        ],
    )


def ledger_signature(rows: list[dict[str, str]]) -> str:
    payload = []
    for row in sorted(
        _ORIGINAL_CLOSED_ROWS(rows),
        key=lambda item: (
            str(item.get("trade_id") or ""),
            str(item.get("closed_at") or ""),
        ),
    ):
        closed_at = effective_closed_at(row)
        payload.append(
            {
                "trade_id": row.get("trade_id"),
                "ticker": row.get("ticker"),
                "play_type": row.get("play_type"),
                "side": row.get("call_or_put"),
                "outcome": row.get("outcome"),
                "closed_at": closed_at.isoformat() if closed_at else "",
                "realized_pl_dollars": row.get("realized_pl_dollars"),
                "pct_gain_loss": row.get("pct_gain_loss"),
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def daily_report_dates(rows: list[dict[str, str]], today: date) -> list[date]:
    historical = {
        closed_at.date()
        for row in _ORIGINAL_CLOSED_ROWS(rows)
        if (closed_at := effective_closed_at(row)) is not None
        and closed_at.date() >= today - timedelta(days=60)
    }
    dates = set(historical)
    dates.add(today)

    cursor = today
    business_days = 0
    while business_days < RECENT_BUSINESS_DAYS:
        if cursor.weekday() < 5:
            dates.add(cursor)
            business_days += 1
        cursor -= timedelta(days=1)

    return sorted(dates)[-MAX_HISTORICAL_DAILY_DATES:]


def weekly_report_starts(today: date) -> list[date]:
    monday = today - timedelta(days=today.weekday())
    return sorted(
        monday - timedelta(days=7 * offset)
        for offset in range(MAX_WEEKLY_REPORTS)
    )


def coverage_snapshot(rows: list[dict[str, str]], today: date) -> dict[str, Any]:
    completed = _ORIGINAL_CLOSED_ROWS(rows)
    missing_dates = [
        str(row.get("trade_id") or "UNKNOWN")
        for row in completed
        if effective_closed_at(row) is None
    ]
    if missing_dates:
        raise RuntimeError(
            "Closed trades are missing every usable close timestamp: "
            + ", ".join(missing_dates[:20])
        )

    week_start, week_end = _week_window(today)
    weekly = rows_closed_between(rows, week_start, week_end)
    daily_total = 0
    cursor = week_start
    while cursor <= week_end:
        daily_total += len(rows_closed_on(rows, cursor))
        cursor += timedelta(days=1)
    if daily_total != len(weekly):
        raise RuntimeError(
            "Daily and weekly ledger coverage disagree: "
            f"daily={daily_total}, weekly={len(weekly)}"
        )

    return {
        "canonical_closed": len(completed),
        "current_week_closed": len(weekly),
        "current_week_daily_total": daily_total,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
    }


def _require_upsert(
    discord: Any,
    logical_name: str,
    state: dict[str, Any],
    state_key: str,
    content: str,
    *,
    search_token: str,
) -> str:
    message_id = discord.upsert_channel_message(
        logical_name,
        state,
        state_key,
        content,
        search_token=search_token,
    )
    if not message_id:
        raise RuntimeError(
            f"Discord did not acknowledge performance card {logical_name}:{state_key}"
        )
    return str(message_id)


def sync_reports(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_open: bool,
) -> None:
    """Backfill recent daily/weekly cards and prove ledger coverage before success."""
    if not discord.ready:
        return

    today = timestamp.date()
    signature = ledger_signature(rows)
    force_rebuild = (
        state.get("performance_reconciliation_version") != REPORT_VERSION
        or state.get("performance_ledger_signature") != signature
    )
    if force_rebuild:
        ford_scan.update_performance_pages(discord, state, rows)

    daily_dates = daily_report_dates(rows, today)
    for report_date in daily_dates:
        daily = format_daily_recap(
            rows,
            report_date,
            market_open=market_open and report_date == today,
        )
        _require_upsert(
            discord,
            "daily_recap",
            state,
            f"daily-recap:{report_date.isoformat()}",
            daily,
            search_token=f"Daily Recap · {report_date.strftime('%m/%d/%y')}",
        )

    for monday in weekly_report_starts(today):
        current_week = monday <= today <= monday + timedelta(days=6)
        friday = monday + timedelta(days=4)
        report_end = min(today, friday) if current_week else friday
        iso_year, iso_week, _ = monday.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly = format_weekly_report(
            rows,
            report_end,
            final=(not current_week or today >= friday),
        )
        _require_upsert(
            discord,
            "weekly_report",
            state,
            f"weekly-report:{week_key}",
            weekly,
            search_token=f"Weekly Report · {monday.strftime('%m/%d')}",
        )

    coverage = coverage_snapshot(rows, today)
    state.update(
        {
            "daily_report_date": today.isoformat(),
            "weekly_report_key": (
                f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
            ),
            "performance_reconciliation_version": REPORT_VERSION,
            "performance_ledger_signature": signature,
            "performance_reconciliation_closed_trades": coverage["canonical_closed"],
            "performance_reconciliation_week_trades": coverage["current_week_closed"],
            "performance_reconciliation_daily_reports": len(daily_dates),
            "performance_reconciliation_weekly_reports": MAX_WEEKLY_REPORTS,
            "performance_reconciliation_checked_at": timestamp.isoformat(),
        }
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ford_scan.rows_closed_on = rows_closed_on
    ford_scan.rows_closed_between = rows_closed_between
    ford_scan.format_daily_recap = format_daily_recap
    ford_scan.format_weekly_report = format_weekly_report
    ford_scan.format_strategy_breakdown = format_strategy_breakdown
    ford_scan.format_performance_stats = format_performance_stats
    ford_scan.sync_reports = sync_reports
    _INSTALLED = True


def validate_reconciliation() -> dict[str, int]:
    rows: list[dict[str, str]] = []
    monday = date(2026, 7, 27)
    for index in range(5):
        row = ford_scan.blank_row()
        closed_at = datetime(2026, 7, 27 + index, 14, 30, tzinfo=ford_scan.MARKET_TZ)
        row.update(
            {
                "trade_id": f"TEST-{index + 1}",
                "timestamp": closed_at.isoformat(),
                "closed_at": closed_at.isoformat() if index != 2 else "",
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": "WIN" if index % 2 == 0 else "LOSS",
                "play_type": "REGULAR",
                "call_or_put": "call" if index % 2 == 0 else "put",
                "ticker": "F",
                "strike": "12",
                "entry_price": "0.50",
                "exit_price": "0.60" if index % 2 == 0 else "0.40",
                "realized_pl_dollars": "10" if index % 2 == 0 else "-10",
                "pct_gain_loss": "20" if index % 2 == 0 else "-20",
            }
        )
        rows.append(row)

    snapshot = coverage_snapshot(rows, date(2026, 8, 1))
    if snapshot["canonical_closed"] != 5 or snapshot["current_week_closed"] != 5:
        raise RuntimeError(f"Synthetic performance reconciliation failed: {snapshot}")
    dates = daily_report_dates(rows, date(2026, 8, 1))
    if not all(monday + timedelta(days=offset) in dates for offset in range(5)):
        raise RuntimeError("Synthetic daily backfill omitted a weekday from the test week")
    return {
        "canonical_closed": snapshot["canonical_closed"],
        "current_week_closed": snapshot["current_week_closed"],
        "daily_dates": len(dates),
        "weekly_reports": len(weekly_report_starts(date(2026, 8, 1))),
    }


if __name__ == "__main__":
    install()
    print(json.dumps(validate_reconciliation(), indent=2))
