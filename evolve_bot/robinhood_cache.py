"""Local cache for real historical data pulled from Robinhood MCP tools.

Robinhood's option/equity historicals are only reachable through MCP tool
calls made interactively in a Claude session - there is no HTTP endpoint a
standalone script (like this bot's own scheduled runs) can hit on its own.
So the pull happens in two steps, not one: a Claude session fetches real
data and writes it here via `save_equity_bars`/`save_option_bars`, then
`backtest.py` (running as a plain script, no MCP involved) reads only from
this cache via `load_equity_bars`/`load_option_bars`. Nothing in this
module makes a network call.

Bars are normalized from Robinhood's raw field names (open_price/
high_price/low_price/close_price/begins_at, volume as an int) into the
plain open/high/low/close/timestamp/volume shape spy_scanner's own
functions already expect (see spy_opening_range_signal, which reads
bar.get("high")/bar.get("low")/bar.get("close")) - so a cached day can be
fed straight into that live code with no adapter at the call site.

Bars flagged interpolated=true carry no real information (Robinhood's own
guidance: gap-fill placeholders, not real prints) and are dropped here so
nothing downstream has to remember to check the flag itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "robinhood_cache"
EQUITY_DIR = CACHE_DIR / "equity"
OPTION_DIR = CACHE_DIR / "option"


def _normalize_bar(raw: dict[str, Any]) -> dict[str, Any] | None:
    if raw.get("interpolated"):
        return None
    try:
        return {
            "timestamp": raw["begins_at"],
            "open": float(raw["open_price"]),
            "high": float(raw["high_price"]),
            "low": float(raw["low_price"]),
            "close": float(raw["close_price"]),
            "volume": int(raw.get("volume") or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None


def normalize_bars(raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop interpolated/malformed bars, normalize field names. Order is
    preserved (Robinhood already returns bars in chronological order)."""
    normalized = []
    for raw in raw_bars:
        bar = _normalize_bar(raw)
        if bar is not None:
            normalized.append(bar)
    return normalized


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(path)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_equity_bars(symbol: str, trading_day: str, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """trading_day is an ISO date string, e.g. '2026-07-06'."""
    normalized = normalize_bars(raw_bars)
    _write_json(EQUITY_DIR / f"{symbol}_{trading_day}.json", normalized)
    return normalized


def load_equity_bars(symbol: str, trading_day: str) -> list[dict[str, Any]]:
    return _read_json(EQUITY_DIR / f"{symbol}_{trading_day}.json") or []


def cached_equity_days(symbol: str) -> list[str]:
    if not EQUITY_DIR.exists():
        return []
    prefix = f"{symbol}_"
    days = [
        p.stem[len(prefix):]
        for p in EQUITY_DIR.glob(f"{prefix}*.json")
    ]
    return sorted(days)


def save_option_bars(option_symbol: str, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = normalize_bars(raw_bars)
    _write_json(OPTION_DIR / f"{option_symbol}.json", normalized)
    return normalized


def load_option_bars(option_symbol: str) -> list[dict[str, Any]] | None:
    """None means 'never cached' (caller should fall back to synthetic
    pricing); [] means 'cached but Robinhood had nothing real' (also a
    fallback case) - kept distinct so a caller can tell a genuine cache
    miss apart from a confirmed-empty real-data lookup if that distinction
    ever matters."""
    return _read_json(OPTION_DIR / f"{option_symbol}.json")


def has_cached_option(option_symbol: str) -> bool:
    return (OPTION_DIR / f"{option_symbol}.json").exists()
