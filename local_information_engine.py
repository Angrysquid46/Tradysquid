"""Local dynamic-market information engine.

This process performs frequent monitoring on the user's laptop instead of
GitHub Actions.  It stores observations in SQLite, suppresses duplicate alerts,
and posts to Discord when a local bot token is available.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import socket
import sqlite3
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, quote_plus, urljoin

import market_data
import discord_transport
import activity_log
import ai_coordination
import capture_0dte_chain
import market_data_collector
import diagnostic_upgrade_system as diagnostics
import requests
import trade_intelligence
import upgrade_batch_44
import rivalry_presentation
import scoreboard
import discord_surface_manifest
from run_with_env import load_env

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "local-information.db"
LOCK_HOST = "127.0.0.1"
LOCK_PORT = int(os.environ.get("LOCAL_ENGINE_LOCK_PORT", "8765"))
POLL_SECONDS = int(os.environ.get("LOCAL_ENGINE_POLL_SECONDS", "30"))
MARKET_REFRESH_MINUTES = int(os.environ.get("LOCAL_MARKET_REFRESH_MINUTES", "5"))
FILINGS_REFRESH_MINUTES = int(os.environ.get("LOCAL_FILINGS_REFRESH_MINUTES", "30"))
STATUS_REFRESH_MINUTES = int(os.environ.get("LOCAL_STATUS_REFRESH_MINUTES", "15"))
FULL_SCAN_ENABLED = os.environ.get("LOCAL_FULL_SCAN_ENABLED", "true").lower() == "true"
POSITION_SAFETY_POLL_SECONDS = int(
    # 60s, not 300s: the stream is meant to be the fast path, but this is
    # the floor every position actually gets guaranteed regardless of
    # whether that connects - five minutes was too long for anything
    # already in a real trade. Still overridable via .env if this needs
    # tuning further either direction.
    os.environ.get("POSITION_SAFETY_POLL_SECONDS", "60")
)
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
TICKER_CHART_DIR = ROOT / "docs" / "tickers"
POSITION_FILE_LOCK = threading.RLock()
MANUAL_SCAN_LOCK = threading.Lock()
PROVIDER_JOB_LOCK = threading.Lock()
RUNNING_JOBS: set[str] = set()
RUNNING_JOBS_LOCK = threading.Lock()
# Phase 3 purge: the live Tradier position-quote stream and its card-
# debounce/staleness machinery (STREAM_QUOTES, STREAM_CARD_*,
# STREAM_QUOTE_*, STREAM_STATS, POSITION_STREAM, _SPY_SPOT_CACHE, and the
# _position_symbols/_stream_quote_event callables main() used to build the
# stream from) existed to re-evaluate open paper positions in real time -
# removed along with the old strategy roster and its positions. Nothing
# in the surviving job set has an open position to stream.


def utc_now() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS observations_kind_time
            ON observations(kind, observed_at DESC);

        CREATE TABLE IF NOT EXISTS engine_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS alerts (
            alert_key TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            last_sent_at TEXT NOT NULL,
            content TEXT NOT NULL
        );

        -- The local provider-event consumer owns its own durable queue.
        -- This schema must be present in every local-information database;
        -- otherwise the startup heartbeat can fail before the engine can
        -- publish any Discord surfaces after an upgrade.
        CREATE TABLE IF NOT EXISTS provider_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE NOT NULL,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            received_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            payload_json TEXT NOT NULL,
            processed_at TEXT,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS provider_event_queue
            ON provider_events(status, priority DESC, available_at, id);

        CREATE TABLE IF NOT EXISTS daily_data_manifest (
            trading_day TEXT PRIMARY KEY,
            expected_minutes INTEGER NOT NULL,
            received_quote_minutes INTEGER NOT NULL DEFAULT 0,
            received_chain_snapshots INTEGER NOT NULL DEFAULT 0,
            missing_periods_json TEXT NOT NULL DEFAULT '[]',
            api_errors INTEGER NOT NULL DEFAULT 0,
            duplicates INTEGER NOT NULL DEFAULT 0,
            invalid_observations INTEGER NOT NULL DEFAULT 0,
            collector_version TEXT NOT NULL DEFAULT '',
            grade TEXT NOT NULL DEFAULT '',
            graded_at TEXT NOT NULL DEFAULT ''
        );
        """
    )
    manifest_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(daily_data_manifest)")
    }
    for name, declaration in (
        ("received_bar_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ("bar_grade", "TEXT NOT NULL DEFAULT ''"),
        ("bar_audited_at", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in manifest_columns:
            connection.execute(
                f"ALTER TABLE daily_data_manifest ADD COLUMN {name} {declaration}"
            )
    connection.commit()
    return connection


def set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO engine_state(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, value, iso_now()),
    )
    connection.commit()


def get_state(connection: sqlite3.Connection, key: str, default: str = "") -> str:
    row = connection.execute(
        "SELECT value FROM engine_state WHERE key = ?", (key,)
    ).fetchone()
    return str(row["value"]) if row else default


def store_observation(
    connection: sqlite3.Connection, kind: str, payload: dict[str, Any]
) -> None:
    connection.execute(
        "INSERT INTO observations(observed_at, kind, payload_json) VALUES (?, ?, ?)",
        (iso_now(), kind, json.dumps(payload, separators=(",", ":"), default=str)),
    )
    connection.execute(
        """
        DELETE FROM observations
        WHERE id IN (
            SELECT id FROM observations
            WHERE kind = ?
            ORDER BY observed_at DESC
            LIMIT -1 OFFSET 2000
        )
        """,
        (kind,),
    )
    connection.commit()


def latest_observation(kind: str) -> dict[str, Any] | None:
    connection = connect_db()
    try:
        row = connection.execute(
            """
            SELECT observed_at, payload_json
            FROM observations
            WHERE kind = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (kind,),
        ).fetchone()
    finally:
        connection.close()
    if not row:
        return None
    return {
        "observed_at": row["observed_at"],
        "payload": json.loads(row["payload_json"]),
    }


def exponential_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = (item - value) * multiplier + value
    return value


def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((item - mean) ** 2 for item in values) / len(values))


def average_true_range(history: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(history) <= period:
        return None
    ranges: list[float] = []
    previous_close: float | None = None
    for day in history:
        high = market_data.as_float(day.get("high"))
        low = market_data.as_float(day.get("low"))
        close = market_data.as_float(day.get("close"))
        if high is None or low is None or close is None:
            continue
        ranges.append(
            max(
                high - low,
                abs(high - previous_close) if previous_close is not None else 0,
                abs(low - previous_close) if previous_close is not None else 0,
            )
        )
        previous_close = close
    return sum(ranges[-period:]) / period if len(ranges) >= period else None


def market_snapshot(symbol: str = market_data.TICKER) -> dict[str, Any]:
    quote = market_data.get_quote(symbol) or {}
    history = market_data.get_daily_history(symbol, days=400)
    spot = market_data.as_float(quote.get("last"))
    if spot is None or not history:
        raise market_data.TradierError(f"{symbol} quote or price history is unavailable")
    try:
        intraday = market_data.get_intraday_history(symbol)
    except (market_data.TradierError, requests.RequestException):
        intraday = []
    closes = [
        value
        for day in history
        if (value := market_data.as_float(day.get("close"))) is not None
    ]
    volumes = [
        value
        for day in history
        if (value := market_data.as_float(day.get("volume"))) is not None
    ]
    context = market_data.directional_market_context(history, spot, intraday)
    ema12 = exponential_moving_average(closes, 12)
    ema26 = exponential_moving_average(closes, 26)
    macd = ema12 - ema26 if ema12 is not None and ema26 is not None else None
    std20 = standard_deviation(closes[-20:])
    sma20 = market_data.simple_moving_average(closes, 20)
    bollinger_upper = sma20 + 2 * std20 if sma20 is not None and std20 is not None else None
    bollinger_lower = sma20 - 2 * std20 if sma20 is not None and std20 is not None else None
    atr14 = average_true_range(history)
    average_volume20 = market_data.simple_moving_average(volumes, 20)
    current_volume = market_data.as_float(quote.get("volume"))
    relative_volume = (
        current_volume / average_volume20
        if current_volume is not None and average_volume20
        else context.get("volume_ratio")
    )
    previous_close = market_data.as_float(quote.get("prevclose"))
    change_pct = (
        (spot / previous_close - 1) * 100 if previous_close and previous_close > 0 else None
    )
    bid = market_data.as_float(quote.get("bid"))
    ask = market_data.as_float(quote.get("ask"))
    spread_pct = (
        (ask - bid) / ((ask + bid) / 2)
        if bid is not None and ask is not None and bid > 0 and ask >= bid
        else None
    )
    support20 = min(closes[-20:]) if closes else spot
    resistance20 = max(closes[-20:]) if closes else spot
    return {
        "symbol": symbol,
        "observed_at": iso_now(),
        "price": spot,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "volume": current_volume,
        "relative_volume": relative_volume,
        "regime": context.get("regime"),
        "qualified": context.get("qualified"),
        "reason": context.get("reason"),
        "failures": context.get("failures") or [],
        "sma20": context.get("sma20"),
        "sma50": context.get("sma50"),
        "sma200": market_data.simple_moving_average(closes, 200),
        "rsi14": context.get("rsi14"),
        "intraday_change_pct": context.get("intraday_change_pct"),
        "intraday_vwap": context.get("intraday_vwap"),
        "intraday_rsi": context.get("intraday_rsi"),
        "intraday_slope_pct": context.get("intraday_slope_pct"),
        "evidence_score": context.get("evidence_score"),
        "ema12": ema12,
        "ema26": ema26,
        "macd": macd,
        "atr14": atr14,
        "bollinger_upper": bollinger_upper,
        "bollinger_lower": bollinger_lower,
        "support20": support20,
        "resistance20": resistance20,
        "day_high": market_data.as_float(quote.get("high")),
        "day_low": market_data.as_float(quote.get("low")),
        "history": history,
    }


def option_quality(option: dict[str, Any], spot: float) -> dict[str, Any]:
    bid = market_data.as_float(option.get("bid"), 0.0) or 0.0
    ask = market_data.as_float(option.get("ask"), 0.0) or 0.0
    mid = (bid + ask) / 2 if bid > 0 and ask >= bid else None
    width = ask - bid if ask >= bid else None
    width_pct = width / mid if width is not None and mid else None
    oi = market_data.open_interest_value(option)
    volume = market_data.option_volume_value(option)
    delta = market_data.greek(option, "delta")
    theta = market_data.greek(option, "theta")
    iv = market_data.iv_value(option)
    strike = market_data.as_float(option.get("strike"))
    option_type = str(option.get("option_type") or "")
    intrinsic = 0.0
    if strike is not None:
        intrinsic = (
            max(spot - strike, 0)
            if option_type == "call"
            else max(strike - spot, 0)
        )
    extrinsic = max((mid or 0) - intrinsic, 0)
    liquidity_pass = (
        oi >= market_data.MIN_OPEN_INTEREST
        and volume >= market_data.MIN_OPTION_VOLUME
        and width_pct is not None
        and width_pct <= market_data.MAX_BID_ASK_PCT
    )
    score = 0.0
    score += min(oi / max(market_data.MIN_OPEN_INTEREST, 1), 5) * 10
    score += min(volume / max(market_data.MIN_OPTION_VOLUME, 1), 5) * 8
    score += max(0, 40 - (width_pct or 1) * 200)
    if delta is not None:
        score += max(0, 20 - abs(abs(delta) - 0.65) * 50)
    return {
        "symbol": option.get("symbol"),
        "underlying": str(
            option.get("root_symbol")
            or option.get("underlying")
            or ""
        ).upper(),
        "type": option_type,
        "strike": strike,
        "expiration": option.get("expiration_date"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "width": width,
        "width_pct": width_pct,
        "open_interest": oi,
        "volume": volume,
        "delta": delta,
        "theta": theta,
        "iv": iv,
        "intrinsic": intrinsic,
        "extrinsic": extrinsic,
        "liquidity_pass": liquidity_pass,
        "quality_score": round(score, 1),
    }


def ranked_option_chain(
    side: str = "call",
    limit: int = 8,
    expiration: str | None = None,
    symbol: str = market_data.TICKER,
) -> list[dict[str, Any]]:
    spot_quote = market_data.get_quote(symbol) or {}
    spot = market_data.as_float(spot_quote.get("last"))
    if spot is None:
        raise market_data.TradierError(f"{symbol} spot price is unavailable")
    expirations = market_data.get_expirations(symbol)
    if expiration is None:
        expiration = next(iter(expirations), None)
    if not expiration:
        return []
    chain = market_data.get_chain(symbol, expiration)
    ranked = [
        option_quality(option, spot)
        for option in chain
        if str(option.get("option_type") or "").lower() == side.lower()
    ]
    ranked = [
        item
        for item in ranked
        if item["strike"] is not None
        and abs(float(item["strike"]) / spot - 1) <= market_data.STRIKE_BAND_PCT
    ]
    ranked.sort(
        key=lambda item: (
            bool(item["liquidity_pass"]),
            float(item["quality_score"]),
            int(item["open_interest"]),
        ),
        reverse=True,
    )
    return ranked[: max(1, min(limit, 15))]


def contract_snapshot(symbol: str) -> dict[str, Any] | None:
    symbol = symbol.strip().upper()
    option = market_data.get_quotes([symbol], include_greeks=True).get(symbol)
    underlying = str(
        (option or {}).get("root_symbol")
        or (option or {}).get("underlying")
        or market_data.TICKER
    ).upper()
    spot_quote = market_data.get_quote(underlying) or {}
    spot = market_data.as_float(spot_quote.get("last"))
    if not option or spot is None:
        return None
    return option_quality(option, spot)


def data_age_text(observed_at: str | None) -> str:
    if not observed_at:
        return "never"
    try:
        parsed = datetime.fromisoformat(observed_at)
        seconds = max(0, int((utc_now() - parsed).total_seconds()))
    except ValueError:
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def market_alert_text(snapshot: dict[str, Any], ticker: str = "SPY") -> str:
    def number(key: str, digits: int = 2, suffix: str = "") -> str:
        value = snapshot.get(key)
        return "Unavailable" if value is None else f"{float(value):.{digits}f}{suffix}"

    return "\n".join(
        [
            f"## {ticker} Local Market Monitor",
            (
                f"**{ticker} ${number('price')}** · **{number('change_pct', 2, '%')}** · "
                f"regime **{snapshot.get('regime', 'Unavailable')}**"
            ),
            (
                f"RSI14 **{number('rsi14', 1)}** · ATR14 **${number('atr14')}** · "
                f"relative volume **{number('relative_volume', 2)}x**"
            ),
            (
                f"Support **${number('support20')}** · resistance **${number('resistance20')}** · "
                f"SMA20 **${number('sma20')}** · SMA50 **${number('sma50')}**"
            ),
            f"**Read:** {snapshot.get('reason') or 'No controlled setup.'}",
            f"Data timestamp: {snapshot.get('observed_at')}",
            "Educational information only—not professional financial advice or a guarantee.",
        ]
    )


def fetch_ticker_news(ticker: str, limit: int = 8) -> list[dict[str, str]]:
    """Fetch a general public-news digest for an integrated ticker."""
    query = quote_plus(f'"{ticker}" stock when:2d')
    response = requests.get(
        f"{GOOGLE_NEWS_RSS_URL}?q={query}&hl=en-US&gl=US&ceid=US:en",
        headers={"User-Agent": market_data.SEC_USER_AGENT or "Tradysquids local monitor"},
        timeout=25,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[dict[str, str]] = []
    for node in root.findall("./channel/item"):
        title = " ".join((node.findtext("title") or "").split())
        link = (node.findtext("link") or "").strip()
        published = (node.findtext("pubDate") or "").strip()
        if title and link:
            items.append({"title": title, "url": link, "date": published})
        if len(items) >= limit:
            break
    return items


def market_is_open() -> bool:
    return bool(market_data.market_is_open_now()[0])


def technicals_text(snapshot: dict[str, Any], ticker: str = "SPY") -> str:
    def value(key: str, digits: int = 2) -> str:
        item = snapshot.get(key)
        return "Unavailable" if item is None else f"{float(item):.{digits}f}"

    session = "LIVE MARKET" if market_is_open() else "AFTER-HOURS / LAST SNAPSHOT"
    return "\n".join([
        "## Tradysquids Technical Dashboard",
        f"**{session}** · {ticker} **${value('price')}** · regime **{snapshot.get('regime')}**",
        f"RSI14 **{value('rsi14', 1)}** · MACD **{value('macd', 3)}** · ATR14 **${value('atr14')}**",
        f"SMA20 **${value('sma20')}** · SMA50 **${value('sma50')}** · SMA200 **${value('sma200')}**",
        f"Bollinger range **${value('bollinger_lower')}–${value('bollinger_upper')}**",
        f"Support **${value('support20')}** · resistance **${value('resistance20')}**",
        f"Updated {snapshot.get('observed_at')}. Educational information only.",
    ])


def market_pulse_text(snapshot: dict[str, Any], ticker: str = "SPY") -> str:
    session = "live" if market_is_open() else "closed; showing the latest available quote"
    return (
        "## Tradysquids Market Pulse\n"
        f"Market is **{session}**.\n"
        + market_alert_text(snapshot, ticker).replace(f"## {ticker} Local Market Monitor\n", "")
    )


def research_store_refresh_job(connection: sqlite3.Connection) -> str:
    """Record each session into the research store so it stays current.

    This exists because the store had gone five years stale - it ended
    2021-05-06 while the system traded 2026 - and every backtest run
    against it was describing a market that no longer existed. Nothing
    was recording sessions as they happened.

    That is the only fix available, because the gap cannot be bought
    back: no provider sells real 1-minute history beyond about a month
    (Tradier ~20 days, Yahoo 30, Robinhood ~30 and it returns SYNTHETIC
    flat bars past that rather than erroring). Data not captured within
    the month is gone permanently. Captured daily, the store grows a real
    1-minute session every trading day.

    Runs after the close as well as during the day, re-requests the last
    few days so a missed run self-heals, and rebuilds features only for
    sessions whose bar count actually changed.
    """
    import spy_research_refresh as srr

    conn = srr.sif.connect()
    try:
        result = srr.refresh(conn, srr.fetch_recent_bars(5))
        # Daily bars carry the session context across the 2021-2026 hole.
        # Optional: yfinance is a research dependency, and a missing one
        # must not take the job down.
        try:
            if now_ct().hour >= 16:
                result.update(srr.refresh_daily(conn, srr.fetch_daily_history()))
        except Exception as exc:
            result["daily_error"] = str(exc)[:120]
        result["coverage"] = srr.coverage(conn)
    finally:
        conn.close()

    # Backfill of the 2021-2026 hole rides along with the daily recording.
    # It is metered by the provider - a free tier allows a handful of calls
    # a day against 63 missing months - so it is resumable by design and a
    # rate limit simply ends this run. Dormant without a key configured.
    try:
        import os

        if os.environ.get("ALPHAVANTAGE_API_KEY", "").strip():
            import spy_gap_backfill as gap

            conn2 = srr.sif.connect()
            try:
                outcome = gap.backfill(conn2)
            finally:
                conn2.close()
            result["gap_months_done"] = outcome.months_done
            result["gap_months_remaining"] = outcome.remaining
            result["gap_stopped_because"] = outcome.stopped_because
    except Exception as exc:
        result["gap_error"] = str(exc)[:160]

    store_observation(connection, "research-store-refresh",
                      {**result, "completed_at": iso_now()})
    cov = result["coverage"]
    changed = result.get("changed") or []
    return (f"{result.get('bars_new', 0)} new bars; "
            f"{len(changed)} session(s) rebuilt; "
            f"store {cov['first']}..{cov['last']} ({cov['sessions']} sessions)")


def _claim_provider_events(connection: sqlite3.Connection, limit: int = 25) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM provider_events
        WHERE status='PENDING' AND available_at <= ?
        ORDER BY priority DESC, id
        LIMIT ?
        """,
        (iso_now(), max(1, min(limit, 100))),
    ).fetchall()
    ids = [row["id"] for row in rows]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        connection.execute(
            f"UPDATE provider_events SET status='PROCESSING' WHERE id IN ({placeholders})",
            ids,
        )
        connection.commit()
    return [
        {**dict(row), "payload": json.loads(row["payload_json"])}
        for row in rows
    ]


def _complete_provider_event(connection: sqlite3.Connection, event_id: int, *, error: str = "") -> None:
    connection.execute(
        "UPDATE provider_events SET status=?, processed_at=?, error=? WHERE id=?",
        ("ERROR" if error else "DONE", iso_now(), error[:1000], int(event_id)),
    )
    connection.commit()


def provider_event_job(connection: sqlite3.Connection) -> str:
    """Consume queued provider events and record them as durable research
    evidence. Used to also route TradingView events into a live strategy
    signal and feed a ticker-universe candidate pool - both removed in the
    Phase 3 purge (strategy-specific and vestigial multi-ticker code
    respectively). This job now only preserves the observation."""
    events = _claim_provider_events(connection, limit=25)
    completed = 0
    for event in events:
        try:
            store_observation(
                connection,
                f"provider-event:{event['provider']}",
                {
                    "symbol": event["symbol"],
                    "event_type": event["event_type"],
                    "payload": event["payload"],
                },
            )
            _complete_provider_event(connection, event["id"])
            completed += 1
        except Exception as exc:
            _complete_provider_event(connection, event["id"], error=str(exc))
    return f"{completed}/{len(events)} provider events processed"



def _current_commit_sha() -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def discord_structure_sync_job(connection: sqlite3.Connection) -> str:
    """Keep the live Discord server's channels, categories, and guide text
    in sync with what the code actually defines. The deploy path deliberately
    never runs this (Discord is a runtime responsibility, not a deployment
    gate - see run_supervisor_simple.py), so this is what actually makes
    "the code changed" eventually mean "Discord changed" - checked on a
    short interval so a same-day code change (this trades 0DTE; a stale
    scanner description or a channel that should be gone sitting there for
    hours is not acceptable) shows up within minutes, not hours. Cheap to
    check every cycle: only the actual Discord API sync - the expensive
    part - is skipped when the code has not moved since the last time it
    ran, so this does not hammer the Discord API when nothing changed."""
    if not (discord_transport.DISCORD_BOT_TOKEN and discord_transport.DISCORD_GUILD_ID):
        return "Discord bot token/guild not configured; skipped"
    current_sha = _current_commit_sha()
    last = latest_observation("discord-structure-sync")
    last_sha = str((last or {}).get("payload", {}).get("sha") or "")
    if current_sha and current_sha == last_sha:
        return f"already synced at {current_sha[:12]}; no code change since"

    import sys

    import sync_discord_structure_reports  # noqa: F401  (runs the patch chain on import)
    import sync_discord_structure_public as public

    original_argv = sys.argv
    try:
        sys.argv = ["sync_discord_structure_public.py", "--apply"]
        result = public.main()
    finally:
        sys.argv = original_argv
    if result:
        raise RuntimeError(f"Discord structure sync exited with code {result}")
    store_observation(connection, "discord-structure-sync", {"at": iso_now(), "sha": current_sha})
    return f"Discord channels, categories, and guides synchronized at {current_sha[:12] or 'unknown'}"


def research_scoring_job(connection: sqlite3.Connection) -> str:
    counts = trade_intelligence.score_research_queue()
    store_observation(connection, "research-scoring", counts)
    return f"{counts['ready']} primary sources ready; {counts['needs_source']} headlines need original-source review"


def intelligence_retention_job(connection: sqlite3.Connection) -> str:
    result = trade_intelligence.apply_retention()
    store_observation(connection, "intelligence-retention", result)
    return f"{result['temporary_files_removed']} temporary files and {result['missing_pointers_removed']} stale pointers removed; canonical evidence preserved"


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def competition_surfaces_job(connection: sqlite3.Connection) -> str:
    """Publish each bot's own dashboard, held-position, and closed-trade cards.

    The former combined rivalry hub is retired; audited results remain in
    each bot's dedicated channels and neutral scorekeeper.
    """
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        return "Discord tracker disabled"
    score_connection = scoreboard.connect_db()
    surface_connection = discord_surface_manifest.connect_db()
    results = []

    for bot in rivalry_presentation.PUBLIC_BOTS:
        bot_fingerprint = _fingerprint({
            "snapshot": scoreboard.scoreboard_snapshot(score_connection, bot),
            "presentation_format": rivalry_presentation.BOT_SURFACE_FORMAT_VERSION,
        })
        state_key = f"competition-surfaces:{bot}:fingerprint"
        if get_state(connection, state_key) == bot_fingerprint:
            results.append(f"{bot}:unchanged")
            continue
        per_bot = rivalry_presentation.publish_bot_surfaces(
            score_connection, surface_connection, tracker, bot
        )
        results.append(f"{bot}:{'ok' if per_bot['ok'] else per_bot['error']}")
        if per_bot["ok"]:
            set_state(connection, state_key, bot_fingerprint)
    return "; ".join(results)


@dataclass
class Job:
    name: str
    interval: timedelta
    callback: Callable[[sqlite3.Connection], str]
    market_hours_only: bool = False
    after_hours_interval: timedelta | None = None
    background: bool = False
    provider_heavy: bool = False
    retry_interval: timedelta | None = None


JOBS = [
    Job(
        "provider-event-queue",
        timedelta(seconds=15),
        provider_event_job,
    ),
    Job(
        "research-scoring",
        timedelta(minutes=15),
        research_scoring_job,
        retry_interval=timedelta(minutes=2),
    ),
    Job(
        "intelligence-retention",
        timedelta(hours=24),
        intelligence_retention_job,
        retry_interval=timedelta(minutes=15),
    ),
    Job(
        "discord-structure-sync",
        timedelta(minutes=3),
        discord_structure_sync_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=2),
    ),
    Job(
        "research-store-refresh",
        timedelta(hours=4),
        research_store_refresh_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=30),
    ),
    # The option archive was a one-time parquet import ending 2023-12-29
    # with no updater, so every backtest priced off either a stale window
    # or a VIX proxy. Nothing can fix that retroactively - no provider
    # sells intraday SPY option history - but Tradier serves the CURRENT
    # chain with real IV and greeks, and SPY lists a same-day expiry every
    # weekday. Captured hourly and stored idempotently per day, the last
    # run before the close is what survives, which is what an end-of-day
    # table wants. From here the archive grows by one measured session a
    # day instead of standing still.
    Job(
        "zero-dte-chain-capture",
        timedelta(hours=1),
        capture_0dte_chain.capture_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=15),
    ),
    # Phase 5 Stage B (Section 9): permanent, append-only Parquet capture,
    # separate from zero-dte-chain-capture's hourly SQLite archive above -
    # both run; retiring the older job is a later decision, not this one.
    Job(
        "spy-market-data-capture",
        timedelta(minutes=1),
        market_data_collector.capture_cycle_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=1),
    ),
    Job(
        "spy-bars-capture",
        timedelta(minutes=1),
        market_data_collector.bars_capture_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=5),
    ),
    # MARKET INTELLIGENCE: previously fully built (upgrade_batch_44.py) but
    # never registered here, so #premarket/#market-regime/#charts-and-levels/
    # #spy-technicals had never posted. Fixing that also required repairing
    # upgrade_batch_44._tracker()/_require_dashboard()/_replace_chart_message(),
    # which called _engine().discord_tracker()/upsert_dashboard() - methods
    # that don't exist on local_information_engine, an old visibility-layer
    # leftover its own install_engine() docstring already flagged as removed.
    Job(
        "active-premarket",
        timedelta(minutes=30),
        upgrade_batch_44.active_premarket_job,
        provider_heavy=True,
        retry_interval=timedelta(minutes=5),
    ),
    Job(
        "market-regime-summary",
        timedelta(minutes=30),
        upgrade_batch_44.market_regime_summary_job,
        provider_heavy=True,
        retry_interval=timedelta(minutes=5),
    ),
    Job(
        "intraday-chart-refresh",
        timedelta(minutes=30),
        upgrade_batch_44.intraday_chart_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=10),
    ),
    Job(
        "market-memory-collection",
        timedelta(minutes=15),
        upgrade_batch_44.market_memory_collection_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=15),
    ),
    Job(
        "spy-technicals-refresh",
        timedelta(minutes=15),
        upgrade_batch_44.spy_technicals_job,
        background=True,
        retry_interval=timedelta(minutes=5),
    ),
    Job(
        "competition-surfaces",
        timedelta(minutes=5),
        competition_surfaces_job,
        background=True,
        retry_interval=timedelta(minutes=2),
    ),
]


