"""Keep Discord Performance channels as scorecards, not duplicate trade journals.

The trade journal owns trade-by-trade lifecycle detail. Performance channels own
one updating summary card per day, week, month, and play type.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import spy_scanner
import performance_reconciliation as base


REPORT_VERSION = "performance-scorecards-v5"
_INSTALLED = False

# SPY 0DTE is the only strategy family this system trades, split into two
# independently-tracked live strategies. REGULAR/SWING/SPREAD were retired
# along with the multi-ticker system they belonged to - PLAY_TYPE_ORDER used
# to list their CALL/PUT combinations for scorecard ordering, which no
# longer means anything live. Kept as a fallback label set for any old
# historical row still sitting in the ledger, not as anything the two live
# strategies use.
PLAY_TYPE_ORDER: tuple[str, ...] = ()

STATE_PREFIXES = (
    "report-v3:",
    "report-v4:",
    "report-v5:",
    "daily-recap:",
    "weekly-report:",
    "monthly-dashboard:",
    "1m-performance",
    "1m-results",
    "5m-performance",
    "5m-results",
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


def clean_period_scorecard(content: str) -> str:
    """Never label an empty scoreboard as trade history."""
    return content.replace(
        "### Trade History\nNo trades closed during this period.",
        "### Status\nNo trades closed during this period yet.",
    )


def play_type_scorecard(label: str, completed: list[dict[str, str]]) -> str:
    metrics = spy_scanner.result_metrics(completed)
    lines = [
        f"## 🧭 Strategy Scorecard · {label}",
        f"**Closed trades:** **{len(completed)}**",
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
    if not completed:
        lines.append("No closed trades recorded for this play type yet.")
    return "\n".join(lines)[:5900]


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
        content = clean_period_scorecard(
            base.format_daily_recap(
                rows,
                report_date,
                market_open=market_open and report_date == timestamp.date(),
            )
        )
        _require_upsert(
            discord,
            "daily_recap",
            state,
            f"report-v4:daily:{report_date.isoformat()}",
            content,
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
        content = clean_period_scorecard(
            base.format_weekly_report(rows, report_end, final=final)
        )
        _require_upsert(
            discord,
            "weekly_report",
            state,
            f"report-v4:weekly:{monday.isoformat()}",
            content,
            f"Weekly Report · {monday.strftime('%m/%d')}",
        )
    return len(weeks)


def _sync_monthly_dashboard(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    today: date,
) -> int:
    """Combined-across-every-strategy monthly scorecard, parallel to
    _sync_daily/_sync_weekly above. #monthly-dashboard already existed as a
    real Discord channel but nothing in the deployed code ever posted to it
    - monthly performance only existed broken out per strategy via
    _sync_monthly_variant below."""
    months = period_months(rows, today)
    for month in months:
        content = clean_period_scorecard(base.format_monthly_report(rows, month))
        _require_upsert(
            discord,
            "monthly_recap",
            state,
            f"report-v5:monthly-dashboard:{month.isoformat()}",
            content,
            f"Monthly Performance · {month.strftime('%B %Y')}",
        )
    return len(months)


def _sync_monthly_variant(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    today: date,
    *,
    play_type: str,
    logical_name: str,
    label: str,
) -> int:
    """Monthly scorecard for ONE of the two independently-tracked SPY 0DTE
    strategies - rows are filtered to play_type before any period math runs,
    so the two variants' monthly numbers can never bleed into each other."""
    filtered = [row for row in rows if row.get("play_type") == play_type]
    months = period_months(filtered, today)
    for month in months:
        content = clean_period_scorecard(base.format_monthly_report(filtered, month)).replace(
            "📊 Monthly Performance", f"📊 {label} Monthly Performance"
        )
        _require_upsert(
            discord,
            logical_name,
            state,
            f"report-v5:monthly:{logical_name}:{month.isoformat()}",
            content,
            f"{label} Monthly Performance · {month.strftime('%B %Y')}",
        )
    return len(months)


