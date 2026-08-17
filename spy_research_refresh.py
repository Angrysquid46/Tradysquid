"""Pull recent SPY minute bars from the live provider into the research DB.

The research store was built from a historical dump that stops at
2021-05-06. Every backtest run against it was therefore measuring a market
five years gone - and because load_sessions ordered by bar_time ascending,
a `limit=250` sample started in 2008.

Tradier serves 1-minute timesales for roughly the last 20 calendar days
(confirmed live: the endpoint rejects a start before a moving cutoff), so
this cannot rebuild the missing 2021-2026 span. What it can do is keep a
genuinely recent window in the same store, in the same schema, so a
strategy can be checked against the market as it trades now.

Re-running is a cheap no-op: bars INSERT OR IGNORE on the primary key and
features are only rebuilt for sessions that changed.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import spy_intraday_features as sif
import spy_research_data as srd


def _is_synthetic(bar: dict[str, Any]) -> bool:
    """Gap-fill masquerading as data.

    Robinhood returns `interpolated: true` bars - flat price, zero volume -
    for any range older than its real retention, instead of erroring. A
    probe for May 2026 came back 2,340 bars of which 0 were real: every one
    was the same 772.68 with no volume. Ingesting that would write a
    perfectly flat, zero-volume week into the store, which is far worse
    than having no data, because nothing downstream would flag it.
    """
    if bar.get("interpolated"):
        return True
    volume = bar.get("volume")
    if volume is not None and float(volume) <= 0:
        # A regular-hours SPY minute never has zero volume.
        return True
    return False


def _rows_from_timesales(bars: list[dict[str, Any]]) -> list[tuple]:
    rows: list[tuple] = []
    for bar in bars:
        if _is_synthetic(bar):
            continue
        bar_time = bar.get("time") or bar.get("timestamp")
        if not isinstance(bar_time, str) or len(bar_time) < 19:
            continue
        bar_time = bar_time[:19]
        try:
            rows.append((
                "SPY", bar_time,
                float(bar["open"]), float(bar["high"]),
                float(bar["low"]), float(bar["close"]),
                float(bar.get("volume") or 0.0),
                None,
                float(bar["vwap"]) if bar.get("vwap") is not None else None,
                srd._is_regular_session(bar_time),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def fetch_recent_bars(calendar_days: int = 20) -> list[tuple]:
    """Imported lazily so the module can be used without provider creds."""
    import spy_scanner

    bars = spy_scanner.get_recent_intraday_history("SPY", "1min", calendar_days)
    return _rows_from_timesales(bars or [])



DAILY_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bars (
    ticker TEXT NOT NULL,
    session_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    source TEXT,
    PRIMARY KEY (ticker, session_date)
);
"""


def fetch_daily_history(ticker: str = "SPY", period: str = "max") -> list[tuple]:
    """Daily OHLCV from Yahoo.

    This is what closes the 2021-2026 hole. The intraday store stops at
    2021-05-06 and no provider here sells 1-minute history that far back
    (Tradier ~20 days, Yahoo hard-caps 1-minute at 30), so those sessions
    can never have minute bars. But the features that were CORRUPTED by
    the gap - gap_pct, atr_14, prior-day and prior-week levels - are all
    derived from session-level OHLC, and daily bars supply that perfectly
    back to 1993.
    """
    import warnings

    warnings.filterwarnings("ignore")
    import yfinance as yf

    frame = yf.Ticker(ticker).history(period=period, interval="1d",
                                      auto_adjust=False)
    rows: list[tuple] = []
    for stamp, row in frame.iterrows():
        try:
            rows.append((
                ticker, stamp.date().isoformat(),
                float(row["Open"]), float(row["High"]),
                float(row["Low"]), float(row["Close"]),
                float(row.get("Volume") or 0.0), "yfinance",
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def refresh_daily(conn, rows: list[tuple]) -> dict[str, Any]:
    conn.executescript(DAILY_SCHEMA)
    if not rows:
        return {"daily_seen": 0, "daily_new": 0}
    before = conn.total_changes
    conn.executemany(
        "INSERT OR REPLACE INTO daily_bars (ticker, session_date, open, high, "
        "low, close, volume, source) VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    span = conn.execute(
        "SELECT MIN(session_date), MAX(session_date), COUNT(*) FROM daily_bars"
    ).fetchone()
    return {"daily_seen": len(rows), "daily_written": conn.total_changes - before,
            "daily_first": span[0], "daily_last": span[1], "daily_rows": span[2]}


def refresh(conn, rows: list[tuple], *, rebuild_features: bool = True) -> dict[str, Any]:
    if not rows:
        return {"bars_seen": 0, "bars_new": 0, "sessions": [], "feature_rows": 0}

    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO minute_bars (ticker, bar_time, open, high, low, "
        "close, volume, bar_count, average, regular_session) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    inserted = conn.total_changes - before

    # Only sessions that actually gained bars need their features rebuilt.
    # The scheduled job re-requests the last few days every run, so without
    # this it would recompute unchanged sessions forever.
    sessions = sorted({row[1][:10] for row in rows})
    changed = [
        session for session in sessions
        if conn.execute(
            "SELECT COUNT(*) FROM minute_bars WHERE ticker='SPY' "
            "AND bar_time >= ? AND bar_time < ?", (f"{session}T", f"{session}U")
        ).fetchone()[0] != conn.execute(
            "SELECT COUNT(*) FROM minute_features WHERE ticker='SPY' "
            "AND session_date = ?", (session,)
        ).fetchone()[0]
    ]
    result: dict[str, Any] = {
        "bars_seen": len(rows), "bars_new": inserted,
        "sessions": sessions, "changed": changed, "feature_rows": 0,
    }
    sessions = changed
    if rebuild_features and sessions:
        # Only the touched sessions. build_features still walks earlier
        # sessions to carry prior-day context forward, it just does not
        # recompute them.
        built = sif.build_features(conn, "SPY", sessions=sessions, progress_every=0)
        result["feature_rows"] = built["rows"]
        result["feature_sessions"] = built["sessions"]
    return result


def coverage(conn) -> dict[str, Any]:
    row = conn.execute(
        "SELECT MIN(session_date) a, MAX(session_date) b, "
        "COUNT(DISTINCT session_date) n FROM minute_features WHERE ticker='SPY'"
    ).fetchone()
    recent = conn.execute(
        "SELECT COUNT(DISTINCT session_date) n FROM minute_features "
        "WHERE ticker='SPY' AND session_date >= '2026-01-01'"
    ).fetchone()
    return {"first": row[0], "last": row[1], "sessions": row[2],
            "sessions_2026": recent[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=20,
                        help="calendar days of 1-minute history to request")
    parser.add_argument("--no-features", action="store_true",
                        help="ingest bars only, skip the feature rebuild")
    parser.add_argument("--daily", action="store_true",
                        help="also refresh daily bars (fills the 2021-2026 "
                             "context hole; needs yfinance)")
    parser.add_argument("--daily-only", action="store_true",
                        help="refresh daily bars and nothing else")
    args = parser.parse_args()

    conn = sif.connect()
    try:
        result: dict[str, Any] = {}
        if args.daily or args.daily_only:
            result.update(refresh_daily(conn, fetch_daily_history()))
        if not args.daily_only:
            rows = fetch_recent_bars(args.days)
            result.update(refresh(conn, rows,
                                  rebuild_features=not args.no_features))
        result["coverage"] = coverage(conn)
        print(json.dumps(result, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