def due(connection: sqlite3.Connection, job: Job, now: datetime) -> bool:
    interval = job.interval
    if job.after_hours_interval and not market_is_open():
        interval = job.after_hours_interval
    if job.retry_interval and get_state(connection, f"job-error:{job.name}") == "1":
        interval = job.retry_interval
    last = get_state(connection, f"job:{job.name}")
    if last:
        try:
            if now - datetime.fromisoformat(last) < interval:
                return False
        except ValueError:
            pass
    if job.market_hours_only:
        market_open, _ = market_data.market_is_open_now()
        return market_open
    return True


# Jobs whose successful output is worth a line. Everything else would be
# thousands of "position-tracker: OK" a day, which is how a real signal
# gets buried.
NOTEWORTHY_JOBS = {
    "new-strategy-entry-scan",
    "zero-dte-chain-capture",
    "closed-position-cleanup",
    "backtest-cards",
    "research-store-refresh",
}


def run_job(connection: sqlite3.Connection, job: Job) -> None:
    started = iso_now()
    cursor = connection.execute(
        "INSERT INTO job_runs(job_name, started_at, status) VALUES (?, ?, ?)",
        (job.name, started, "RUNNING"),
    )
    connection.commit()
    try:
        detail = job.callback(connection)
        status = "OK"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:1000]
        status = "ERROR"
        print(f"{job.name}: {detail}", file=sys.stderr)
        # Job failures went to stderr and a sqlite row nobody reads. A
        # failing job is the single most useful thing to know early - the
        # information-engine acceptance check has been RETRYING since
        # 23:52 yesterday and nothing surfaced it.
        activity_log.record("job.error", job=job.name, detail=detail)
    connection.execute(
        "UPDATE job_runs SET finished_at=?, status=?, detail=? WHERE id=?",
        (iso_now(), status, detail, cursor.lastrowid),
    )
    set_state(connection, f"job:{job.name}", utc_now().isoformat())
    set_state(connection, f"job-error:{job.name}", "1" if status == "ERROR" else "0")
    connection.commit()
    if status == "OK" and job.name in NOTEWORTHY_JOBS:
        activity_log.record("job.ok", job=job.name, detail=str(detail)[:300])
    print(f"{job.name}: {status} · {detail}")