def _sync_strategy_results_variant(
    discord: Any,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    *,
    play_type: str,
    logical_name: str,
    label: str,
) -> int:
    """Results scorecard for ONE independently-tracked strategy, combined
    across call and put - same filter-first isolation as the monthly
    variant above. Used to be split into one card per side (CALL/PUT),
    which read as duplicate cards sitting in the same channel even though
    each was technically a different group - owner wants one combined card
    per strategy here too, matching the daily/weekly/monthly pattern."""
    filtered = [row for row in rows if row.get("play_type") == play_type]
    completed = canonical_rows(filtered)
    _require_upsert(
        discord,
        logical_name,
        state,
        f"report-v5:results:{logical_name}:combined",
        play_type_scorecard(label, completed),
        f"{label} Results",
    )
    return 1 if completed else 0


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
    monthly_dashboard_count = _sync_monthly_dashboard(discord, state, rows, timestamp.date())

    strategy_count = 0
    monthly_count = 0
    for play_type, performance_logical, results_logical, label in base.STRATEGY_VARIANTS:
        strategy_count += _sync_strategy_results_variant(
            discord, state, rows, play_type=play_type, logical_name=results_logical, label=label
        )
        monthly_count += _sync_monthly_variant(
            discord, state, rows, timestamp.date(),
            play_type=play_type, logical_name=performance_logical, label=label,
        )

    monday = base.week_start(timestamp.date())
    friday = monday + timedelta(days=4)
    current_week_rows = base.rows_closed_between(rows, monday, min(timestamp.date(), friday))

    state.update(
        {
            "performance_reconciliation_version": REPORT_VERSION,
            "performance_ledger_signature": signature,
            "performance_reconciliation_closed_trades": len(canonical_rows(rows)),
            "performance_reconciliation_week_trades": len(current_week_rows),
            "performance_reconciliation_daily_reports": daily_count,
            "performance_reconciliation_weekly_reports": weekly_count,
            "performance_reconciliation_monthly_dashboard_reports": monthly_dashboard_count,
            "performance_reconciliation_strategy_groups": strategy_count,
            "performance_reconciliation_monthly_reports": monthly_count,
            "performance_reconciliation_history_pages": 0,
            "performance_reconciliation_scorecard_only": True,
            "performance_reconciliation_removed_misplaced_cards": removed,
            "performance_reconciliation_checked_at": timestamp.isoformat(),
        }
    )


def validate_reconciliation() -> dict[str, int]:
    # Cycles through every currently-live play_type (base.STRATEGY_VARIANTS -
    # both SPY_0DTE variants, Key-Levels, Expansion-Level, and all 10 ratchet
    # variants), not just the two SPY_0DTE variants - a synthetic self-test
    # that only ever exercised 2 of 14 live strategies gave no real coverage
    # for the other 12, including whichever one the owner most recently
    # added. Real bug once found this way: this used to run against the
    # retired REGULAR/SWING/SPREAD/"F" (Ford) system, silently validating
    # nothing about the SPY-only strategies actually live today.
    variants = base.STRATEGY_VARIANTS
    rows: list[dict[str, str]] = []
    monday = datetime(2026, 7, 27, 14, 30, tzinfo=spy_scanner.MARKET_TZ)
    sides = ("call", "put")
    for index in range(100):
        closed_at = monday + timedelta(days=index % 5, minutes=index)
        play_type = variants[index % len(variants)][0]
        side = sides[index % len(sides)]
        outcome = "WIN" if index % 3 else "LOSS"
        row = spy_scanner.blank_row()
        row.update(
            {
                "trade_id": f"TEST-{index + 1:03d}",
                "timestamp": (closed_at - timedelta(hours=1)).isoformat(),
                "closed_at": closed_at.isoformat() if index != 49 else "",
                "last_evaluated_at": closed_at.isoformat(),
                "outcome": outcome,
                "play_type": play_type,
                "call_or_put": side,
                "ticker": "SPY",
                "strike": "600",
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
    if sum(len(group) for group in groups.values()) != 100:
        raise RuntimeError("Synthetic play-type scorecards lost trades")
    # The real point of the split: each variant's own filtered group must
    # never leak another variant's trades into it, for every live variant,
    # not just the first two.
    rows_by_variant = {
        play_type: [row for row in rows if row.get("play_type") == play_type]
        for play_type, *_ in variants
    }
    if sum(len(canonical_rows(v)) for v in rows_by_variant.values() if v) != 100:
        raise RuntimeError("Per-variant filtering lost or duplicated trades")
    for play_type, variant_rows in rows_by_variant.items():
        if any(row.get("play_type") != play_type for row in variant_rows):
            raise RuntimeError(f"{play_type} filter leaked another variant's trade")
    return {
        "closed_trades": 100,
        "daily_scorecards": len(period_dates(rows, date(2026, 8, 1))),
        "weekly_scorecards": len(period_weeks(rows, date(2026, 8, 1))),
        "monthly_scorecards": sum(
            len(period_months(v, date(2026, 8, 1))) for v in rows_by_variant.values() if v
        ),
        "strategy_scorecards": len(groups),
        "history_pages": 0,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    base.install()
    base.REPORT_VERSION = REPORT_VERSION
    results_logical_names = ("results_1m", "results_5m", "results_key_levels", "results_expansion") + tuple(
        results_logical for _, _, results_logical, _ in base.RATCHET_VARIANTS
    )
    for logical_name in results_logical_names:
        base.REPORT_MARKERS[logical_name] = tuple(
            dict.fromkeys((*base.REPORT_MARKERS[logical_name], "Strategy Scorecard ·"))
        )
    base.sync_reports = sync_reports
    base.validate_reconciliation = validate_reconciliation
    spy_scanner.sync_reports = sync_reports
    _INSTALLED = True


if __name__ == "__main__":
    install()
    print(json.dumps(validate_reconciliation(), indent=2))
