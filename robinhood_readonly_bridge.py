"""Ingest symbols returned by the authenticated Robinhood MCP.

This bridge accepts discovery symbols only. It has no account, order, transfer,
buy, sell, or trade parameters and cannot call Robinhood itself.
"""

from __future__ import annotations

import argparse
from datetime import datetime

import dynamic_universe


def ingest_symbols(symbols: list[str], source: str = "robinhood_mcp") -> int:
    normalized = list(dict.fromkeys(
        dynamic_universe.normalize_symbol(symbol) for symbol in symbols
    ))
    return dynamic_universe.import_robinhood_snapshot({
        "source": source,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbols": [
            {
                "symbol": symbol,
                "score": 60,
                "options_available": True,
            }
            for symbol in normalized
        ],
    })


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import read-only Robinhood MCP discovery symbols."
    )
    parser.add_argument("symbols", nargs="+", help="Ticker symbols only")
    args = parser.parse_args()
    count = ingest_symbols(args.symbols)
    print(f"Imported {count} read-only Robinhood discovery symbol(s).")
    print("No account action, order, transfer, buy, sell, or trade was requested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
