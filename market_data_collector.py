"""Phase 5 Stage B: the permanent collector jobs and daily data-quality
manifest bookkeeping (Master Spec Section 9). Two scheduler jobs:

- capture_cycle_job: every minute, SPY quotes + the 0DTE chain snapshot
  (mirrors market_data_pilot.py's proven per-minute shape).
- bars_capture_job: every ~20 minutes, the accumulated 1-minute OHLCV bar
  series (a low-frequency batch pull - get_recent_intraday_history returns
  the whole day's series in one call, so polling it every minute would
  just re-fetch the same growing series for no benefit).

daily_data_manifest's schema lives in local_information_engine.py's
connect_db() alongside job_runs/engine_state; this module only reads and
increments it.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

import market_api_budget
import market_data
import market_data_store

COLLECTOR_VERSION = "market-data-collector-v1"
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
    trading_day = now.date()

    glob_pattern = market_data_store.dataset_glob(
        market_data_store.BARS_DATASET, symbol, trading_day
    )
    existing_dir = market_data_store.partition_dir(
        market_data_store.BARS_DATASET, symbol, trading_day
    )
    last_timestamp = 0
    if existing_dir.exists() and any(existing_dir.glob("*.parquet")):
        rows = market_data_store.query(
            f"SELECT MAX(bar_timestamp) AS max_ts FROM read_parquet('{glob_pattern}')"
        )
        if rows and rows[0].get("max_ts") is not None:
            last_timestamp = int(rows[0]["max_ts"])

    if not market_api_budget.request_allowed(market_api_budget.PRIORITY_SHARED_SPY_OBSERVATIONS):
        return "bars capture skipped: budget gate blocked shared SPY observations"

    try:
        bars = market_data.get_recent_intraday_history(symbol, "1min", calendar_days=1)
    except Exception as exc:
        return f"bars capture failed: {type(exc).__name__}: {exc}"

    new_rows = []
    invalid = 0
    for bar in bars:
        timestamp = bar.get("timestamp")
        if timestamp is None or int(timestamp) <= last_timestamp:
            continue
        row, cls = classify_bar_row(bar, symbol, now)
        if cls == REJECTED:
            invalid += 1
            continue
        new_rows.append(row)

    market_data_store.write_bars(symbol, trading_day, now, new_rows)
    return f"{len(new_rows)} new bars written; {invalid} invalid; last_timestamp={last_timestamp}"
