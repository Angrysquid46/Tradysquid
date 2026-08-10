"""Build complete Discord performance reports from the canonical trade ledger.

Daily, weekly, strategy, and monthly reporting are separate products. Every
closed trade must appear once in each applicable history view. Summary cards
never substitute for the underlying trade history.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import spy_scanner


REPORT_VERSION = "performance-ledger-v3"
PAGE_SIZE = 10
MAX_MONTHS = 24
_INSTALLED = False

_ORIGINAL_CLOSED_ROWS = spy_scanner.closed_rows

SPY_0DTE_VARIANTS = (
    ("SPY_0DTE_1M", "performance_1m", "results_1m", "1-Minute Strategy"),
    ("SPY_0DTE_5M", "performance_5m", "results_5m", "5-Minute Strategy"),
)

REPORT_ROUTES = {
    "daily_recap": "daily-recap",
    "weekly_report": "weekly-report",
    "performance_1m": "1m-performance",
    "results_1m": "1m-results",
    "performance_5m": "5m-performance",
    "results_5m": "5m-results",
}

REPORT_MARKERS = {
    "daily_recap": (
        "Daily Performance Index",
        "Daily Report ·",
        "Daily Trade History ·",
        "Daily Recap ·",
    ),
    "weekly_report": (
        "Weekly Performance Index",
        "Weekly Report ·",
        "Weekly Trade History ·",
    ),
    "performance_1m": (
        "1-Minute Strategy Monthly Performance Index",
        "1-Minute Strategy Monthly Performance ·",
        "1-Minute Strategy Monthly Trade History ·",
    ),
    "results_1m": (
        "1-Minute Strategy Results",
        "1-Minute Strategy Trade History ·",
    ),
    "performance_5m": (
        "5-Minute Strategy Monthly Performance Index",
        "5-Minute Strategy Monthly Performance ·",
        "5-Minute Strategy Monthly Trade History ·",
    ),
    "results_5m": (
        "5-Minute Strategy Results",
        "5-Minute Strategy Trade History ·",
    ),
}

STATE_PREFIXES = (
    "report-v3:",
    "daily-recap:",
    "weekly-report:",
    "1m-performance",
    "1m-results",
    "5m-performance",
    "5m-results",
)


def effective_closed_at(row: dict[str, Any]) -> datetime | None:
    """Use the best recorded lifecycle timestamp without inventing a date."""
    for key in ("closed_at", "last_evaluated_at", "timestamp"):
        parsed = spy_scanner.parse_iso(str(row.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def canonical_closed_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    completed = list(_ORIGINAL_CLOSED_ROWS(rows))
    missing = [
        str(row.get("trade_id") or "UNKNOWN")
        for row in completed
        if effective_closed_at(row) is None
    ]
    if missing:
        raise RuntimeError(
            "Closed trades are missing every usable lifecycle timestamp: "
            + ", ".join(missing[:25])
        )
    return sorted(
        completed,
        key=lambda row: (
            effective_closed_at(row) or datetime.min.replace(tzinfo=spy_scanner.MARKET_TZ),
            str(row.get("trade_id") or ""),
        ),
    )


def rows_closed_on(rows: list[dict[str, str]], target_date: date) -> list[dict[str, str]]:
    return [
        row
        for row in canonical_closed_rows(rows)
        if effective_closed_at(row).date() == target_date
    ]


def rows_closed_between(
    rows: list[dict[str, str]], start_date: date, end_date: date
) -> list[dict[str, str]]:
    return [
        row
        for row in canonical_closed_rows(rows)
        if start_date <= effective_closed_at(row).date() <= end_date
    ]


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def chunks(values: list[Any], size: int = PAGE_SIZE) -> Iterable[list[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def ledger_signature(rows: list[dict[str, str]]) -> str:
    payload = []
    for row in canonical_closed_rows(rows):
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


def strategy_label(row: dict[str, str]) -> str:
    play_type = str(row.get("play_type") or "PLAY").upper()
    side = str(row.get("call_or_put") or "").upper()
    return f"{play_type} {side}".strip()


def compact_trade_line(row: dict[str, str]) -> str:
    trade_id = str(row.get("trade_id") or "UNKNOWN")[:24]
    ticker = str(row.get("ticker") or "F").upper()[:6]
    label = strategy_label(row)[:18]
    outcome = str(row.get("outcome") or "CLOSED").upper()[:7]
    dollars = spy_scanner.fmt_money(spy_scanner.realized_pl_dollars(row))
    pct = spy_scanner.fmt_pct(spy_scanner.as_float(row.get("pct_gain_loss"), 0.0))
    closed_at = effective_closed_at(row)
    stamp = closed_at.strftime("%m/%d") if closed_at else "date?"
    return f"• **{trade_id}** · {ticker} {label} · **{outcome} {dollars} ({pct})** · {stamp}"


def result_summary(title: str, completed: list[dict[str, str]], period_text: str) -> str:
    metrics = spy_scanner.result_metrics(completed)
    lines = [
        f"## {title}",
        f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades.",
        "### Period",
        period_text,
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        "### Money",
        (
            f"Won **{spy_scanner.fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{spy_scanner.fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{spy_scanner.fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%** · "
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%**"
        ),
    ]
    if completed:
        best = max(
            completed,
            key=lambda row: spy_scanner.as_float(row.get("realized_pl_dollars"), -math.inf)
            or -math.inf,
        )
        worst = min(
            completed,
            key=lambda row: spy_scanner.as_float(row.get("realized_pl_dollars"), math.inf)
            or math.inf,
        )
        lines.extend(
            [
                "### Best / Worst",
                f"Best: {compact_trade_line(best)[2:]}\nWorst: {compact_trade_line(worst)[2:]}",
            ]
        )
    else:
        lines.extend(["### Trade History", "No trades closed during this period."])
    return "\n".join(lines)[:5900]


def history_page(title: str, completed: list[dict[str, str]], page: int, total_pages: int) -> str:
    start = (page - 1) * PAGE_SIZE + 1
    end = start + len(completed) - 1
    return "\n".join(
        [
            f"## {title} · Page {page}/{total_pages}",
            f"**Trade history coverage:** **{start}-{end} of {(total_pages - 1) * PAGE_SIZE + len(completed)}**",
            "### Trades",
            "\n".join(compact_trade_line(row) for row in completed),
        ]
    )[:5900]


def format_daily_recap(
    rows: list[dict[str, str]], report_date: date, *, market_open: bool
) -> str:
    completed = rows_closed_on(rows, report_date)
    status = "LIVE" if market_open else "FINAL"
    return result_summary(
        f"📅 Daily Report · {report_date.strftime('%m/%d/%y')}",
        completed,
        f"**Status:** {status} · {report_date.strftime('%A, %B %d, %Y')}",
    )


def format_weekly_report(
    rows: list[dict[str, str]], report_date: date, *, final: bool = False
) -> str:
    monday = week_start(report_date)
    completed = rows_closed_between(rows, monday, report_date)
    counts = []
    cursor = monday
    while cursor <= report_date:
        counts.append(f"{cursor.strftime('%a')} {len(rows_closed_on(rows, cursor))}")
        cursor += timedelta(days=1)
    return result_summary(
        f"📆 Weekly Report · {monday.strftime('%m/%d')}–{report_date.strftime('%m/%d/%y')}",
        completed,
        (
            f"**Status:** {'FINAL' if final else 'LIVE'}\n"
            f"**Daily reconciliation:** {' · '.join(counts)}"
        ),
    )


def format_monthly_report(rows: list[dict[str, str]], month: date) -> str:
    end = month_end(month)
    completed = rows_closed_between(rows, month, end)
    return result_summary(
        f"📊 Monthly Performance · {month.strftime('%B %Y')}",
        completed,
        f"{month.strftime('%B %d, %Y')} through {end.strftime('%B %d, %Y')}",
    )


def strategy_groups(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in canonical_closed_rows(rows):
        groups.setdefault(strategy_label(row), []).append(row)
    if sum(len(group) for group in groups.values()) != len(canonical_closed_rows(rows)):
        raise RuntimeError("Strategy grouping lost one or more canonical trades")
    return groups


def strategy_summary_pages(rows: list[dict[str, str]], title: str = "Strategy Breakdown") -> list[str]:
    groups = strategy_groups(rows)
    ranked = sorted(
        groups.items(),
        key=lambda item: (
            spy_scanner.result_metrics(item[1])["total_pnl"],
            spy_scanner.result_metrics(item[1])["expectancy_pct"],
        ),
        reverse=True,
    )
    if not ranked:
        return [
            f"## {title}\n**Canonical ledger coverage:** **0/0** closed trades.\n### Results\nNo completed trades yet."
        ]
    pages = []
    grouped_pages = list(chunks(ranked, 7))
    for page_number, page_groups in enumerate(grouped_pages, 1):
        lines = [
            f"## {title} · Page {page_number}/{len(grouped_pages)}",
            (
                f"**Canonical ledger coverage:** **{sum(len(group) for _, group in ranked)}/"
                f"{len(canonical_closed_rows(rows))}** closed trades across **{len(ranked)}** strategies."
            ),
            "### Ranked Strategies",
        ]
        for label, group in page_groups:
            metrics = spy_scanner.result_metrics(group)
            lines.append(
                f"**{label}** · {len(group)} trades · {int(metrics['wins'])}W/"
                f"{int(metrics['losses'])}L/{int(metrics['scratches'])}S · {metrics['win_rate']:.0f}% · "
                f"Net {spy_scanner.fmt_metric_money(metrics, 'total_pnl')} · "
                f"Exp {metrics['expectancy_pct']:+.0f}%"
            )
        pages.append("\n".join(lines)[:5900])
    return pages


def _require_upsert(
    discord: Any,
    logical_name: str,
    state: dict[str, Any],
    state_key: str,
    content: str,
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
            f"Discord did not acknowledge report card {logical_name}:{state_key}"
        )
    return str(message_id)


def _clear_report_state(state: dict[str, Any]) -> None:
    for container_name in ("messages", "message_hashes"):
        container = state.setdefault(container_name, {})
        for key in list(container):
            if str(key).startswith(STATE_PREFIXES):
                container.pop(key, None)


def _purge_report_channel(discord: Any, logical_name: str) -> int:
    channel_id = discord.channels.get(logical_name)
    if not channel_id:
        raise RuntimeError(
            f"Required report channel is missing: #{REPORT_ROUTES[logical_name]}"
        )
    markers = REPORT_MARKERS[logical_name]
    removed = 0
    before = ""
    while True:
        suffix = f"&before={before}" if before else ""
        page = discord._request("GET", f"/channels/{channel_id}/messages?limit=100{suffix}")
        if not isinstance(page, list) or not page:
            break
        for message in page:
            author = message.get("author") or {}
            if not (author.get("bot") or message.get("webhook_id")):
                continue
            text = spy_scanner.message_search_text(message)
            if any(marker in text for marker in markers):
                message_id = str(message.get("id") or "")
                if message_id:
                    discord._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
                    removed += 1
        before = str(page[-1].get("id") or "")
        if len(page) < 100 or not before:
            break
    return removed


def _sync_history(
    discord: Any,
    state: dict[str, Any],
    logical_name: str,
    key_prefix: str,
    title: str,
    completed: list[dict[str, str]],
) -> int:
    if not completed:
        return 0
    pages = list(chunks(completed, PAGE_SIZE))
    for page_number, page_rows in enumerate(pages, 1):
        page_title = f"{title} · Page {page_number}/{len(pages)}"
        _require_upsert(
            discord,
            logical_name,
            state,
            f"report-v3:{key_prefix}:history:{page_number}",
            history_page(title, page_rows, page_number, len(pages)),
            page_title,
        )
    return len(pages)


def _period_dates(rows: list[dict[str, str]]) -> list[date]:
    return sorted({effective_closed_at(row).date() for row in canonical_closed_rows(rows)})


def _period_weeks(rows: list[dict[str, str]]) -> list[date]:
    return sorted({week_start(value) for value in _period_dates(rows)})


def _period_months(rows: list[dict[str, str]]) -> list[date]:
    months = sorted({month_start(value) for value in _period_dates(rows)})
    return months[-MAX_MONTHS:]


def _sync_daily(discord: Any, state: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, int]:
    completed = canonical_closed_rows(rows)
    dates = _period_dates(rows)
    _require_upsert(
        discord,
        "daily_recap",
        state,
        "report-v3:daily:index",
        "\n".join(
            [
                "## Daily Performance Index",
                f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades.",
                f"**Recorded trading days:** **{len(dates)}**",
                "Each date below contains a summary and every closed trade in paginated history.",
            ]
        ),
        "Daily Performance Index",
    )
    pages = 0
    for report_date in dates:
        day_rows = rows_closed_on(rows, report_date)
        token = f"Daily Report · {report_date.strftime('%m/%d/%y')}"
        _require_upsert(
            discord,
            "daily_recap",
            state,
            f"report-v3:daily:{report_date.isoformat()}:summary",
            format_daily_recap(rows, report_date, market_open=False),
            token,
        )
        pages += _sync_history(
            discord,
            state,
            "daily_recap",
            f"daily:{report_date.isoformat()}",
            f"Daily Trade History · {report_date.strftime('%m/%d/%y')}",
            day_rows,
        )
    return {"periods": len(dates), "history_pages": pages, "trades": len(completed)}


def _sync_weekly(discord: Any, state: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, int]:
    completed = canonical_closed_rows(rows)
    weeks = _period_weeks(rows)
    _require_upsert(
        discord,
        "weekly_report",
        state,
        "report-v3:weekly:index",
        "\n".join(
            [
                "## Weekly Performance Index",
                f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades.",
                f"**Recorded weeks:** **{len(weeks)}**",
                "Each week below contains a weekly-format summary and every closed trade.",
            ]
        ),
        "Weekly Performance Index",
    )
    pages = 0
    for monday in weeks:
        friday = monday + timedelta(days=4)
        week_rows = rows_closed_between(rows, monday, friday)
        _require_upsert(
            discord,
            "weekly_report",
            state,
            f"report-v3:weekly:{monday.isoformat()}:summary",
            format_weekly_report(rows, friday, final=True),
            f"Weekly Report · {monday.strftime('%m/%d')}",
        )
        pages += _sync_history(
            discord,
            state,
            "weekly_report",
            f"weekly:{monday.isoformat()}",
            f"Weekly Trade History · {monday.strftime('%m/%d/%y')}",
            week_rows,
        )
    return {"periods": len(weeks), "history_pages": pages, "trades": len(completed)}


def _sync_strategy_results_variant(
    discord: Any, state: dict[str, Any], rows: list[dict[str, str]], *, play_type: str, logical_name: str, label: str
) -> dict[str, int]:
    """Results report for ONE of the two independently-tracked SPY 0DTE
    variants - rows are filtered to play_type before anything else runs, so
    this variant's ranking, pagination, and trade history can never include
    the other variant's trades."""
    filtered = [row for row in rows if row.get("play_type") == play_type]
    completed = canonical_closed_rows(filtered)
    title = f"{label} Results"
    summaries = strategy_summary_pages(filtered, title=title)
    for page_number, content in enumerate(summaries, 1):
        _require_upsert(
            discord,
            logical_name,
            state,
            f"report-v3:{logical_name}:summary:{page_number}",
            content,
            f"{title} · Page {page_number}/{len(summaries)}",
        )
    pages = 0
    groups = strategy_groups(filtered)
    for group_label in sorted(groups):
        safe_key = hashlib.sha256(group_label.encode("utf-8")).hexdigest()[:10]
        pages += _sync_history(
            discord,
            state,
            logical_name,
            f"{logical_name}:{safe_key}",
            f"{label} Trade History · {group_label}",
            groups[group_label],
        )
    return {
        "periods": len(groups),
        "history_pages": pages,
        "summary_pages": len(summaries),
        "trades": len(completed),
    }


