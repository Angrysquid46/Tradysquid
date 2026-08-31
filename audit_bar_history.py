"""Audit and optionally repair trusted SPY one-minute bar history.

Repairs are additive only: verified provider rows are deduplicated by provider
timestamp and legacy misplaced rows are copied into the correct trading-day
partition without deleting their original immutable part-file.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta

import market_data
import market_data_collector as collector


def weekdays(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def audit(start: date, end: date) -> list[dict]:
    return [
        collector.session_bar_completeness(market_data.TICKER, day)
        for day in weekdays(start, end)
    ]


def apply_repair(start: date, end: date) -> dict:
    now = market_data.now_ct()
    bars = market_data.get_intraday_history_range(
        market_data.TICKER, "1min", start, end
    )
    ingested = collector.ingest_bar_rows(market_data.TICKER, bars, now)
    repartitioned = collector.repair_bar_partitions(market_data.TICKER, now)
    return {
        "provider_rows": len(bars),
        "ingested": ingested,
        "repartitioned": repartitioned,
        "audit": audit(start, end),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must be on or after --start")
    result = apply_repair(args.start, args.end) if args.apply else audit(args.start, args.end)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
