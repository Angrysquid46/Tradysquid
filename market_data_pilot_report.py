"""Summarize a market_data_pilot.py JSONL run: latency, bytes, rows,
success rate, and projected daily/monthly volume at the tested cadence.

Standalone reporting tool for Phase 5 Stage A - reads the pilot's output,
makes no network calls of its own.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

RTH_SESSION_SECONDS = 6.5 * 3600
TRADING_DAYS_PER_MONTH = 21


def load_records(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))
    return ordered[index]


def summarize_label(
    records: list[dict[str, Any]], label: str, interval_seconds: int
) -> dict[str, Any]:
    subset = [r for r in records if r["label"] == label]
    if not subset:
        return {"label": label, "calls": 0}
    successes = [r for r in subset if r["success"]]
    latencies = [r["latency_ms"] for r in successes]
    byte_sizes = [r["bytes"] for r in successes]
    row_counts = [r["rows"] for r in successes]
    calls_per_rth_day = RTH_SESSION_SECONDS / interval_seconds
    mean_bytes = statistics.mean(byte_sizes) if byte_sizes else 0.0
    return {
        "label": label,
        "calls": len(subset),
        "successes": len(successes),
        "success_rate": round(len(successes) / len(subset), 4),
        "latency_ms_mean": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_p95": (
            round(_percentile(latencies, 0.95), 1) if len(latencies) >= 2 else
            (round(latencies[0], 1) if latencies else None)
        ),
        "bytes_mean": round(mean_bytes, 1),
        "rows_mean": round(statistics.mean(row_counts), 1) if row_counts else None,
        "projected_calls_per_rth_day": round(calls_per_rth_day, 1),
        "projected_bytes_per_rth_day": round(mean_bytes * calls_per_rth_day, 1),
        "projected_mb_per_month": round(
            mean_bytes * calls_per_rth_day * TRADING_DAYS_PER_MONTH / (1024 * 1024), 2
        ),
    }


def summarize(records: list[dict[str, Any]], interval_seconds: int) -> dict[str, Any]:
    labels = sorted({r["label"] for r in records})
    return {
        "total_records": len(records),
        "interval_seconds": interval_seconds,
        "by_label": [summarize_label(records, label, interval_seconds) for label in labels],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL file produced by market_data_pilot.py")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="The cadence the pilot was run at, for daily/monthly projections",
    )
    args = parser.parse_args()
    records = load_records(Path(args.path))
    print(json.dumps(summarize(records, args.interval_seconds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
