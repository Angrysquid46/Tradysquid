"""The evolve bot's own trade log - a completely separate CSV from
spy-plays-log.csv, by design (never merged into the shared ledger, never
scored against the other strategies). Schema is deliberately richer than
the main system's log: every signal value that mattered at entry is
captured, specifically so a later weekly review (or the ML pipeline) can
read this file directly and understand what happened without guessing.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

HEADER = [
    "trade_id",
    "run_number",
    "timestamp",
    "option_symbol",
    "call_or_put",
    "strike",
    "expiration",
    "entry_price",
    "contracts",
    "position_size_dollars",
    "balance_before",
    # Entry signal context - everything the bankroll/decision logic saw at
    # entry, so a later review or the ML pipeline never has to guess what
    # informed a trade.
    "spot_price_at_entry",
    "delta_at_entry",
    "theta_at_entry",
    "iv_at_entry",
    "open_interest_at_entry",
    "volume_at_entry",
    "market_regime",
    "market_condition_at_entry",
    "opening_range_high",
    "opening_range_low",
    "vix_at_entry",
    "sentiment_at_entry",
    "put_call_ratio_at_entry",
    "model_score_at_entry",
    "thesis",
    # Outcome
    "outcome",
    "exit_price",
    "closed_at",
    "last_signal",
    "pl_dollars",
    "pl_pct",
    "balance_after",
    "max_favorable_pct",
    "max_adverse_pct",
    "last_evaluated_at",
]


def blank_row() -> dict[str, str]:
    return {field: "" for field in HEADER}


def read_log(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_log(path: Path, rows: list[dict[str, str]]) -> None:
    """Atomic write, matching spy_scanner.write_log's pattern - a crash
    mid-write must never leave a truncated or corrupt trade log behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        temp_path.replace(path)
    except BaseException:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def open_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("outcome") == "OPEN"]


def closed_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("outcome") in ("WIN", "LOSS", "SCRATCH")]


def next_trade_id(rows: list[dict[str, str]], run_number: int, timestamp) -> str:
    date_str = timestamp.strftime("%Y%m%d")
    prefix = f"EVOLVE-{date_str}-"
    existing = [row.get("trade_id", "") for row in rows if row.get("trade_id", "").startswith(prefix)]
    sequence = len(existing) + 1
    return f"{prefix}{sequence:03d}"
