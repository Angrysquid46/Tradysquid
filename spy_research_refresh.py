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


def _rows_from_timesales(bars: list[dict[str, Any]]) -> list[tuple]:
    rows: list[tuple] = []
    for bar in bars:
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

    sessions = sorted({row[1][:10] for row in rows})
    result: dict[str, Any] = {
        "bars_seen": len(rows), "bars_new": inserted,
        "sessions": sessions, "feature_rows": 0,
    }
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
    args = parser.parse_args()

    conn = sif.connect()
    try:
        rows = fetch_recent_bars(args.days)
        result = refresh(conn, rows, rebuild_features=not args.no_features)
        result["coverage"] = coverage(conn)
        print(json.dumps(result, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
