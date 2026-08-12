"""Walks real cached historical trading days through the real 0DTE
opening-range signal, prices the resulting candidates with real Robinhood
option data where cached (synthetic Black-Scholes fallback otherwise), and
replays the SAME real price path through several exit-parameter variants
to generate labeled training rows - the technique already proven on the
ratchet-floor backtest (many rule variants over one real dataset, not one
trade per real day).

Only reads from robinhood_cache.py's local cache for equity/option bars -
no MCP tool calls happen here, since this runs as a plain script and MCP
tools are only reachable interactively (see robinhood_cache.py's module
docstring). Tradier is still called live for daily history (IV estimation
lookback) and market-condition classification - those aren't gated by the
~29-day intraday limit that forced the Robinhood-cache approach in the
first place.

Output is intentionally a SEPARATE file from tradelog.py's live trade log
- these are simulated rows for model training, never real paper trades,
and must never be mixed with or scored against the live evolve bot's own
track record.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import backtest_exit
import chain_synthesis
import market_features
import robinhood_cache
import synthetic_pricing as pricing

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first
import engine  # noqa: E402 - for build_thesis reuse

CT = ZoneInfo("America/Chicago")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BACKTEST_TRADES_PATH = DATA_DIR / "backtest_trades.csv"

HEADER = [
    "trade_id", "trading_day", "variant_label", "call_or_put", "strike", "option_symbol",
    "entry_price", "price_source_at_entry", "delta_at_entry", "iv_at_entry", "spot_at_entry",
    "market_condition", "regime",
    # vix_at_entry/sentiment_at_entry are real historical values (FRED/
    # Finnhub, confirmed to cover this backtest's date range). put_call_ratio_at_entry
    # is deliberately left blank for every backtest row - it's computed
    # live from an already-fetched real chain (see market_features.py's
    # module docstring), and no historical chain exists for an expired
    # SPY expiration, so there is no honest way to backfill it here.
    "vix_at_entry", "sentiment_at_entry", "put_call_ratio_at_entry",
    "thesis",
    "stop_pct", "target_pct", "floor_pct", "floor_trigger_pct",
    "outcome", "exit_price", "last_signal", "pl_pct", "max_favorable_pct", "max_adverse_pct",
]

# Parameter variants swept per real trading day - centered on the live
# SPY_0DTE defaults (the middle row) with a spread of tighter/looser
# stops and targets around them, so the same real price path yields
# several labeled outcomes instead of just one.
DEFAULT_VARIANTS = [
    {"label": "tight_30_40", "stop_pct": 0.30, "target_pct": 0.40, "floor_pct": -10.0, "floor_trigger_pct": 20.0},
    {"label": "moderate_40_50", "stop_pct": 0.40, "target_pct": 0.50, "floor_pct": -12.0, "floor_trigger_pct": 25.0},
    {"label": "live_default_50_50", "stop_pct": 0.50, "target_pct": 0.50, "floor_pct": -15.0, "floor_trigger_pct": 30.0},
    {"label": "wide_target_50_75", "stop_pct": 0.50, "target_pct": 0.75, "floor_pct": -15.0, "floor_trigger_pct": 30.0},
    {"label": "loose_60_100", "stop_pct": 0.60, "target_pct": 1.00, "floor_pct": -20.0, "floor_trigger_pct": 40.0},
]


def _find_breakout_index(bars: list[dict[str, Any]]) -> int | None:
    """Mirrors spy_0dte_opening_range_signal's own breakout search so the
    backtest knows WHICH bar to treat as the entry moment - the live
    function only reports that a breakout happened, not where."""
    bars_needed = max(s.SPY_0DTE_OPENING_RANGE_MINUTES // 1, 1)
    if len(bars) <= bars_needed:
        return None
    opening_range = bars[:bars_needed]
    highs = [b["high"] for b in opening_range]
    lows = [b["low"] for b in opening_range]
    if not highs or not lows:
        return None
    range_high, range_low = max(highs), min(lows)
    for i in range(bars_needed, len(bars)):
        price = bars[i]["close"]
        if price > range_high or price < range_low:
            return i
    return None


def _bar_close_ct(timestamp_iso: str) -> datetime:
    return datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).astimezone(CT)


def _daily_bars_through(trading_day: str, lookback_days: int = 150) -> list[dict[str, Any]]:
    """Daily bars ending at trading_day (not today) - get_daily_history is
    hardcoded to fetch through today, so this fetches a wide-enough window
    and slices it down to what would have been known as of trading_day.
    Only daily bars are needed here (IV lookback, market-condition trend),
    and Tradier's daily retention (~20 years, confirmed live) comfortably
    covers any trading_day this backtest will ever be given.

    lookback_days is measured back from TODAY, not from trading_day, so an
    older trading_day eats into that budget before its own lookback even
    starts - e.g. a trading_day 35 days back only has (lookback_days - 35)
    calendar days of runway before it. 150 leaves comfortable room for
    MARKET_CONDITION_VOL_LOOKBACK_DAYS (20 trading days, needs ~28 calendar
    days) even for a trading_day at the far edge of the cached window; 60
    was too tight and silently produced an UNKNOWN market_condition for
    the earliest cached real days - caught by inspecting real backtest
    output, not by a test with small synthetic fixture data."""
    history = s.get_daily_history(s.TICKER, days=lookback_days)
    return [bar for bar in history if str(bar.get("date", "")) <= trading_day]


def _price_series(
    option_symbol: str,
    strike: float,
    call_or_put: str,
    iv: float,
    bars_after_entry: list[dict[str, Any]],
    close_time_ct: datetime,
) -> list[dict[str, Any]]:
    """One real-or-synthetic mark per bar from entry to end of day - shared
    across every variant so 'replay under different rules' means literally
    the same price path, not a re-derived one per variant."""
    real_bars = robinhood_cache.load_option_bars(option_symbol) or []
    real_by_ts = {bar["timestamp"]: bar["close"] for bar in real_bars}
    series = []
    for bar in bars_after_entry:
        ts = bar["timestamp"]
        bar_ct = _bar_close_ct(ts)
        minutes_remaining = max((close_time_ct - bar_ct).total_seconds() / 60, 0)
        if ts in real_by_ts:
            mark, source = real_by_ts[ts], "real"
        else:
            years = pricing.years_remaining_in_trading_day(bar_ct, close_time_ct)
            mark = pricing.black_scholes_price(bar["close"], strike, years, iv, call_or_put)
            source = "synthetic"
        series.append({"timestamp": ts, "minutes_remaining": minutes_remaining, "mark": mark, "source": source})
    return series


def _simulate_variant(entry_price: float, series: list[dict[str, Any]], variant: dict[str, Any]) -> dict[str, Any]:
    peak_pct = 0.0
    trough_pct = 0.0
    last_signal = "HOLD"
    exit_price = series[-1]["mark"] if series else entry_price
    for point in series:
        mark = point["mark"]
        pnl_pct = (mark - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
        peak_pct = max(peak_pct, pnl_pct)
        trough_pct = min(trough_pct, pnl_pct)
        signal, _ = backtest_exit.backtest_exit_signal(
            entry_price, mark, point["minutes_remaining"], peak_pct,
            variant["stop_pct"], variant["target_pct"], variant["floor_pct"], variant["floor_trigger_pct"],
        )
        if signal != "HOLD":
            last_signal = signal
            exit_price = mark
            break
    else:
        last_signal = "EOD CLOSE"  # ran out of cached bars before any signal fired
    pl_pct = (exit_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
    outcome = "WIN" if pl_pct > 0 else ("LOSS" if pl_pct < 0 else "SCRATCH")
    return {
        "outcome": outcome,
        "exit_price": round(exit_price, 4),
        "last_signal": last_signal,
        "pl_pct": round(pl_pct, 2),
        "max_favorable_pct": round(peak_pct, 2),
        "max_adverse_pct": round(trough_pct, 2),
    }


def run_backtest_for_day(trading_day: str, variants: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    variants = variants or DEFAULT_VARIANTS
    bars = robinhood_cache.load_equity_bars("SPY", trading_day)
    if not bars:
        return []
    signal = s.spy_0dte_opening_range_signal(bars, bar_minutes=1)
    if not signal.get("qualified"):
        return []
    breakout_index = _find_breakout_index(bars)
    if breakout_index is None:
        return []

    entry_bar = bars[breakout_index]
    spot_price = entry_bar["close"]
    entry_moment_ct = _bar_close_ct(entry_bar["timestamp"])
    close_time_ct = entry_moment_ct.replace(hour=s.MARKET_CLOSE[0], minute=s.MARKET_CLOSE[1], second=0, microsecond=0)
    call_or_put = "call" if signal["regime"] == "BULLISH / CONTROLLED" else "put"

    daily_bars = _daily_bars_through(trading_day)
    market_condition = s.classify_market_condition(daily_bars)["label"]
    iv = pricing.estimate_implied_volatility(daily_bars)
    years_to_expiry = pricing.years_remaining_in_trading_day(entry_moment_ct, close_time_ct)

    # Day-level features - computed once per trading_day, not per
    # candidate/variant, since VIX and sentiment don't vary within a day
    # at this granularity.
    vix_series = market_features.fetch_vix_series(
        (entry_moment_ct.date() - timedelta(days=10)).isoformat(), trading_day
    )
    vix = market_features.vix_on_or_before(trading_day, vix_series)
    sentiment = market_features.market_sentiment_for_date(trading_day)

    candidates = chain_synthesis.build_candidates(
        spot_price, call_or_put, trading_day, years_to_expiry, iv,
        moment_iso=entry_bar["timestamp"], play_type="SPY_EVOLVE_BACKTEST",
    )
    if not candidates:
        return []

    bars_after_entry = bars[breakout_index + 1:]
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        series = _price_series(
            candidate["option_symbol"], float(candidate["strike"]), call_or_put, iv,
            bars_after_entry, close_time_ct,
        )
        thesis = engine.build_thesis(candidate, signal, market_condition)
        for variant in variants:
            result = _simulate_variant(candidate["entry_price"], series, variant)
            rows.append(
                {
                    "trade_id": f"BT-{trading_day}-{candidate['option_symbol']}-{variant['label']}",
                    "trading_day": trading_day,
                    "variant_label": variant["label"],
                    "call_or_put": call_or_put,
                    "strike": candidate["strike"],
                    "option_symbol": candidate["option_symbol"],
                    "entry_price": candidate["entry_price"],
                    "price_source_at_entry": candidate["price_source"],
                    "delta_at_entry": candidate["delta"],
                    "iv_at_entry": candidate["iv"],
                    "spot_at_entry": candidate["spot_at_entry"],
                    "market_condition": market_condition,
                    "regime": signal["regime"],
                    "vix_at_entry": "" if vix is None else vix,
                    "sentiment_at_entry": "" if sentiment is None else sentiment,
                    "put_call_ratio_at_entry": "",
                    "thesis": thesis,
                    "stop_pct": variant["stop_pct"],
                    "target_pct": variant["target_pct"],
                    "floor_pct": variant["floor_pct"],
                    "floor_trigger_pct": variant["floor_trigger_pct"],
                    **result,
                }
            )
    return rows


def _read_existing_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8") as f:
        return {row["trade_id"]: row for row in csv.DictReader(f)}


def _write_rows(path: Path, rows_by_id: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for trade_id in sorted(rows_by_id):
            writer.writerow(rows_by_id[trade_id])
    tmp_path.replace(path)


def run_backtest(trading_days: list[str] | None = None) -> dict[str, Any]:
    """Idempotent: re-running upserts by trade_id rather than appending
    duplicates, so pulling more real days later and re-running is safe."""
    trading_days = trading_days if trading_days is not None else robinhood_cache.cached_equity_days("SPY")
    existing = _read_existing_rows(BACKTEST_TRADES_PATH)
    new_row_count = 0
    days_with_trades = 0
    for trading_day in trading_days:
        rows = run_backtest_for_day(trading_day)
        if rows:
            days_with_trades += 1
        for row in rows:
            existing[row["trade_id"]] = {key: str(row.get(key, "")) for key in HEADER}
            new_row_count += 1
    _write_rows(BACKTEST_TRADES_PATH, existing)
    return {
        "trading_days_scanned": len(trading_days),
        "trading_days_with_a_qualified_entry": days_with_trades,
        "rows_written_this_run": new_row_count,
        "total_rows_in_file": len(existing),
    }


if __name__ == "__main__":
    print(run_backtest())