def recover_interrupted_jobs(connection: sqlite3.Connection) -> int:
    """Close stale RUNNING rows left behind by a service restart or crash."""
    cursor = connection.execute(
        """
        UPDATE job_runs
        SET finished_at=?, status='INTERRUPTED',
            detail='Service restarted before this job reported completion'
        WHERE status='RUNNING'
        """,
        (iso_now(),),
    )
    connection.commit()
    return int(cursor.rowcount or 0)


def run_background_job(job: Job) -> None:
    """Run a slow provider job without blocking health and event polling."""
    connection = connect_db()
    try:
        if job.provider_heavy:
            with PROVIDER_JOB_LOCK:
                run_job(connection, job)
        else:
            run_job(connection, job)
    finally:
        connection.close()
        with RUNNING_JOBS_LOCK:
            RUNNING_JOBS.discard(job.name)


def start_background_job(job: Job) -> bool:
    with RUNNING_JOBS_LOCK:
        if job.name in RUNNING_JOBS:
            return False
        RUNNING_JOBS.add(job.name)
    threading.Thread(
        target=run_background_job,
        args=(job,),
        name=f"job-{job.name}",
        daemon=True,
    ).start()
    return True


def acquire_instance_lock() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        listener.bind((LOCK_HOST, LOCK_PORT))
        listener.listen(8)
        listener.setblocking(False)
    except OSError as exc:
        listener.close()
        raise RuntimeError(
            "The local information engine is already running."
        ) from exc
    return listener


