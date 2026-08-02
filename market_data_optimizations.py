"""Remove duplicate market-data work without reducing scan coverage.

The existing scanner asks for different daily-history lengths from several
callers and fetches each ticker's underlying quote separately. This runtime
canonicalizes daily history into one reusable request and prefetches all active
underlying quotes in one batched call before the sequential scanner begins.
The scanner algorithms, option-chain coverage, and candidate count are unchanged.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATUS_PATH = ROOT / "state" / "market-data-optimizations.json"
CANONICAL_DAILY_DAYS = max(
    420, int(os.environ.get("CANONICAL_DAILY_HISTORY_DAYS", "420"))
)
QUOTE_CACHE_SECONDS = max(
    0.25, float(os.environ.get("QUOTE_CACHE_SECONDS", "2"))
)
_LOCK = threading.RLock()
_QUOTES: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
_INSTALLED = False


def _write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, STATUS_PATH)


def install(ford_scan: Any, multi_ticker_scan: Any | None = None) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_get_quotes = ford_scan.get_quotes
    original_multi_main = (
        multi_ticker_scan.main if multi_ticker_scan is not None else None
    )

    def get_quotes(
        symbols: list[str], include_greeks: bool = True
    ) -> dict[str, dict[str, Any]]:
        unique = list(
            dict.fromkeys(
                str(symbol or "").strip().upper()
                for symbol in symbols
                if str(symbol or "").strip()
            )
        )
        current = time.monotonic()
        output: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        with _LOCK:
            for symbol in unique:
                key = (symbol, bool(include_greeks))
                cached = _QUOTES.get(key)
                if cached and current - cached[0] <= QUOTE_CACHE_SECONDS:
                    output[symbol] = dict(cached[1])
                else:
                    missing.append(symbol)
        if missing:
            fetched = original_get_quotes(
                missing, include_greeks=include_greeks
            )
            stamped = time.monotonic()
            with _LOCK:
                for symbol, quote in fetched.items():
                    normalized = str(symbol).upper()
                    value = dict(quote)
                    _QUOTES[(normalized, bool(include_greeks))] = (
                        stamped,
                        value,
                    )
                    if include_greeks:
                        _QUOTES[(normalized, False)] = (stamped, value)
                    output[normalized] = value
        return {symbol: output[symbol] for symbol in unique if symbol in output}

    def get_daily_history(
        symbol: str, days: int = 90
    ) -> list[dict[str, Any]]:
        end = ford_scan.now_ct().date()
        canonical_start = end - timedelta(days=CANONICAL_DAILY_DAYS)
        data = ford_scan.tradier_get(
            "/markets/history",
            {
                "symbol": str(symbol).upper(),
                "interval": "daily",
                "start": canonical_start.isoformat(),
                "end": end.isoformat(),
            },
        )
        history = data.get("history") or {}
        values = history.get("day") if isinstance(history, dict) else None
        if not values:
            return []
        rows = [values] if isinstance(values, dict) else list(values)
        requested_days = max(1, int(days))
        cutoff = end - timedelta(days=requested_days)
        filtered = [
            row
            for row in rows
            if str(row.get("date") or "") >= cutoff.isoformat()
        ]
        return filtered or rows

    ford_scan.get_quotes = get_quotes
    ford_scan.get_quote = lambda symbol: get_quotes(
        [symbol], include_greeks=False
    ).get(str(symbol).upper())
    ford_scan.get_daily_history = get_daily_history

    if original_multi_main is not None:

        def multi_main(tickers: list[str] | None = None) -> int:
            selected = tickers or multi_ticker_scan.configured_active_tickers()
            if selected:
                get_quotes(selected, include_greeks=False)
            result = original_multi_main(selected)
            _write_status(
                {
                    "updated_at": ford_scan.now_ct().isoformat(
                        timespec="seconds"
                    ),
                    "batch": selected,
                    "underlying_quotes_prefetched": len(selected),
                    "canonical_daily_history_days": CANONICAL_DAILY_DAYS,
                    "quote_cache_seconds": QUOTE_CACHE_SECONDS,
                    "result": result,
                }
            )
            return result

        multi_ticker_scan.main = multi_main

    ford_scan.MARKET_DATA_OPTIMIZATION_RUNTIME = (
        "batched-quotes-canonical-history-v1"
    )
    _write_status(
        {
            "installed_at": ford_scan.now_ct().isoformat(timespec="seconds"),
            "canonical_daily_history_days": CANONICAL_DAILY_DAYS,
            "quote_cache_seconds": QUOTE_CACHE_SECONDS,
            "status": "INSTALLED",
        }
    )
    _INSTALLED = True


__all__ = ["install"]
