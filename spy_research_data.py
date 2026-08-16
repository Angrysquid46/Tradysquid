"""Phase 1 of the SPY strategy research build: ingest the historical datasets.

Loads the owner-supplied research archive into its own SQLite store,
`state/spy_research.db`, kept deliberately separate from
`state/market_memory.db`:

  * market_memory is small, fast, and refreshed daily; it feeds the live
    #spy-technicals charts. Dropping ~1.6 million minute bars into it
    would bloat it and slow the collection cycle for no benefit.
  * This store is large, slow-moving, and read by research code only.
    Nothing in the live trading path imports it.

See docs/SPY_STRATS_BUILD_PLAN.md for the full phase plan.

## Timezone, resolved by evidence rather than assumption

The 1-minute CSV's timestamps are NOT Eastern. Determined empirically:

  * The two highest-volume minutes across 2.07M scanned bars are 13:59
    and 07:30 - the classic U-shaped open/close volume spikes.
  * 07:30 is the most common first bar of the day (3,119 days) and 13:59
    the most common last bar (2,731 days). That is a 6.5-hour session.
  * 07:30 is the session open in BOTH January and July of every year
    checked, so the timestamps follow DST rather than a fixed offset.

Therefore the source is local Mountain time (America/Denver), and ET is
Mountain + 2h year-round. Bars are converted on ingest and STORED IN ET,
matching how market_memory already stores Tradier's naive-Eastern
intraday bars, so the two stores speak the same clock.

Getting this wrong by an hour would silently corrupt every time-of-day
rule in the strategy specs (opening range, 10:30 reversal, power hour,
late-day), which is why it is pinned by a test.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "spy_research.db"

SOURCE_DIR = Path(r"C:\Users\strea\OneDrive\Desktop\spy strats")
MINUTE_CSV = SOURCE_DIR / "spy_1min_2008_2021_cleaned.csv"

SOURCE_TZ = ZoneInfo("America/Denver")
MARKET_TZ = ZoneInfo("America/New_York")

# Regular US equity session in Eastern, used only to tag bars - extended
# hours are kept, not discarded, because gap and premarket strategies in
# the specs need them.
SESSION_OPEN = (9, 30)
SESSION_CLOSE = (15, 59)

# The seven daily CSVs all share a Date key spanning 1993-2026 and are
# meant to be inner-merged on it (per the owner's own
# "macro overlays instructions.txt"). Listed with the file each column
# group comes from so provenance stays traceable.
DAILY_SOURCES: tuple[tuple[str, str], ...] = (
    ("spy_ultimate_max_indicators (1).csv", "indicators"),
    ("spy_macro_execution_overlays.csv", "macro_overlays"),
    ("spy_0dte_velocity_matrix.csv", "velocity_matrix"),
    ("spy_backtest_performance_metrics.csv", "performance_metrics"),
    ("spy_institutional_liquidity_flow.csv", "liquidity_flow"),
    ("spy_options_mechanics_skew.csv", "options_skew"),
    ("spy_structural_alpha_additions.csv", "structural_alpha"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_bars (
    ticker TEXT NOT NULL,
    bar_time TEXT NOT NULL,          -- Eastern, 'YYYY-MM-DDTHH:MM:SS'
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, bar_count REAL, average REAL,
    regular_session INTEGER NOT NULL,
    PRIMARY KEY (ticker, bar_time)
);
CREATE INDEX IF NOT EXISTS minute_bars_session
    ON minute_bars(ticker, substr(bar_time, 1, 10));

CREATE TABLE IF NOT EXISTS daily_indicators (
    ticker TEXT NOT NULL,
    bar_date TEXT NOT NULL,
    column_name TEXT NOT NULL,
    value REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (ticker, bar_date, column_name)
);
CREATE INDEX IF NOT EXISTS daily_indicators_col
    ON daily_indicators(ticker, column_name, bar_date);

CREATE TABLE IF NOT EXISTS ingest_log (
    dataset TEXT PRIMARY KEY,
    rows_ingested INTEGER NOT NULL,
    first_key TEXT,
    last_key TEXT,
    ingested_at TEXT NOT NULL,
    detail TEXT
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


def open_readonly() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Minute bars
# ---------------------------------------------------------------------------

def mountain_to_eastern(stamp: str) -> str:
    """'2008-01-22 07:30:00' (Mountain) -> '2008-01-22T09:30:00' (Eastern).

    Uses real zone conversion rather than a blanket +2h so the result
    stays correct even on the DST changeover days, where a naive shift
    would be wrong for part of the day."""
    naive = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S")
    eastern = naive.replace(tzinfo=SOURCE_TZ).astimezone(MARKET_TZ)
    return eastern.strftime("%Y-%m-%dT%H:%M:%S")


def _is_regular_session(bar_time_et: str) -> int:
    hour, minute = int(bar_time_et[11:13]), int(bar_time_et[14:16])
    minutes = hour * 60 + minute
    return int(
        SESSION_OPEN[0] * 60 + SESSION_OPEN[1] <= minutes <= SESSION_CLOSE[0] * 60 + SESSION_CLOSE[1]
    )


def _float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def iter_minute_rows(path: Path = MINUTE_CSV) -> Iterator[tuple]:
    """Streams the 134 MB CSV rather than loading it, and converts each
    timestamp to Eastern as it goes."""
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            stamp = (row.get("date") or "").strip()
            if not stamp:
                continue
            try:
                bar_time = mountain_to_eastern(stamp)
            except ValueError:
                continue
            yield (
                "SPY", bar_time,
                _float(row.get("open")), _float(row.get("high")),
                _float(row.get("low")), _float(row.get("close")),
                _float(row.get("volume")), _float(row.get("barCount")),
                _float(row.get("average")), _is_regular_session(bar_time),
            )


def ingest_minute_bars(
    conn: sqlite3.Connection, path: Path = MINUTE_CSV, *, batch_size: int = 50_000
) -> dict[str, Any]:
    """INSERT OR IGNORE so a re-run is a cheap no-op and a partial run can
    simply be repeated."""
    before = conn.total_changes
    scanned = 0
    batch: list[tuple] = []
    for row in iter_minute_rows(path):
        batch.append(row)
        scanned += 1
        if len(batch) >= batch_size:
            conn.executemany(
                "INSERT OR IGNORE INTO minute_bars (ticker, bar_time, open, high, low, close, "
                "volume, bar_count, average, regular_session) VALUES (?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            batch.clear()
    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO minute_bars (ticker, bar_time, open, high, low, close, "
            "volume, bar_count, average, regular_session) VALUES (?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
    conn.commit()
    inserted = conn.total_changes - before

    row = conn.execute(
        "SELECT COUNT(*) AS n, MIN(bar_time) AS first, MAX(bar_time) AS last FROM minute_bars WHERE ticker='SPY'"
    ).fetchone()
    _log_ingest(conn, "minute_bars", row["n"], row["first"], row["last"],
                f"scanned {scanned} source rows, inserted {inserted} new")
    return {"scanned": scanned, "inserted": inserted, "total": row["n"],
            "first": row["first"], "last": row["last"]}


# ---------------------------------------------------------------------------
# Daily indicator CSVs
# ---------------------------------------------------------------------------

def ingest_daily_csv(conn: sqlite3.Connection, filename: str, source: str) -> dict[str, Any]:
    """Stored long/tall (one row per date+column) rather than one wide
    table. The seven files carry ~50 columns between them and more may
    arrive later; a tall table absorbs new columns without a migration,
    and the research queries want a handful of named series at a time
    anyway."""
    path = SOURCE_DIR / filename
    if not path.exists():
        return {"source": source, "status": "missing", "rows": 0}

    before = conn.total_changes
    batch: list[tuple] = []
    dates: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = [c for c in (reader.fieldnames or []) if c and c != "Date"]
        for row in reader:
            bar_date = (row.get("Date") or "").strip()[:10]
            if not bar_date:
                continue
            dates.append(bar_date)
            for column in columns:
                value = _float(row.get(column))
                if value is None:
                    continue
                batch.append(("SPY", bar_date, column, value, source))
            if len(batch) >= 20_000:
                conn.executemany(
                    "INSERT OR IGNORE INTO daily_indicators (ticker, bar_date, column_name, value, source) "
                    "VALUES (?,?,?,?,?)", batch)
                batch.clear()
    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO daily_indicators (ticker, bar_date, column_name, value, source) "
            "VALUES (?,?,?,?,?)", batch)
    conn.commit()

    inserted = conn.total_changes - before
    result = {
        "source": source, "status": "ok", "columns": len(columns),
        "dates": len(dates), "inserted": inserted,
        "first": min(dates) if dates else None, "last": max(dates) if dates else None,
    }
    _log_ingest(conn, f"daily:{source}", inserted, result["first"], result["last"],
                f"{len(columns)} columns over {len(dates)} dates")
    return result


def _log_ingest(
    conn: sqlite3.Connection, dataset: str, rows: int, first: str | None, last: str | None, detail: str
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingest_log (dataset, rows_ingested, first_key, last_key, ingested_at, detail) "
        "VALUES (?,?,?,?,?,?)",
        (dataset, rows, first, last, datetime.now().isoformat(timespec="seconds"), detail),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(conn: sqlite3.Connection, ticker: str = "SPY") -> dict[str, Any]:
    """Reconciles what landed against what a sane SPY history should look
    like. Returns findings rather than asserting, so the caller can print
    an honest report including the gaps."""
    minute = conn.execute(
        "SELECT COUNT(*) AS n, MIN(bar_time) AS first, MAX(bar_time) AS last, "
        "SUM(regular_session) AS regular FROM minute_bars WHERE ticker=?", (ticker,)
    ).fetchone()

    sessions = [
        row["d"] for row in conn.execute(
            "SELECT DISTINCT substr(bar_time,1,10) AS d FROM minute_bars "
            "WHERE ticker=? AND regular_session=1 ORDER BY d", (ticker,)
        ).fetchall()
    ]

    # A complete regular session is 390 one-minute bars (09:30-15:59).
    short_sessions = [
        dict(row) for row in conn.execute(
            "SELECT substr(bar_time,1,10) AS d, COUNT(*) AS bars FROM minute_bars "
            "WHERE ticker=? AND regular_session=1 GROUP BY d HAVING bars < 200 ORDER BY d",
            (ticker,)
        ).fetchall()
    ]

    # Validates the Mountain->Eastern conversion against the data that
    # actually landed: the modal first and last regular-session bar must
    # be 09:30 and 15:59 Eastern. Counting bar occurrences per minute
    # would prove nothing here - every minute appears in every session.
    session_open = conn.execute(
        "SELECT t, COUNT(*) AS days FROM ("
        "  SELECT substr(bar_time,1,10) AS d, MIN(substr(bar_time,12,5)) AS t FROM minute_bars"
        "  WHERE ticker=? AND regular_session=1 GROUP BY d"
        ") GROUP BY t ORDER BY days DESC LIMIT 1", (ticker,)
    ).fetchone()
    session_close = conn.execute(
        "SELECT t, COUNT(*) AS days FROM ("
        "  SELECT substr(bar_time,1,10) AS d, MAX(substr(bar_time,12,5)) AS t FROM minute_bars"
        "  WHERE ticker=? AND regular_session=1 GROUP BY d"
        ") GROUP BY t ORDER BY days DESC LIMIT 1", (ticker,)
    ).fetchone()

    daily = conn.execute(
        "SELECT COUNT(DISTINCT bar_date) AS days, COUNT(DISTINCT column_name) AS cols, "
        "MIN(bar_date) AS first, MAX(bar_date) AS last FROM daily_indicators WHERE ticker=?",
        (ticker,)
    ).fetchone()

    by_source = [
        dict(row) for row in conn.execute(
            "SELECT source, COUNT(DISTINCT column_name) AS cols, COUNT(*) AS values_stored "
            "FROM daily_indicators WHERE ticker=? GROUP BY source ORDER BY source", (ticker,)
        ).fetchall()
    ]

    return {
        "minute_bars": dict(minute) if minute else {},
        "minute_sessions": len(sessions),
        "minute_first_session": sessions[0] if sessions else None,
        "minute_last_session": sessions[-1] if sessions else None,
        "modal_session_open_et": dict(session_open) if session_open else {},
        "modal_session_close_et": dict(session_close) if session_close else {},
        "short_sessions": short_sessions[:10],
        "short_session_count": len(short_sessions),
        "daily": dict(daily) if daily else {},
        "daily_by_source": by_source,
    }


def run_ingest(*, minute: bool = True, daily: bool = True) -> dict[str, Any]:
    conn = connect()
    try:
        result: dict[str, Any] = {}
        if daily:
            result["daily"] = [ingest_daily_csv(conn, name, source) for name, source in DAILY_SOURCES]
        if minute:
            result["minute"] = ingest_minute_bars(conn)
        result["verify"] = verify(conn)
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    import json

    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(json.dumps(
        run_ingest(minute=only in ("all", "minute"), daily=only in ("all", "daily")),
        indent=2, default=str,
    ))
