"""Phase 5 step 1 - ingest EOD option chains into a compact table.

Source: the `spy_eod_YYYY.parquet` set (2010-2023, ~600 MB). Chosen over
the 8 GB JSON because it is the same kind of data - one end-of-day
snapshot per trading day - in a fraction of the space, and it overlaps
the 2008-2021 minute-bar history better than the JSON's 2014-2025.

Only a band is kept, not all 14 years of every strike: contracts within
`STRIKE_BAND_PCT` of spot and `MAX_DTE` days of expiry. That is
everything a 0DTE strategy can actually trade plus enough short-dated
context to read an implied-volatility level, and it turns ~6.9M rows into
something queryable in a couple of hundred MB.

**The limitation that shapes all of Phase 5:** every row here is quoted
at 16:00 (`QUOTE_TIME_HOURS` is 16.0 in every file). A 0DTE contract at
16:00 on its expiration day is minutes from expiry and worth essentially
intrinsic value - it says almost nothing about what that contract cost at
09:45 when a strategy would have entered. So entry prices are never read
from this table directly. They are modelled, from a real IV level found
here, and labelled as modelled wherever they surface.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

SOURCE_DIR = Path(r"C:\Users\strea\OneDrive\Desktop\spy strats")
DB_PATH = Path("state/spy_options.db")

STRIKE_BAND_PCT = 0.05      # keep strikes within 5% of spot
MAX_DTE = 5                 # 0DTE plus enough short-dated rows to read IV from

SCHEMA = """
CREATE TABLE IF NOT EXISTS eod_chain (
    quote_date TEXT NOT NULL,
    expire_date TEXT NOT NULL,
    dte REAL,
    underlying REAL,
    strike REAL NOT NULL,
    strike_distance_pct REAL,
    call_bid REAL, call_ask REAL, call_iv REAL, call_delta REAL,
    call_gamma REAL, call_vega REAL, call_theta REAL, call_volume REAL,
    put_bid REAL, put_ask REAL, put_iv REAL, put_delta REAL,
    put_gamma REAL, put_vega REAL, put_theta REAL, put_volume REAL,
    PRIMARY KEY (quote_date, expire_date, strike)
);
CREATE INDEX IF NOT EXISTS eod_chain_quote ON eod_chain(quote_date, dte);

CREATE TABLE IF NOT EXISTS ingest_log (
    source TEXT PRIMARY KEY,
    rows_read INTEGER,
    rows_stored INTEGER,
    ingested_at TEXT
);
"""

COLUMNS = (
    "quote_date", "expire_date", "dte", "underlying", "strike", "strike_distance_pct",
    "call_bid", "call_ask", "call_iv", "call_delta",
    "call_gamma", "call_vega", "call_theta", "call_volume",
    "put_bid", "put_ask", "put_iv", "put_delta",
    "put_gamma", "put_vega", "put_theta", "put_volume",
)


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def open_readonly(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _clean(value: Any) -> float | None:
    """Parquet columns arrive as str/float/None mixtures; blanks and
    unparseable values become NULL rather than 0.0, because a zero bid is
    a real and meaningful quote while a missing one is not."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows_from_batch(batch) -> Iterator[tuple]:
    data = batch.to_pydict()
    get = lambda name: data.get(f"[{name}]", [None] * batch.num_rows)

    quote_dates = get("QUOTE_DATE")
    expire_dates = get("EXPIRE_DATE")
    dtes = get("DTE")
    unders = get("UNDERLYING_LAST")
    strikes = get("STRIKE")
    distances = get("STRIKE_DISTANCE_PCT")
    fields = {name: get(name) for name in (
        "C_BID", "C_ASK", "C_IV", "C_DELTA", "C_GAMMA", "C_VEGA", "C_THETA", "C_VOLUME",
        "P_BID", "P_ASK", "P_IV", "P_DELTA", "P_GAMMA", "P_VEGA", "P_THETA", "P_VOLUME",
    )}

    for i in range(batch.num_rows):
        dte = _clean(dtes[i])
        distance = _clean(distances[i])
        if dte is None or dte > MAX_DTE or dte < 0:
            continue
        if distance is None or abs(distance) > STRIKE_BAND_PCT:
            continue
        strike = _clean(strikes[i])
        quote_date = str(quote_dates[i] or "").strip()[:10]
        expire_date = str(expire_dates[i] or "").strip()[:10]
        if not quote_date or not expire_date or strike is None:
            continue
        yield (
            quote_date, expire_date, dte, _clean(unders[i]), strike, distance,
            *(_clean(fields[name][i]) for name in
              ("C_BID", "C_ASK", "C_IV", "C_DELTA", "C_GAMMA", "C_VEGA", "C_THETA", "C_VOLUME")),
            *(_clean(fields[name][i]) for name in
              ("P_BID", "P_ASK", "P_IV", "P_DELTA", "P_GAMMA", "P_VEGA", "P_THETA", "P_VOLUME")),
        )


def ingest_parquet(conn: sqlite3.Connection, path: Path, *, batch_size: int = 100_000) -> dict[str, Any]:
    """Stream one year's parquet into the compact table."""
    import pyarrow.parquet as pq

    if not path.exists():
        return {"status": "missing", "source": path.name}

    placeholders = ",".join("?" * len(COLUMNS))
    statement = f"INSERT OR REPLACE INTO eod_chain ({','.join(COLUMNS)}) VALUES ({placeholders})"

    read = stored = 0
    reader = pq.ParquetFile(path)
    for batch in reader.iter_batches(batch_size=batch_size):
        read += batch.num_rows
        rows = list(_rows_from_batch(batch))
        if rows:
            conn.executemany(statement, rows)
            stored += len(rows)
    conn.execute(
        "INSERT OR REPLACE INTO ingest_log (source, rows_read, rows_stored, ingested_at) "
        "VALUES (?,?,?,datetime('now'))",
        (path.name, read, stored),
    )
    conn.commit()
    return {"status": "ok", "source": path.name, "read": read, "stored": stored}


def ingest_all(conn: sqlite3.Connection, *, source_dir: Path | None = None,
               progress: bool = True) -> list[dict[str, Any]]:
    directory = source_dir or SOURCE_DIR
    results = []
    for path in sorted(directory.glob("spy_eod_*.parquet")):
        result = ingest_parquet(conn, path)
        results.append(result)
        if progress:
            print(f"  {result['source']}: {result.get('stored', 0):,} of "
                  f"{result.get('read', 0):,} rows kept", flush=True)
    return results


def verify(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) n, COUNT(DISTINCT quote_date) days, MIN(quote_date) a, "
        "MAX(quote_date) b FROM eod_chain"
    ).fetchone()
    zero_dte = conn.execute(
        "SELECT COUNT(*) n, COUNT(DISTINCT quote_date) days FROM eod_chain WHERE dte = 0"
    ).fetchone()
    with_iv = conn.execute(
        "SELECT COUNT(*) n FROM eod_chain WHERE call_iv IS NOT NULL OR put_iv IS NOT NULL"
    ).fetchone()
    return {
        "rows": row["n"],
        "trading_days": row["days"],
        "range": [row["a"], row["b"]],
        "zero_dte_rows": zero_dte["n"],
        "zero_dte_days": zero_dte["days"],
        "rows_with_iv": with_iv["n"],
    }


def main() -> None:
    conn = connect()
    try:
        ingest_all(conn)
        import json
        print(json.dumps(verify(conn), indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