def drain_health_probes(listener: socket.socket) -> None:
    """Accept queued launcher probes so the single-instance socket stays healthy."""
    while True:
        try:
            connection, _ = listener.accept()
        except BlockingIOError:
            return
        except OSError:
            return
        with connection:
            try:
                connection.sendall(b"OK\n")
            except OSError:
                pass


def serve_health_probes(listener: socket.socket) -> None:
    """Continuously serve launcher probes independently of scheduler sleeps."""
    listener.settimeout(1.0)
    while True:
        try:
            connection, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        with connection:
            try:
                connection.sendall(b"OK\n")
            except OSError:
                pass


def run_once() -> int:
    connection = connect_db()
    try:
        for job in JOBS:
            run_job(connection, job)
    finally:
        connection.close()
    return 0


def main() -> int:
    load_env()
    if "--once" in sys.argv:
        return run_once()
    try:
        instance_lock = acquire_instance_lock()
    except RuntimeError as exc:
        print(exc)
        return 0
    print("Tradysquids local information engine is running.")
    print("Frequent monitoring is local and does not use GitHub Actions minutes.")
    threading.Thread(
        target=serve_health_probes,
        args=(instance_lock,),
        name="engine-health-listener",
        daemon=True,
    ).start()
    connection = connect_db()
    try:
        recovered = recover_interrupted_jobs(connection)
        if recovered:
            print(f"Recovered {recovered} interrupted scheduler job(s).")
        with instance_lock:
            while True:
                current = utc_now()
                for job in JOBS:
                    if due(connection, job, current):
                        if job.background:
                            start_background_job(job)
                        else:
                            run_job(connection, job)
                time.sleep(max(POLL_SECONDS, 10))
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
