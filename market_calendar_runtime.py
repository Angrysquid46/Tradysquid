"""Correct Tradier calendar times before market-hours upgrade reviews.

Tradier documents calendar start/end values in Eastern time. Tradysquid's market
clock is America/Chicago, so provider times must be localized in New York and
then converted instead of being interpreted as Central.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import diagnostic_upgrade_system as diagnostics

EASTERN = ZoneInfo("America/New_York")
_INSTALLED = False


def official_market_session(
    moment: datetime | None = None,
    *,
    calendar_payload: dict[str, Any] | None = None,
):
    local_moment = (moment or datetime.now(diagnostics.ford_scan.MARKET_TZ)).astimezone(
        diagnostics.ford_scan.MARKET_TZ
    )
    eastern_moment = local_moment.astimezone(EASTERN)
    payload = calendar_payload
    if payload is None:
        try:
            payload = diagnostics.ford_scan.tradier_get(
                "/markets/calendar",
                {"month": eastern_moment.month, "year": eastern_moment.year},
            )
        except Exception:
            payload = None
    if payload:
        for item in diagnostics._calendar_days(payload):
            if str(item.get("date") or "") != eastern_moment.date().isoformat():
                continue
            status = str(item.get("status") or "").casefold()
            if status not in {"open", "early-close", "early_close"}:
                return None
            open_data = item.get("open") if isinstance(item.get("open"), dict) else {}
            start_clock = diagnostics._parse_clock(
                open_data.get("start") or item.get("open_time"),
                diagnostics.clock_time(9, 30),
            )
            end_clock = diagnostics._parse_clock(
                open_data.get("end") or item.get("close_time"),
                diagnostics.clock_time(16, 0),
            )
            start_eastern = datetime.combine(
                eastern_moment.date(), start_clock, tzinfo=EASTERN
            )
            end_eastern = datetime.combine(
                eastern_moment.date(), end_clock, tzinfo=EASTERN
            )
            return (
                start_eastern.astimezone(diagnostics.ford_scan.MARKET_TZ),
                end_eastern.astimezone(diagnostics.ford_scan.MARKET_TZ),
            )
    fallback = diagnostics.fallback_market_session(local_moment.date())
    if not fallback:
        return None
    return (
        datetime.combine(
            local_moment.date(), fallback[0], tzinfo=diagnostics.ford_scan.MARKET_TZ
        ),
        datetime.combine(
            local_moment.date(), fallback[1], tzinfo=diagnostics.ford_scan.MARKET_TZ
        ),
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    diagnostics.official_market_session = official_market_session
    _INSTALLED = True
