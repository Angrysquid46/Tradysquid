"""Generic Tradier market-data plumbing - the "verified factual historical
market data" / "working market-data plumbing" survivor category Master Spec
Section 2 names explicitly, extracted out of spy_scanner.py before its
Phase 3 purge.

This is quote/chain/history retrieval and generic technical-context scoring
(SMA/RSI/volume/VWAP-based "regime" read), used by local_information_engine.py
and, through it, discord_command_bot.py's surviving /quote, /trend, /chain,
/setup, /option commands. It contains no strategy entry/exit logic, no
trade-log access, and no Discord posting - purely read-only market data.

Every function body below is verbatim from spy_scanner.py (extracted by
exact line range, not retyped), to avoid introducing a transcription bug in
numeric/financial logic during the purge.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

REPO_ROOT = Path(__file__).resolve().parent
STATE_DIR = REPO_ROOT / "state"
REPORT_STATE_PATH = STATE_DIR / "discord-report-state.json"

TICKER = "SPY"
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "").strip()
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()

MARKET_TZ = ZoneInfo("America/Chicago")
TRADIER_TIMESALES_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)

MIN_OPEN_INTEREST = int(os.environ.get("MIN_OPEN_INTEREST", "500"))
MIN_OPTION_VOLUME = int(os.environ.get("MIN_OPTION_VOLUME", "200"))
MAX_BID_ASK_PCT = float(os.environ.get("MAX_BID_ASK_PCT", "0.25"))
STRIKE_BAND_PCT = float(os.environ.get("STRIKE_BAND_PCT", "0.12"))
MAX_EXTENSION_ABOVE_SMA20_PCT = float(os.environ.get("MAX_EXTENSION_ABOVE_SMA20_PCT", "0.05"))

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Tradysquids-TradeBot/1.0"})


def now_ct() -> datetime:
    return datetime.now(MARKET_TZ)

def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def split_chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]

def market_is_open_now() -> tuple[bool, datetime]:
    now = now_ct()
    if now.weekday() >= 5:
        return False, now
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_time <= now <= close_time, now

class TradierError(RuntimeError):
    pass

def tradier_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TRADIER_TOKEN:
        raise TradierError("TRADIER_TOKEN is not configured")
    try:
        response = SESSION.get(
            f"{TRADIER_BASE_URL}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise TradierError(f"Tradier request failed: {exc}") from exc
    if not response.ok:
        body = response.text[:500].replace(TRADIER_TOKEN, "[REDACTED]")
        raise TradierError(f"Tradier HTTP {response.status_code} for {path}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise TradierError(f"Tradier returned invalid JSON for {path}") from exc

def get_quotes(symbols: list[str], include_greeks: bool = True) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(symbol for symbol in symbols if symbol))
    quote_map: dict[str, dict[str, Any]] = {}
    for chunk in split_chunks(unique, 50):
        data = tradier_get(
            "/markets/quotes",
            {"symbols": ",".join(chunk), "greeks": str(include_greeks).lower()},
        )
        quotes = data.get("quotes", {}).get("quote")
        if not quotes:
            continue
        if isinstance(quotes, dict):
            quotes = [quotes]
        for quote in quotes:
            symbol = quote.get("symbol")
            if symbol:
                quote_map[symbol] = quote
    return quote_map


def get_quote(symbol: str) -> dict[str, Any] | None:
    return get_quotes([symbol], include_greeks=False).get(symbol)

def get_expirations(symbol: str) -> list[str]:
    data = tradier_get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    values = data.get("expirations", {}).get("date")
    if values is None:
        return []
    return [values] if isinstance(values, str) else list(values)

def get_chain(symbol: str, expiration: str) -> list[dict[str, Any]]:
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )
    values = data.get("options", {}).get("option")
    if values is None:
        return []
    return [values] if isinstance(values, dict) else list(values)

def get_daily_history(symbol: str, days: int = 90) -> list[dict[str, Any]]:
    end = now_ct().date()
    start = end - timedelta(days=days)
    data = tradier_get(
        "/markets/history",
        {
            "symbol": symbol,
            "interval": "daily",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )
    history = data.get("history") or {}
    values = history.get("day") if isinstance(history, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)

def _et_window_str(day: date, hour: int, minute: int) -> str:
    """Convert a CT wall-clock moment on `day` to the ET-labeled string
    Tradier's timesales endpoint actually expects (see TRADIER_TIMESALES_TZ
    above)."""
    ct_dt = datetime.combine(day, dt_time(hour, minute), tzinfo=MARKET_TZ)
    et_dt = ct_dt.astimezone(TRADIER_TIMESALES_TZ)
    return et_dt.strftime("%Y-%m-%d %H:%M")

def get_intraday_history(
    symbol: str,
    interval: str = "5min",
) -> list[dict[str, Any]]:
    """Return today's intraday bars when Tradier supplies time-and-sales data."""
    today = now_ct().date()
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": _et_window_str(today, 8, 30),
            "end": _et_window_str(today, 15, 0),
            "session_filter": "open",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)