def _sync_monthly_performance_variant(
    discord: Any, state: dict[str, Any], rows: list[dict[str, str]], *, play_type: str, logical_name: str, label: str
) -> dict[str, int]:
    """Monthly performance report for ONE SPY 0DTE variant - same isolation
    as _sync_strategy_results_variant: filtered to play_type first, so the
    two variants' monthly numbers can never bleed into each other."""
    filtered = [row for row in rows if row.get("play_type") == play_type]
    completed = canonical_closed_rows(filtered)
    months = _period_months(filtered)
    _require_upsert(
        discord,
        logical_name,
        state,
        f"report-v3:{logical_name}:index",
        "\n".join(
            [
                f"## {label} Monthly Performance Index",
                f"**Canonical ledger coverage:** **{len(completed)}/{len(completed)}** closed trades.",
                f"**Recorded months shown:** **{len(months)}**",
                "Monthly summaries use the weekly layout and include every trade in history pages.",
            ]
        ),
        f"{label} Monthly Performance Index",
    )
    pages = 0
    covered = 0
    for month in months:
        month_rows = rows_closed_between(filtered, month, month_end(month))
        covered += len(month_rows)
        _require_upsert(
            discord,
            logical_name,
            state,
            f"report-v3:{logical_name}:{month.isoformat()}:summary",
            format_monthly_report(filtered, month).replace(
                "📊 Monthly Performance", f"📊 {label} Monthly Performance"
            ),
            f"{label} Monthly Performance · {month.strftime('%B %Y')}",
        )
        pages += _sync_history(
            discord,
            state,
            logical_name,
            f"{logical_name}:monthly:{month.isoformat()}",
            f"{label} Monthly Trade History · {month.strftime('%B %Y')}",
            month_rows,
        )
    if covered != len(completed):
        raise RuntimeError(
            f"{label} monthly reporting omitted canonical trades: {covered}/{len(completed)}"
        )
    return {"periods": len(months), "history_pages": pages, "trades": covered}


