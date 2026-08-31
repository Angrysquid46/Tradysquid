"""Phase 5 Stage B: the permanent collector jobs and daily data-quality
manifest bookkeeping (Master Spec Section 9). Two scheduler jobs:

- capture_cycle_job: every minute, SPY quotes + the 0DTE chain snapshot
  (mirrors market_data_pilot.py's proven per-minute shape).
- bars_capture_job: every minute, the accumulated 1-minute OHLCV bar series.
  The provider returns the growing day in one call and the writer deduplicates
  by bar timestamp. Minute-scale live traders require newly completed bars;
  a 20-minute batch cadence leaves their evidence stale even while quotes and
  chains remain current.

daily_data_manifest's schema lives in local_information_engine.py's
connect_db() alongside job_runs/engine_state; this module only reads and
increments it.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import market_api_budget
import market_data
import market_data_store

COLLECTOR_VERSION = "market-data-collector-v1"
BAR_BACKFILL_CALENDAR_DAYS = 7
# Fallback only - a full regular-hours session. expected_session_minutes()
# below is the real answer for a specific trading day; this is what it
# falls back to if the calendar lookup fails, not the primary source.
EXPECTED_RTH_MINUTES = 390


def _calendar_days(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value: Any = payload
    for key in ("calendar", "days", "day"):
        if isinstance(value, dict) and key in value:
            value = value[key]
    if isinstance(value, dict):
        value = [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _parse_clock(value: Any, default: time) -> time:
    text = str(value or "")
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return default
    return time(int(match.group(1)), int(match.group(2)))


def expected_session_minutes(trading_day: date) -> int:
    """Real expected regular-trading-hours duration for a specific day,
    including early closes (half-days) - queries Tradier's own
    /markets/calendar rather than assuming every session is a full 390
    minutes (Phase 14 audit finding: a hardcoded 390 misgrades legitimate
    shortened sessions as incomplete). Falls back to EXPECTED_RTH_MINUTES
    on any failure - fetch error, missing day, or a closed/holiday day
    this function was never asked about - matching this repo's existing
    fail-open convention for non-critical grading data."""
    try:
        payload = market_data.tradier_get(
            "/markets/calendar", {"month": trading_day.month, "year": trading_day.year},
            priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT, cache_ttl_seconds=21600,
        )
    except Exception:
        return EXPECTED_RTH_MINUTES
    for item in _calendar_days(payload):
        if str(item.get("date") or "") != trading_day.isoformat():
            continue
        status = str(item.get("status") or "").casefold()
        if status not in {"open", "early-close", "early_close"}:
            return EXPECTED_RTH_MINUTES
        open_data = item.get("open") if isinstance(item.get("open"), dict) else {}
        start = _parse_clock(open_data.get("start") or item.get("open_time"), time(8, 30))
        end = _parse_clock(open_data.get("end") or item.get("close_time"), time(15, 0))
        minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        return minutes if minutes > 0 else EXPECTED_RTH_MINUTES
    return EXPECTED_RTH_MINUTES

VERIFIED_REAL = market_data_store.VERIFIED_REAL
REAL_WITH_LIMITATIONS = market_data_store.REAL_WITH_LIMITATIONS
REJECTED = market_data_store.REJECTED


def find_zero_dte_expiration(symbol: str) -> str | None:
    today = market_data.now_ct().date().isoformat()
    try:
        expirations = market_data.get_expirations(symbol, priority=market_api_budget.PRIORITY_SHARED_OPTIONS_COLLECTION)
    except Exception:
        return None
    return today if today in expirations else None


def classify_quote_row(raw: dict[str, Any], now: datetime) -> tuple[dict[str, Any], str]:
    bid = market_data.as_float(raw.get("bid"))
    ask = market_data.as_float(raw.get("ask"))
    if bid is not None and ask is not None and bid > ask:
        data_class = REJECTED
    elif bid is None or ask is None or not raw.get("bid_date") or not raw.get("ask_date"):
        data_class = REAL_WITH_LIMITATIONS
    else:
        data_class = VERIFIED_REAL
    row = {
        "captured_at": now.isoformat(),
        "symbol": raw.get("symbol"),
        "bid": bid,
        "ask": ask,
        "last": market_data.as_float(raw.get("last")),
        "bid_size": raw.get("bidsize"),
        "ask_size": raw.get("asksize"),
        "change": market_data.as_float(raw.get("change")),
        "change_percentage": market_data.as_float(raw.get("change_percentage")),
        "volume": raw.get("volume"),
        "trade_date_ms": raw.get("trade_date"),
        "bid_date_ms": raw.get("bid_date"),
        "ask_date_ms": raw.get("ask_date"),
        "provider": "tradier",
        "collector_version": COLLECTOR_VERSION,
        "data_class": data_class,
    }
    return row, data_class


def classify_chain_row(
    contract: dict[str, Any], underlying: dict[str, Any], now: datetime
) -> tuple[dict[str, Any], str]:
    bid = market_data.as_float(contract.get("bid"))
    ask = market_data.as_float(contract.get("ask"))
    if bid is not None and ask is not None and bid > ask:
        data_class = REJECTED
    elif bid is None or ask is None or not contract.get("bid_date") or not contract.get("ask_date"):
        data_class = REAL_WITH_LIMITATIONS
    else:
        data_class = VERIFIED_REAL
    row = {
        "captured_at": now.isoformat(),
        "underlying_symbol": contract.get("underlying") or contract.get("root_symbol"),
        "underlying_bid": market_data.as_float(underlying.get("bid")),
        "underlying_ask": market_data.as_float(underlying.get("ask")),
        "underlying_last": market_data.as_float(underlying.get("last")),
        "option_symbol": contract.get("symbol"),
        "expiration": contract.get("expiration_date"),
        "strike": market_data.as_float(contract.get("strike")),
        "side": contract.get("option_type"),
        "bid": bid,
        "ask": ask,
        "last": market_data.as_float(contract.get("last")),
        "bid_size": contract.get("bidsize"),
        "ask_size": contract.get("asksize"),
        "volume": market_data.option_volume_value(contract),
        "open_interest": market_data.open_interest_value(contract),
        "iv": market_data.iv_value(contract),
        "delta": market_data.greek(contract, "delta"),
        "gamma": market_data.greek(contract, "gamma"),
        "theta": market_data.greek(contract, "theta"),
        "vega": market_data.greek(contract, "vega"),
        "bid_date_ms": contract.get("bid_date"),
        "ask_date_ms": contract.get("ask_date"),
        "provider": "tradier",
        "collector_version": COLLECTOR_VERSION,
        "data_class": data_class,
    }
    return row, data_class


def classify_bar_row(
    raw: dict[str, Any], symbol: str, now: datetime
) -> tuple[dict[str, Any], str]:
    if any(raw.get(key) is None for key in ("open", "high", "low", "close")):
        data_class = REJECTED
    elif raw.get("vwap") is None or raw.get("volume") is None:
        data_class = REAL_WITH_LIMITATIONS
    else:
        data_class = VERIFIED_REAL
    row = {
        "bar_time": raw.get("time"),
        "bar_timestamp": raw.get("timestamp"),
        "symbol": symbol,
        "open": market_data.as_float(raw.get("open")),
        "high": market_data.as_float(raw.get("high")),
        "low": market_data.as_float(raw.get("low")),
        "close": market_data.as_float(raw.get("close")),
        "price": market_data.as_float(raw.get("price")),
        "volume": raw.get("volume"),
        "vwap": market_data.as_float(raw.get("vwap")),
        "provider": "tradier",
        "collector_version": COLLECTOR_VERSION,
        "data_class": data_class,
        "captured_at": now.isoformat(),
    }
    return row, data_class


def bar_trading_day(timestamp: int | float) -> date:
    """Derive the physical partition from the provider bar timestamp."""
    return datetime.fromtimestamp(int(timestamp), market_data.MARKET_TZ).date()


def _existing_bar_timestamps(symbol: str) -> set[int]:
    root = market_data_store.DATA_ROOT / market_data_store.BARS_DATASET / symbol
    if not root.exists() or not any(root.rglob("*.parquet")):
        return set()
    glob = market_data_store.dataset_glob(market_data_store.BARS_DATASET, symbol)
    rows = market_data_store.query(
        f"SELECT DISTINCT bar_timestamp FROM read_parquet('{glob}')"
    )
    return {int(row["bar_timestamp"]) for row in rows}


def ingest_bar_rows(
    symbol: str,
    bars: list[dict[str, Any]],
    captured_at: datetime,
) -> dict[str, Any]:
    """Validate, globally deduplicate, and partition bars by their own date.

    One provider response may span several sessions.  The capture date is
    provenance, never the storage partition key.
    """
    existing = _existing_bar_timestamps(symbol)
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    invalid = 0
    duplicates = 0
    seen: set[int] = set()
    for bar in bars:
        timestamp = bar.get("timestamp")
        if timestamp is None:
            invalid += 1
            continue
        timestamp = int(timestamp)
        if timestamp in existing or timestamp in seen:
            duplicates += 1
            continue
        row, cls = classify_bar_row(bar, symbol, captured_at)
        if cls == REJECTED:
            invalid += 1
            continue
        seen.add(timestamp)
        grouped[bar_trading_day(timestamp)].append(row)

    written = 0
    partitions: dict[str, int] = {}
    for trading_day, rows in sorted(grouped.items()):
        if market_data_store.write_bars(symbol, trading_day, captured_at, rows):
            written += len(rows)
            partitions[trading_day.isoformat()] = len(rows)
    return {
        "written": written,
        "invalid": invalid,
        "duplicates": duplicates,
        "partitions": partitions,
    }


def repair_bar_partitions(symbol: str, captured_at: datetime) -> dict[str, int]:
    """Add correctly partitioned copies of legacy misplaced rows.

    The trusted store is append-only, so incorrect legacy part-files are not
    deleted or rewritten.  Queries deduplicate by timestamp; this function
    restores the physical per-day partitions required by point-in-time reads.
    """
    root = market_data_store.DATA_ROOT / market_data_store.BARS_DATASET / symbol
    if not root.exists() or not any(root.rglob("*.parquet")):
        return {}
    glob = market_data_store.dataset_glob(market_data_store.BARS_DATASET, symbol)
    rows = market_data_store.query(
        f"SELECT * FROM read_parquet('{glob}', filename=true)"
    )
    correctly_stored: dict[date, set[int]] = defaultdict(set)
    misplaced: dict[date, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        timestamp = int(row["bar_timestamp"])
        trading_day = bar_trading_day(timestamp)
        expected_dir = market_data_store.partition_dir(
            market_data_store.BARS_DATASET, symbol, trading_day
        ).resolve()
        actual = Path(str(row["filename"])).resolve().parent
        clean = {key: value for key, value in row.items() if key != "filename"}
        if actual == expected_dir:
            correctly_stored[trading_day].add(timestamp)
        else:
            misplaced[trading_day].setdefault(timestamp, clean)

    repaired: dict[str, int] = {}
    for trading_day, by_timestamp in sorted(misplaced.items()):
        rows_to_copy = [
            row for timestamp, row in sorted(by_timestamp.items())
            if timestamp not in correctly_stored[trading_day]
        ]
        if rows_to_copy and market_data_store.write_bars(
            symbol, trading_day, captured_at, rows_to_copy
        ):
            repaired[trading_day.isoformat()] = len(rows_to_copy)
    return repaired


def session_bar_completeness(symbol: str, trading_day: date) -> dict[str, Any]:
    """Audit distinct regular-session minutes across the whole append-only tree."""
    root = market_data_store.DATA_ROOT / market_data_store.BARS_DATASET / symbol
    expected = expected_session_minutes(trading_day)
    start = datetime.combine(trading_day, time(8, 30), market_data.MARKET_TZ)
    expected_timestamps = [int((start + timedelta(minutes=i)).timestamp()) for i in range(expected)]
    observed: set[int] = set()
    if root.exists() and any(root.rglob("*.parquet")):
        glob = market_data_store.dataset_glob(market_data_store.BARS_DATASET, symbol)
        rows = market_data_store.query(
            f"SELECT DISTINCT bar_timestamp FROM read_parquet('{glob}') "
            "WHERE bar_timestamp >= ? AND bar_timestamp < ?",
            [expected_timestamps[0], expected_timestamps[-1] + 60],
        )
        observed = {int(row["bar_timestamp"]) for row in rows}
    missing = [ts for ts in expected_timestamps if ts not in observed]
    periods: list[dict[str, str]] = []
    if missing:
        gap_start = previous = missing[0]
        for timestamp in missing[1:]:
            if timestamp - previous > 60:
                periods.append({
                    "start": datetime.fromtimestamp(gap_start, market_data.MARKET_TZ).isoformat(),
                    "end": datetime.fromtimestamp(previous, market_data.MARKET_TZ).isoformat(),
                })
                gap_start = timestamp
            previous = timestamp
        periods.append({
            "start": datetime.fromtimestamp(gap_start, market_data.MARKET_TZ).isoformat(),
            "end": datetime.fromtimestamp(previous, market_data.MARKET_TZ).isoformat(),
        })
    return {
        "trading_day": trading_day.isoformat(),
        "expected": expected,
        "received": expected - len(missing),
        "missing": len(missing),
        "missing_periods": periods,
        "complete": not missing,
    }


def record_bar_completeness(connection: Any, result: dict[str, Any]) -> None:
    ensure_manifest_row(connection, result["trading_day"])
    connection.execute(
        "UPDATE daily_data_manifest SET missing_periods_json=?, "
        "received_bar_minutes=?, bar_grade=?, bar_audited_at=? "
        "WHERE trading_day=?",
        (
            json.dumps(result["missing_periods"], separators=(",", ":")),
            result["received"],
            "A" if result["complete"] else "REJECT",
            market_data.now_ct().isoformat(),
            result["trading_day"],
        ),
    )
    connection.commit()


def ensure_manifest_row(connection, trading_day: str) -> None:
    expected_minutes = expected_session_minutes(date.fromisoformat(trading_day))
    connection.execute(
        """
        INSERT INTO daily_data_manifest (
            trading_day, expected_minutes, received_quote_minutes,
            received_chain_snapshots, missing_periods_json, api_errors,
            duplicates, invalid_observations, collector_version, grade, graded_at
        ) VALUES (?, ?, 0, 0, '[]', 0, 0, 0, ?, '', '')
        ON CONFLICT(trading_day) DO NOTHING
        """,
        (trading_day, expected_minutes, COLLECTOR_VERSION),
    )
    connection.commit()


def record_cycle_result(
    connection,
    trading_day: str,
    *,
    quote_written: bool,
    chain_written: bool,
    api_errors: int = 0,
    invalid: int = 0,
) -> None:
    ensure_manifest_row(connection, trading_day)
    connection.execute(
        """
        UPDATE daily_data_manifest
        SET received_quote_minutes = received_quote_minutes + ?,
            received_chain_snapshots = received_chain_snapshots + ?,
            api_errors = api_errors + ?,
            invalid_observations = invalid_observations + ?
        WHERE trading_day = ?
        """,
        (
            1 if quote_written else 0,
            1 if chain_written else 0,
            api_errors,
            invalid,
            trading_day,
        ),
    )
    connection.commit()


def grade_day(connection, trading_day: str) -> str:
    """Starting thresholds - invented policy for a logging/grading
    feature, not measured data, and deliberately easy to retune:
    A >=98% of expected minutes received with zero invalid rows; B >=90%;
    C >=50%; otherwise REJECT (including no manifest row at all, i.e. the
    collector never ran that day)."""
    row = connection.execute(
        """
        SELECT expected_minutes, received_quote_minutes, received_chain_snapshots,
               invalid_observations
        FROM daily_data_manifest WHERE trading_day=?
        """,
        (trading_day,),
    ).fetchone()
    if row is None:
        grade = "REJECT"
    else:
        expected, received_quotes, received_chain, invalid = row
        expected = expected or 1
        received = min(received_quotes, received_chain)
        ratio = received / expected
        if ratio >= 0.98 and not invalid:
            grade = "A"
        elif ratio >= 0.90:
            grade = "B"
        elif ratio >= 0.50:
            grade = "C"
        else:
            grade = "REJECT"
        connection.execute(
            "UPDATE daily_data_manifest SET grade=?, graded_at=? WHERE trading_day=?",
            (grade, market_data.now_ct().isoformat(), trading_day),
        )
        connection.commit()
    return grade


def capture_cycle_job(connection) -> str:
    symbol = market_data.TICKER
    now = market_data.now_ct()
    trading_day = now.date()
    trading_day_str = trading_day.isoformat()
    quote_written = False
    chain_written = False
    api_errors = 0
    invalid = 0
    raw_quote: dict[str, Any] | None = None

    try:
        quotes = market_data.get_quotes(
            [symbol], include_greeks=False,
            priority=market_api_budget.PRIORITY_SHARED_SPY_OBSERVATIONS,
        )
        raw_quote = quotes.get(symbol)
    except Exception:
        api_errors += 1

    if raw_quote:
        row, cls = classify_quote_row(raw_quote, now)
        if cls == REJECTED:
            invalid += 1
        else:
            path = market_data_store.write_quote(symbol, trading_day, now, [row])
            quote_written = path is not None
    elif api_errors == 0:
        invalid += 1

    expiration = find_zero_dte_expiration(symbol)
    if expiration:
        try:
            contracts = market_data.get_chain(
                symbol, expiration,
                priority=market_api_budget.PRIORITY_SHARED_OPTIONS_COLLECTION,
            )
        except Exception:
            api_errors += 1
        else:
            rows = []
            for contract in contracts:
                row, cls = classify_chain_row(contract, raw_quote or {}, now)
                if cls == REJECTED:
                    invalid += 1
                    continue
                rows.append(row)
            path = market_data_store.write_chain_snapshot(symbol, trading_day, now, rows)
            chain_written = path is not None

    record_cycle_result(
        connection,
        trading_day_str,
        quote_written=quote_written,
        chain_written=chain_written,
        api_errors=api_errors,
        invalid=invalid,
    )
    return (
        f"quote={'OK' if quote_written else 'MISS'} "
        f"chain={'OK' if chain_written else 'MISS'} "
        f"errors={api_errors} invalid={invalid}"
    )


def bars_capture_job(connection) -> str:
    symbol = market_data.TICKER
    now = market_data.now_ct()

    if not market_api_budget.request_allowed(market_api_budget.PRIORITY_SHARED_SPY_OBSERVATIONS):
        return "bars capture skipped: budget gate blocked shared SPY observations"

    try:
        bars = market_data.get_recent_intraday_history(
            symbol, "1min", calendar_days=BAR_BACKFILL_CALENDAR_DAYS
        )
    except Exception as exc:
        return f"bars capture failed: {type(exc).__name__}: {exc}"

    result = ingest_bar_rows(symbol, bars, now)
    audited_days = sorted({bar_trading_day(bar["timestamp"]) for bar in bars if bar.get("timestamp") is not None})
    incomplete = []
    if connection is not None:
        for trading_day in audited_days:
            audit = session_bar_completeness(symbol, trading_day)
            record_bar_completeness(connection, audit)
            if not audit["complete"]:
                incomplete.append(f"{trading_day}:{audit['missing']}")
    return (
        f"{result['written']} new bars written; {result['invalid']} invalid; "
        f"{result['duplicates']} duplicates; partitions={result['partitions']}; "
        f"incomplete={','.join(incomplete) if incomplete else 'none'}"
    )
