"""Automatic daily equity-bar caching from Tradier, so the backtest/
retrain pipeline gets fed every real trading day without a manual
Robinhood MCP session - owner: "I'd like it automated so I don't have
to ask for it to do its job... so we don't miss anything."

Robinhood's own historicals are MCP-only (see robinhood_cache.py's
module docstring - no HTTP endpoint a standalone script can hit).
spy_scanner already calls Tradier's /markets/timesales endpoint live and
unattended, every 3 minutes, for the real trading loop; the identical
endpoint works fine for backfilling a recent past day too - Tradier
just doesn't retain intraday data much past ~29 days back (see
backtest.py's own docstring on why the Robinhood cache exists at all),
which is why this only ever looks a short distance back, not the bot's
whole history. A day already cached (by this or an earlier manual
Robinhood pull) is left untouched - a manual Robinhood pull stays
authoritative for real option-priced days someone chooses to run by
hand; this only fills in what would otherwise be missing.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import robinhood_cache

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

RECENT_TRADING_DAYS_TO_CHECK = 5


def _tradier_bar_to_robinhood_shape(bar: dict[str, Any]) -> dict[str, Any]:
    """Tradier's own 'time' field is an unlabeled ET wall-clock string;
    its 'timestamp' field is a real UTC unix epoch, which is what gets
    used here to build an unambiguous UTC 'begins_at' matching the exact
    shape robinhood_cache.normalize_bars already expects."""
    ts = datetime.fromtimestamp(bar["timestamp"], tz=timezone.utc)
    return {
        "begins_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open_price": bar["open"],
        "high_price": bar["high"],
        "low_price": bar["low"],
        "close_price": bar["close"],
        "volume": bar.get("volume", 0),
    }


def _fetch_tradier_intraday_bars_for_day(symbol: str, trading_day: date) -> list[dict[str, Any]]:
    """Generalizes spy_scanner.get_intraday_history (hardcoded to "today
    only") to an arbitrary recent past day, using the identical request
    shape against the same /markets/timesales endpoint."""
    data = s.tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": "1min",
            "start": s._et_window_str(trading_day, 8, 30),
            "end": s._et_window_str(trading_day, 15, 0),
            "session_filter": "open",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def recent_real_trading_days(symbol: str, n: int = RECENT_TRADING_DAYS_TO_CHECK) -> list[str]:
    """Real market calendar days (weekends/holidays already excluded),
    oldest first - sourced from Tradier's own daily history so this
    never has to hardcode a market calendar of its own."""
    daily = s.get_daily_history(symbol, days=n + 10)
    days = [row["date"] for row in daily if row.get("date")]
    return days[-n:]


def fill_missing_recent_days(symbol: str = "SPY") -> dict[str, Any]:
    """The real automation step: whatever of the last few real trading
    days isn't in robinhood_cache yet gets pulled from Tradier and saved
    in the same cache, same format, so backtest.py/refresh_pipeline.py
    never have to know or care which source a given cached day came
    from. Safe to call daily (or more often) - an already-cached day is
    always left alone."""
    cached = set(robinhood_cache.cached_equity_days(symbol))
    missing = [day for day in recent_real_trading_days(symbol) if day not in cached]
    filled = []
    for day_str in missing:
        trading_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        raw_bars = _fetch_tradier_intraday_bars_for_day(symbol, trading_day)
        if not raw_bars:
            continue
        converted = [_tradier_bar_to_robinhood_shape(bar) for bar in raw_bars]
        robinhood_cache.save_equity_bars(symbol, day_str, converted)
        filled.append(day_str)
    return {"checked": missing, "filled": filled}
