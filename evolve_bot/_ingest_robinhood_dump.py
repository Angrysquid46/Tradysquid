"""One-off ingestion helper, run manually after an MCP get_equity_historicals
/ get_option_historicals call whose result was too large to return inline
and got saved to a tool-results JSON file instead. Not test_*.py (not
collected by pytest) and not part of the automated pipeline - MCP data
only ever arrives through an interactive session, so this is a deliberate
manual step, re-run each time there's a new dump to fold in (see
robinhood_cache.py's module docstring for why this can't be automatic).

Usage: python _ingest_robinhood_dump.py equity <path-to-dump.json> <symbol>
       python _ingest_robinhood_dump.py option <path-to-dump.json> <option_symbol>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

import robinhood_cache


def ingest_equity_dump(path: str, symbol: str) -> dict[str, int]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    results = payload["data"]["results"]
    bars_by_day: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        for bar in result["bars"]:
            # begins_at is UTC; regular-session bars (13:30-20:00 UTC)
            # never cross a UTC midnight boundary, so the UTC date portion
            # is always the correct trading day.
            day = bar["begins_at"][:10]
            bars_by_day[day].append(bar)
    counts = {}
    for day, bars in bars_by_day.items():
        saved = robinhood_cache.save_equity_bars(symbol, day, bars)
        counts[day] = len(saved)
    return counts


def ingest_option_dump(path: str, option_symbol: str) -> int:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    results = payload["data"]["results"]
    bars = results[0]["bars"] if results else []
    saved = robinhood_cache.save_option_bars(option_symbol, bars)
    return len(saved)


if __name__ == "__main__":
    kind, path, symbol = sys.argv[1], sys.argv[2], sys.argv[3]
    if kind == "equity":
        result = ingest_equity_dump(path, symbol)
        print(json.dumps(result, indent=2))
    elif kind == "option":
        count = ingest_option_dump(path, symbol)
        print(f"saved {count} real bars for {symbol}")
    else:
        raise SystemExit(f"unknown kind: {kind!r} (expected 'equity' or 'option')")