def update_performance_pages(
    discord: Any, state: dict[str, Any], rows: list[dict[str, str]]
) -> None:
    """The complete rebuild is owned by sync_reports to prevent split routing."""
    return None


def sync_reports(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_open: bool,
) -> None:
    if not discord.ready:
        return
    signature = ledger_signature(rows)
    rebuild = (
        state.get("performance_reconciliation_version") != REPORT_VERSION
        or state.get("performance_ledger_signature") != signature
    )
    removed = 0
    if rebuild:
        for logical_name in REPORT_ROUTES:
            removed += _purge_report_channel(discord, logical_name)
        _clear_report_state(state)

    daily = _sync_daily(discord, state, rows)
    weekly = _sync_weekly(discord, state, rows)

    expected = len(canonical_closed_rows(rows))
    for name, result in (("daily", daily), ("weekly", weekly)):
        if result["trades"] != expected:
            raise RuntimeError(
                f"{name} reporting coverage failed: {result['trades']}/{expected}"
            )

    variant_results: dict[str, dict[str, int]] = {}
    strategy_groups_total = 0
    monthly_reports_total = 0
    history_pages_total = daily["history_pages"] + weekly["history_pages"]
    for play_type, performance_logical, results_logical, label in SPY_0DTE_VARIANTS:
        variant_expected = len([row for row in canonical_closed_rows(rows) if row.get("play_type") == play_type])
        results = _sync_strategy_results_variant(
            discord, state, rows, play_type=play_type, logical_name=results_logical, label=label
        )
        monthly = _sync_monthly_performance_variant(
            discord, state, rows, play_type=play_type, logical_name=performance_logical, label=label
        )
        for name, result in ((f"{label} results", results), (f"{label} monthly", monthly)):
            if result["trades"] != variant_expected:
                raise RuntimeError(
                    f"{name} reporting coverage failed: {result['trades']}/{variant_expected}"
                )
        variant_results[play_type] = {"results": results, "monthly": monthly}
        strategy_groups_total += results["periods"]
        monthly_reports_total += monthly["periods"]
        history_pages_total += results["history_pages"] + monthly["history_pages"]

    state.update(
        {
            "performance_reconciliation_version": REPORT_VERSION,
            "performance_ledger_signature": signature,
            "performance_reconciliation_closed_trades": expected,
            "performance_reconciliation_daily_reports": daily["periods"],
            "performance_reconciliation_weekly_reports": weekly["periods"],
            "performance_reconciliation_strategy_groups": strategy_groups_total,
            "performance_reconciliation_monthly_reports": monthly_reports_total,
            "performance_reconciliation_history_pages": history_pages_total,
            "performance_reconciliation_removed_misplaced_cards": removed,
            "performance_reconciliation_checked_at": timestamp.isoformat(),
        }
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    spy_scanner.CHANNEL_NAMES.update(REPORT_ROUTES)
    for logical_name in REPORT_ROUTES:
        if logical_name not in spy_scanner.AUTOMATED_CHANNEL_KEYS:
            spy_scanner.AUTOMATED_CHANNEL_KEYS.append(logical_name)
    spy_scanner.rows_closed_on = rows_closed_on
    spy_scanner.rows_closed_between = rows_closed_between
    spy_scanner.format_daily_recap = format_daily_recap
    spy_scanner.format_weekly_report = format_weekly_report
    spy_scanner.update_performance_pages = update_performance_pages
    spy_scanner.sync_reports = sync_reports
    _INSTALLED = True


def validate_reconciliation() -> dict[str, int]:
    rows: list[dict[str, str]] = []
    monday = datetime(2026, 7, 27, 14, 30, tzinfo=spy_scanner.MARKET_TZ)
    strategies = (
        ("REGULAR", "call"),
        ("REGULAR", "put"),
        ("SWING", "call"),
        ("SWING", "put"),
        ("SPREAD", "call"),
    )
    for index in range(100):
        closed_at = monday + timedelta(days=index % 5, minutes=index)
        play_type, side = strategies[index % len(strategies)]
        row = spy_scanner.blank_row()
        row.update(
            {
                "trade_id": f"TEST-{index + 1:03d}",
                "timestamp": (closed_at - timedelta(hours=1)).isoformat(),
                "closed_at": closed_at.isoformat() if index != 49 else "",
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": "WIN" if index % 3 else "LOSS",
                "play_type": play_type,
                "call_or_put": side,
                "ticker": "F",
                "strike": "12" if play_type != "SPREAD" else "12/11",
                "entry_price": "0.50",
                "exit_price": "0.60" if index % 3 else "0.40",
                "realized_pl_dollars": "10" if index % 3 else "-10",
                "pct_gain_loss": "20" if index % 3 else "-20",
            }
        )
        rows.append(row)

    completed = canonical_closed_rows(rows)
    daily = sum(len(rows_closed_on(rows, monday.date() + timedelta(days=i))) for i in range(5))
    weekly = len(rows_closed_between(rows, monday.date(), monday.date() + timedelta(days=4)))
    grouped = sum(len(group) for group in strategy_groups(rows).values())
    monthly = len(rows_closed_between(rows, date(2026, 7, 1), date(2026, 7, 31)))
    if {len(completed), daily, weekly, grouped, monthly} != {100}:
        raise RuntimeError(
            f"Synthetic 100-trade reconciliation failed: {len(completed)}, {daily}, {weekly}, {grouped}, {monthly}"
        )
    return {
        "canonical_closed": len(completed),
        "daily_covered": daily,
        "weekly_covered": weekly,
        "strategy_covered": grouped,
        "monthly_covered": monthly,
    }


if __name__ == "__main__":
    install()
    print(json.dumps(validate_reconciliation(), indent=2))
