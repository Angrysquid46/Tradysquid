"""Phase 5 Stage B: append-only Parquet storage for permanent market-data
collection (Master Spec Section 9), plus a thin DuckDB query layer over it
(Section 9/10). Separate from market_data.py, which stays the pure Tradier
API wrapper - this module only knows how to write/read already-shaped rows.

Layout: data/market/<dataset>/<symbol>/<year>/<month>/<trading_day>/
<timestamp>.parquet - one immutable part-file per capture cycle, never
rewritten. A crash mid-day just means the next cycle writes the next
part-file; nothing needs repair. DuckDB queries a whole partition or the
entire dataset via glob, so there is no separate database file to keep in
sync with the Parquet tree.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" / "market"

CHAIN_DATASET = "chain"
QUOTES_DATASET = "quotes"
BARS_DATASET = "bars"

VERIFIED_REAL = "VERIFIED_REAL"
REAL_WITH_LIMITATIONS = "REAL_WITH_LIMITATIONS"
REJECTED = "REJECTED"


def partition_dir(dataset: str, symbol: str, trading_day: date) -> Path:
    return (
        DATA_ROOT
        / dataset
        / symbol
        / f"{trading_day.year:04d}"
        / f"{trading_day.month:02d}"
        / trading_day.isoformat()
    )


def _part_file_name(captured_at: datetime) -> str:
    return captured_at.strftime("%Y%m%dT%H%M%S%f") + ".parquet"


def write_rows(
    dataset: str,
    symbol: str,
    trading_day: date,
    captured_at: datetime,
    rows: list[dict[str, Any]],
) -> Path | None:
    """Write one immutable part-file for this cycle. No-op (returns None)
    if there are no rows - an empty snapshot is not written as an empty
    file, it is simply absent, which the manifest's expected-vs-received
    counters already account for."""
    if not rows:
        return None
    directory = partition_dir(dataset, symbol, trading_day)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _part_file_name(captured_at)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)
    return path


def write_chain_snapshot(
    symbol: str, trading_day: date, captured_at: datetime, rows: list[dict[str, Any]]
) -> Path | None:
    return write_rows(CHAIN_DATASET, symbol, trading_day, captured_at, rows)


def write_quote(
    symbol: str, trading_day: date, captured_at: datetime, rows: list[dict[str, Any]]
) -> Path | None:
    return write_rows(QUOTES_DATASET, symbol, trading_day, captured_at, rows)


def write_bars(
    symbol: str, trading_day: date, captured_at: datetime, rows: list[dict[str, Any]]
) -> Path | None:
    return write_rows(BARS_DATASET, symbol, trading_day, captured_at, rows)


def dataset_glob(dataset: str, symbol: str, trading_day: date | None = None) -> str:
    if trading_day is not None:
        return str(partition_dir(dataset, symbol, trading_day) / "*.parquet")
    return str(DATA_ROOT / dataset / symbol / "**" / "*.parquet")


def query(sql: str, parameters: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    """Thin DuckDB wrapper - callers write read_parquet('<glob>') themselves
    via dataset_glob(), so this module never has to know the schema of
    what it's querying."""
    relation = duckdb.sql(sql, params=list(parameters) if parameters else None)
    return [dict(zip(relation.columns, row)) for row in relation.fetchall()]
