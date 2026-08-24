"""Phase 5 Stage A: measure real Tradier request cost for SPY quotes and
0DTE chain snapshots at a candidate cadence.

Master Spec Section 9 (permanent factual market-data collection) requires
a measured pilot capture - request cost, bytes/row - before committing to
any collection cadence or storage estimate. This script produces that
measurement. It is a standalone tool, not part of the live scheduler: it
makes no permanent storage decisions and writes nothing outside
data/pilot/.

Byte size is an approximation: len(json.dumps(parsed_result).encode()) of
the already-parsed response, not the raw wire payload (whitespace/key-
ordering differ), chosen to avoid touching market_data.tradier_get()'s
signature. Close enough to size a storage estimate; not exact billing.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import market_data

ROOT = Path(__file__).resolve().parent
PILOT_DIR = ROOT / "data" / "pilot"
DEFAULT_INTERVAL_SECONDS = 60


def _measure(label: str, callback: Callable[[], Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = callback()
    except Exception as exc:
        elapsed_ms = (time.monotonic() - started) * 1000
        return {
            "label": label,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "success": False,
            "latency_ms": round(elapsed_ms, 1),
            "bytes": 0,
            "rows": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    elapsed_ms = (time.monotonic() - started) * 1000
    payload_bytes = len(json.dumps(result, default=str).encode("utf-8"))
    rows = len(result) if isinstance(result, (list, dict)) else 1
    return {
        "label": label,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "success": True,
        "latency_ms": round(elapsed_ms, 1),
        "bytes": payload_bytes,
        "rows": rows,
        "error": "",
    }


def find_zero_dte_expiration(symbol: str) -> str | None:
    today = market_data.now_ct().date().isoformat()
    try:
        expirations = market_data.get_expirations(symbol)
    except Exception:
        return None
    return today if today in expirations else None


def run_cycle(symbol: str, expiration: str | None) -> list[dict[str, Any]]:
    measurements = [
        _measure(
            "get_quotes",
            lambda: market_data.get_quotes([symbol], include_greeks=False),
        )
    ]
    if expiration:
        measurements.append(
            _measure(
                "get_chain",
                lambda: market_data.get_chain(symbol, expiration),
            )
        )
    return measurements


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def _print_record(record: dict[str, Any]) -> None:
    status = "OK" if record["success"] else "FAIL"
    line = (
        f"[{record['at']}] {record['label']:10s} {status:4s} "
        f"{record['latency_ms']:7.1f}ms {record['bytes']:6d}B {record['rows']:3d} rows"
    )
    if record["error"]:
        line += f" ({record['error']})"
    print(line)


def run(
    symbol: str,
    interval_seconds: int,
    cycles: int | None,
    output_path: Path,
) -> None:
    expiration = find_zero_dte_expiration(symbol)
    if expiration is None:
        print(
            f"warning: no same-day expiration found for {symbol}; "
            "chain measurements will be skipped this run"
        )
    completed = 0
    while cycles is None or completed < cycles:
        cycle_started = time.monotonic()
        records = run_cycle(symbol, expiration)
        append_jsonl(output_path, records)
        for record in records:
            _print_record(record)
        completed += 1
        if cycles is not None and completed >= cycles:
            break
        elapsed = time.monotonic() - cycle_started
        time.sleep(max(0.0, interval_seconds - elapsed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=market_data.TICKER)
    parser.add_argument(
        "--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Stop after this many cycles instead of running until killed",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSONL output path (default: data/pilot/market-data-pilot-<date>.jsonl)",
    )
    args = parser.parse_args()
    output_path = (
        Path(args.output)
        if args.output
        else PILOT_DIR / f"market-data-pilot-{datetime.now().date().isoformat()}.jsonl"
    )
    run(args.symbol, args.interval_seconds, args.cycles, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
