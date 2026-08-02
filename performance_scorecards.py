"""Keep Discord Performance channels as scorecards, not duplicate trade journals.

The trade journal owns trade-by-trade lifecycle detail. Performance channels own
one updating summary card per day, week, month, and play type.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

import ford_scan
import performance_reconciliation as base


REPORT_VERSION = "performance-scorecards-v4"
_INSTALLED = False

PLAY_TYPE_ORDER = (
    "REGULAR CALL",
    "REGULAR PUT",
    "SWING CALL",
    "SWING PUT",
    "SPREAD CALL",
    "SPREAD PUT",
)

STATE_PREFIXES = (
    "report-v3:",
    "report-v4:",
    "daily-recap:",
    "weekly-report:",
    "performance-stats",
    "strategy-breakdown",
)


def normalize_play_type(row: dict[str, str]) -> str:
    """Map historical naming variants into stable scorecard play types."""
    raw_play = str(row.get("play_type") or "PLAY").upper()
    raw_side = str(row.get("call_or_put") or "").upper()
    combined = f"{raw_play} {raw_side}"

    if "PUT" in combined:
        side = "PUT"
    elif "CALL" in combined:
        side = "CALL"
    else:
        side = raw_side or "OTHER"

    if "REGULAR" in raw_play:
        family = "REGULAR"
    elif "SWING" in raw_play:
        family = "SWING"
    elif "SPREAD" in raw_play or "CREDIT" in raw_play:
        family = "SPREAD"
    else:
        family = raw_play.strip() or "PLAY"

    return f"{family} {side}".strip()


def canonical_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return base.canonical_closed_rows(rows)


def period_dates(rows: list[dict[str, str]], today: date) -> list[date]:
    dates = {base.effective_closed_at(row).date() for row in canonical_rows(rows)}
    if today.weekday() < 5:
        dates.add(today)
    return sorted(dates)


def period_weeks(rows: list[dict[str, str]], today: date) -> list[date]:
    weeks = {
        base.week_start(base.effective_closed_at(row).date())
        for row in canonical_rows(rows)
    }
    weeks.add(base.week_start(today))
    return sorted(weeks)


def period_months(rows: list[dict[str, str]], today: date) -> list[date]:
    months = {
        base.month_start(base.effective_closed_at(row).date())
        for row in canonical_rows(rows)
    }
    months.add(base.month_start(today))
    return sorted(months)[-24:]


def play_type_groups(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {label: [] for label in PLAY_TYPE_ORDER}
    for row in canonical_rows(rows):
        groups.setdefault(normalize_play_type(row), []).append(row)
    if sum(len(group) for group in groups.values()) != len(canonical_rows(rows)):
        raise RuntimeError("Play-type scorecards lost one or more canonical trades")
    return groups


def play_type_scorecard(label: str, completed: list[dict[str, str]]) -> str:
    metrics = ford_scan.result_metrics(completed)
    lines = [
        f"## 🧭 {label}",
        f"**Closed trades:** **{len(completed)}**",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        "### Money",
        (
            f"Won **{ford_scan.fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{ford_scan.fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{ford_scan.fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%** · "
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%**"
        ),
    ]
    if not completed:
        lines.append("No closed trades recorded for this play type yet.")
    return "\n".join(lines)[:5900]


def safe_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return cleaned or hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


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
            f"Discord did not acknowledge scorecard {logical_name}:{state_key}"
        )
    return str(message_id)


def _clear_report_state(state: dict[str, Any]) -> None:
    for container_name in ("messages", "message_hashes"):
        container = state.setdefault(container_name, {})
        for key in list(container):
            if str(key).startswith(STATE_PREFIXES):
                container.pop(key, None)


def _purge_old_report_cards(discord: Any) -> int:
    removed = 0
    for logical_name in base.REPORT_ROUTES:
        removed += base._purge_report_channel(discord, logical_name)
    return removed


def _sync_daily(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_open: bool,
) -> int:
    dates = period_dates(rows, timestamp.date())
    for report_date in dates:
        _require_upsert(
            discord,
            "daily_recap",
            state,
            f"report-v4:daily:{report_date.isoformat()}",
            base.format_daily_recap(
                rows,
                report_date,
                market_open=market_open and report_date == timestamp.date(),
            ),
            f"Daily Report · {report_date.strftime('%m/%d/%y')}",
        )
    return len(dates)


def _sync_weekly(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    today: date,
) -> int:
    weeks = period_weeks(rows, today)
    current_monday = base.week_start(today)
    for monday in weeks:
        friday = monday + timedelta(days=4)
        report_end = min(today, friday) if monday == current_monday else friday
        final = monday < current_monday or today >= friday
        _require_upsert(
            discord,
            "weekly_report",
            state,
            f"report-v4:weekly:{monday.isoformat()}",
            base.format_weekly_report(rows, report_end, final=final),
            f"Weekly Report · {monday.strftime('%m/%d')}",
        )
    return len(weeks)


def _sync_monthly(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    today: date,
) -> int:
    months = period_months(rows, today)
    for month in months:
        _require_upsert(
            discord,
            "performance_stats",
            state,
            f"report-v4:monthly:{month.isoformat()}",
            base.format_monthly_report(rows, month),
            f"Monthly Performance · {month.strftime('%B %Y')}",
        )
    return len(months)


def _sync_strategies(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
) -> int:
    groups = play_type_groups(rows)
    ordered = list(PLAY_TYPE_ORDER) + sorted(
        label for label in groups if label not in PLAY_TYPE_ORDER
    )
    for label in ordered:
        _require_upsert(
            discord,
            "strategy_breakdown",
            state,
            f"report-v4:strategy:{safe_key(label)}",
            play_type_scorecard(label, groups[label]),
            f"{label} Scorecard",
        )
    return len(ordered)


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

    signature = base.ledger_signature(rows)
    version_changed = state.get("performance_reconciliation_version") != REPORT_VERSION
    removed = 0
    if version_changed:
        removed = _purge_old_report_cards(discord)
        _clear_report_state(state)

    daily_count = _sync_daily(
        discord, state, rows, timestamp, market_open=market_open
    )
    weekly_count = _sync_weekly(discord, state, rows, timestamp.date())
    strategy_count = _sync_strategies(discord, state, rows)
    monthly_count = _sync_monthly(discord, state, rows, timestamp.date())

    state.update(
        {
            "performance_reconciliation_version": REPORT_VERSION,
            "performance_ledger_signature": signature,
            "performance_reconciliation_closed_trades": len(canonical_rows(rows)),
            "performance_reconciliation_daily_reports": daily_count,
            "performance_reconciliation_weekly_reports": weekly_count,
            "performance_reconciliation_strategy_groups": strategy_count,
            "performance_reconciliation_monthly_reports": monthly_count,
            "performance_reconciliation_history_pages": 0,
            "performance_reconciliation_scorecard_only": True,
            "performance_reconciliation_removed_misplaced_cards": removed,
            "performance_reconciliation_checked_at": timestamp.isoformat(),
        }
    )


def validate_reconciliation() -> dict[str, int]:
    rows: list[dict[str, str]] = []
    monday = datetime(2026, 7, 27, 14, 30, tzinfo=ford_scan.MARKET_TZ)
    strategies = (
        ("REGULAR", "call"),
        ("REGULAR", "put"),
        ("SWING", "call"),
        ("SWING", "put"),
        ("SPREAD", "call"),
        ("SPREAD", "put"),
    )
    for index in range(100):
        closed_at = monday + timedelta(days=index % 5, minutes=index)
        play_type, side = strategies[index % len(strategies)]
        outcome = "WIN" if index % 3 else "LOSS"
        row = ford_scan.blank_row()
        row.update(
            {
                "trade_id": f"TEST-{index + 1:03d}",
                "timestamp": (closed_at - timedelta(hours=1)).isoformat(),
                "closed_at": closed_at.isoformat() if index != 49 else "",
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": outcome,
                "play_type": play_type,
                "call_or_put": side,
                "ticker": "F",
                "strike": "12",
                "entry_price": "0.50",
                "exit_price": "0.60" if outcome == "WIN" else "0.40",
                "realized_pl_dollars": "10" if outcome == "WIN" else "-10",
                "pct_gain_loss": "20" if outcome == "WIN" else "-20",
            }
        )
        rows.append(row)

    groups = play_type_groups(rows)
    if len(canonical_rows(rows)) != 100:
        raise RuntimeError("Synthetic scorecard ledger did not retain 100 trades")
    if any(label not in groups for label in PLAY_TYPE_ORDER):
        raise RuntimeError("Synthetic scorecard validation omitted a play type")
    if sum(len(group) for group in groups.values()) != 100:
        raise RuntimeError("Synthetic play-type scorecards lost trades")
    return {
        "closed_trades": 100,
        "daily_scorecards": len(period_dates(rows, date(2026, 8, 1))),
        "weekly_scorecards": len(period_weeks(rows, date(2026, 8, 1))),
        "monthly_scorecards": len(period_months(rows, date(2026, 8, 1))),
        "strategy_scorecards": len(groups),
        "history_pages": 0,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    base.install()
    base.REPORT_VERSION = REPORT_VERSION
    base.sync_reports = sync_reports
    base.validate_reconciliation = validate_reconciliation
    ford_scan.sync_reports = sync_reports
    _INSTALLED = True


if __name__ == "__main__":
    install()
    print(json.dumps(validate_reconciliation(), indent=2))