def get_recent_intraday_history(
    symbol: str, interval: str, calendar_days: int
) -> list[dict[str, Any]]:
    """Multi-day intraday bars, not just today - get_intraday_history is
    hardcoded to a single day (today)."""
    end = now_ct().date()
    start = end - timedelta(days=calendar_days)
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": _et_window_str(start, 8, 30),
            "end": _et_window_str(end, 15, 0),
            "session_filter": "open",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)

def simple_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period

def exponential_moving_average_series(values: list[float], period: int) -> list[float | None]:
    """Generic EMA - one value per input point, None until enough data has
    accumulated to seed the average."""
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    series: list[float | None] = [None] * (period - 1)
    seed = sum(values[:period]) / period
    series.append(seed)
    previous = seed
    for value in values[period:]:
        current = (value - previous) * multiplier + previous
        series.append(current)
        previous = current
    return series

def exponential_moving_average(values: list[float], period: int) -> float | None:
    series = exponential_moving_average_series(values, period)
    return series[-1] if series else None

def average_true_range(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> float | None:
    if len(closes) < period + 1 or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    return sum(ranges[-period:]) / period if len(ranges) >= period else None

def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5

def bollinger_bands(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[float | None, float | None, float | None]:
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    middle = sum(window) / period
    deviation = standard_deviation(window)
    if deviation is None:
        return None, middle, None
    return middle + num_std * deviation, middle, middle - num_std * deviation

def relative_strength_index(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [current - previous for previous, current in zip(values[-period - 1:-1], values[-period:])]
    gains = sum(max(change, 0) for change in changes) / period
    losses = sum(max(-change, 0) for change in changes) / period
    if losses == 0:
        return 100.0
    return 100 - (100 / (1 + gains / losses))

def directional_market_context(
    history: list[dict[str, Any]],
    spot_price: float,
    intraday: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    volumes = [value for day in history if (value := as_float(day.get("volume"))) is not None]
    sma20 = simple_moving_average(closes, 20)
    sma50 = simple_moving_average(closes, 50)
    rsi14 = relative_strength_index(closes)
    average_volume20 = simple_moving_average(volumes, 20)
    latest_volume = volumes[-1] if volumes else None
    volume_ratio = (
        latest_volume / average_volume20
        if latest_volume is not None and average_volume20 and average_volume20 > 0
        else None
    )
    intraday = intraday or []
    intraday_closes = [
        value
        for bar in intraday
        if (value := as_float(bar.get("close") or bar.get("price"))) is not None
    ]
    intraday_volumes = [
        as_float(bar.get("volume"), 0.0) or 0.0
        for bar in intraday
        if as_float(bar.get("close") or bar.get("price")) is not None
    ]
    intraday_open = intraday_closes[0] if intraday_closes else None
    intraday_change_pct = (
        ((spot_price / intraday_open) - 1) * 100
        if intraday_open and intraday_open > 0
        else None
    )
    intraday_vwap = None
    if intraday_closes and sum(intraday_volumes) > 0:
        intraday_vwap = sum(
            price * volume
            for price, volume in zip(intraday_closes, intraday_volumes)
        ) / sum(intraday_volumes)
    intraday_rsi = relative_strength_index(intraday_closes, 9)
    fast_average = simple_moving_average(intraday_closes, 5)
    slow_average = simple_moving_average(intraday_closes, 20)
    slope_pct = (
        ((intraday_closes[-1] / intraday_closes[-4]) - 1) * 100
        if len(intraday_closes) >= 4 and intraday_closes[-4] > 0
        else None
    )

    reasons: list[str] = []
    failures: list[str] = []
    regime = "NO TRADE"
    if sma20 is None or sma50 is None or rsi14 is None:
        failures.append("insufficient daily history")
    else:
        extension = (spot_price / sma20) - 1
        score = 0
        spot_vs_sma20 = (spot_price / sma20) - 1
        sma_trend_pct = (sma20 / sma50) - 1
        if spot_vs_sma20 >= 0.0025:
            score += 1
            reasons.append("price is above its 20-day average")
        elif spot_vs_sma20 <= -0.0025:
            score -= 1
            reasons.append("price is below its 20-day average")
        if sma_trend_pct >= 0.002:
            score += 1
            reasons.append("20-day trend is above the 50-day trend")
        elif sma_trend_pct <= -0.002:
            score -= 1
            reasons.append("20-day trend is below the 50-day trend")
        if rsi14 >= 55:
            score += 1
        elif rsi14 <= 45:
            score -= 1

        if intraday_change_pct is not None:
            if intraday_change_pct >= 0.35:
                score += 2
                reasons.append(f"intraday move is bullish ({intraday_change_pct:+.1f}%)")
            elif intraday_change_pct <= -0.35:
                score -= 2
                reasons.append(f"intraday move is bearish ({intraday_change_pct:+.1f}%)")
        if intraday_vwap:
            vwap_distance_pct = ((spot_price / intraday_vwap) - 1) * 100
            if vwap_distance_pct >= 0.15:
                score += 1
                reasons.append("price is holding above intraday VWAP")
            elif vwap_distance_pct <= -0.15:
                score -= 1
                reasons.append("price is holding below intraday VWAP")
        if fast_average is not None and slow_average is not None:
            momentum_gap_pct = ((fast_average / slow_average) - 1) * 100
            if momentum_gap_pct >= 0.10:
                score += 1
                reasons.append("5-bar momentum is above the 20-bar trend")
            elif momentum_gap_pct <= -0.10:
                score -= 1
                reasons.append("5-bar momentum is below the 20-bar trend")
        if intraday_rsi is not None:
            if intraday_rsi >= 60:
                score += 1
            elif intraday_rsi <= 40:
                score -= 1
        if slope_pct is not None:
            if slope_pct >= 0.35:
                score += 1
                reasons.append("recent 15-minute price slope is rising")
            elif slope_pct <= -0.35:
                score -= 1
                reasons.append("recent 15-minute price slope is falling")

        if score >= 2:
            regime = "BULLISH / CONTROLLED"
        elif score <= -2:
            regime = "BEARISH / CONTROLLED"
        elif intraday_closes:
            regime = "NEUTRAL / RANGE"
            reasons.append("combined daily and intraday evidence is balanced")
        else:
            failures.append(
                "intraday confirmation is unavailable and daily evidence is mixed"
            )
        if abs(extension) > MAX_EXTENSION_ABOVE_SMA20_PCT:
            reasons.append(
                f"price is extended {extension * 100:+.1f}% from the 20-day average; "
                "contract risk filters still apply"
            )
    return {
        "qualified": not failures,
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "intraday_change_pct": intraday_change_pct,
        "intraday_vwap": intraday_vwap,
        "intraday_rsi": intraday_rsi,
        "intraday_fast_average": fast_average,
        "intraday_slow_average": slow_average,
        "intraday_slope_pct": slope_pct,
        "evidence_score": score if sma20 is not None and sma50 is not None and rsi14 is not None else 0,
        "regime": regime,
        "reason": "; ".join(reasons) if reasons else "No controlled directional setup",
        "failures": failures,
    }

def open_interest_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(option.get(key))
        if value is not None and value > 0:
            return int(value)
    greeks = option.get("greeks") or {}
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(greeks.get(key))
        if value is not None and value > 0:
            return int(value)
    return 0


def option_volume_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    return int(as_float(option.get("volume"), 0.0) or 0)

def greek(option: dict[str, Any], key: str) -> float | None:
    return as_float((option.get("greeks") or {}).get(key))

def fmt_money(value: float | None) -> str:
    """Display one-contract and aggregate dollar values as whole dollars."""
    if value is None:
        return "—"
    rounded = int(round(value))
    return f"-${abs(rounded):,}" if rounded < 0 else f"${rounded:,}"

def read_report_state() -> dict[str, Any]:
    default = {
        "messages": {},
        "message_hashes": {},
        "daily_report_date": "",
        "weekly_report_key": "",
        "guide_version": "",
        "routed_closed_trade_ids": [],
    }
    if not REPORT_STATE_PATH.exists():
        return default
    try:
        loaded = json.loads(REPORT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    if not isinstance(loaded, dict):
        return default
    default.update(loaded)
    if not isinstance(default.get("messages"), dict):
        default["messages"] = {}
    if not isinstance(default.get("routed_closed_trade_ids"), list):
        default["routed_closed_trade_ids"] = []
    return default

def write_report_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )

def iv_value(option: dict[str, Any] | None) -> float | None:
    if not option:
        return None
    greeks = option.get("greeks") or {}
    for source in (greeks, option):
        for key in (
            "mid_iv",
            "smv_vol",
            "bid_iv",
            "ask_iv",
            "iv",
            "implied_volatility",
            "impliedVolatility",
        ):
            value = as_float(source.get(key))
            if value is not None and value > 0:
                return value
    return None
