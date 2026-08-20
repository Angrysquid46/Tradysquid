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

import spy_scanner
import ai_coordination
import capture_0dte_chain
import diagnostic_upgrade_system as diagnostics
import dynamic_universe
import outcome_learning
import requests
import tradier_stream
import trade_intelligence
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
STREAM_QUOTES: dict[str, dict[str, Any]] = {}
STREAM_LAST_WRITTEN: dict[str, float] = {}
# P/L last actually rendered onto each card, so a position that moves hard
# can jump the debounce queue instead of sitting stale behind it.
STREAM_LAST_CARD_PL: dict[str, float] = {}
# Card-refresh pacing. These are DISPLAY controls only: evaluate_open_row
# and the close path run on every single tick regardless, so widening them
# can never delay an exit - it only slows how often the visible card is
# redrawn.
#
# Why they exist: a 0DTE option's P/L is never still, so the "content
# unchanged" fast path in upsert_channel_message almost never fires and
# nearly every push became a real PATCH. At the old flat 2s-per-trade
# debounce, six open positions produced ~3 edits/sec into a single
# channel. Discord allows on the order of one edit per second per channel,
# so the channel sat permanently rate-limited - and an exhausted 429 retry
# raises DiscordError, which is what used to tear down the market-data
# websocket.
#
# The interval therefore has to scale with how many cards share the
# channel, not stay flat per card.
# Floor: the fastest a single card may redraw. Each strategy owns its held
# channel now, so a card normally sits alone in its bucket and this floor
# is what it actually runs at. Kept at 2s rather than 1s because the exit
# post and the 60s position-tracker sweep also write to that channel - at
# 1s there is no headroom left for them and the 429s come back.
STREAM_CARD_MIN_SECONDS = float(os.environ.get("STREAM_CARD_MIN_SECONDS", "2"))
STREAM_CARD_SECONDS_PER_POSITION = float(
    os.environ.get("STREAM_CARD_SECONDS_PER_POSITION", "2")
)
# A move this large (in P/L percentage points) since the last redraw is
# worth showing sooner, but never faster than STREAM_CARD_MIN_SECONDS.
STREAM_CARD_FORCE_PL_MOVE = float(os.environ.get("STREAM_CARD_FORCE_PL_MOVE", "10"))


def _card_push_interval(open_position_count: int) -> float:
    """Seconds a single card must wait between redraws.

    Scales with the number of open positions because they all edit the same
    Discord channel and share its rate limit.
    """
    return max(
        STREAM_CARD_MIN_SECONDS,
        max(open_position_count, 1) * STREAM_CARD_SECONDS_PER_POSITION,
    )
# monotonic time.time() each symbol's STREAM_QUOTES entry was last
# refreshed (by a real stream tick OR the active refetch in
# _stream_quote_event) - see STREAM_QUOTE_STALE_SECONDS.
STREAM_QUOTE_RECEIVED_AT: dict[str, float] = {}
# A 0DTE option's own quote can print far less often than SPY's own
# underlying ticks do. _stream_quote_event used to only re-evaluate a
# position when its OWN option symbol ticked - real bug caught live: a
# a trade peaked at +29%, but its option hadn't ticked again
# by the time price reversed, so it didn't get re-checked until it had
# already fallen to +6% (a 23-point overshoot past where the floor
# should have locked it in). Now, on ANY tick relevant to an open row
# (its own option OR its underlying), a quote older than this many
# seconds gets actively refetched via REST before evaluating, instead of
# passively waiting for the option to tick again on its own.
#
# Started at 2.0s; caught live still leaving a real gap - a $0.16, high-
# theta 0DTE put peaked +31% and closed -25% (target was -15%, a 10-point
# overshoot) even through this fixed path, because the whole swing
# happened inside one 2-second staleness window. Tightened to 0.5s: this
# doesn't guarantee zero overshoot (no discrete-interval check can, in a
# continuously moving market - a violent enough move inside even a
# sub-second window would still slip through), but it bounds the worst
# case to a quarter of what it was, not eliminates the concept.
STREAM_QUOTE_STALE_SECONDS = 0.5

# Counters for the live exit path, so its cost and latency can be measured
# instead of estimated. Flushed by position_tracker_job. Plain ints
# incremented on the hot path - no locking, since an occasional lost
# increment does not change what these are for, and contention here would
# slow the very path being measured.
STREAM_STATS: dict[str, float] = {
    "ticks": 0.0,           # stream events received
    "relevant_ticks": 0.0,  # events touching an open position
    "evaluations": 0.0,     # exit checks actually run
    "refetches": 0.0,       # REST calls forced by a stale option quote
    "closes": 0.0,          # exits fired from the stream path
    "card_pushes": 0.0,     # Discord updates (2s-debounced display branch)
    "eval_seconds": 0.0,    # cumulative time in evaluation
    "projection_skips": 0.0,  # refetches avoided by the delta projection
    "drift_refetches": 0.0,   # forced because SPY outran the projection
}

POSITION_STREAM: tradier_stream.TradierPositionStream | None = None
# SPY's own spot price for Key-Levels' underlying-level stop/target check
# (see _stream_quote_event) - cached rather than fetched on every option
# tick, since ticks can arrive many times a second. Staleness bound
# shares STREAM_QUOTE_STALE_SECONDS (not a separate hardcoded value) as
# of 2026-08-13 - this cache used to allow up to 2s of staleness, four
# times looser than the 0.5s bound the option-quote path was tightened
# to on 2026-08-11 (PR #173) after a real overshoot got caught live.
# Real evidence this second gap existed too, not just a theoretical
# inconsistency: SPY_KEY_LEVELS trades kept overshooting by 20+ points
# (2026-08-12 14:35, well after the #173 fix) while 0DTE trades'
# overshoot shrank as intended - Key-Levels' stop/target check runs off
# THIS cache, which the #173 fix never touched.
_SPY_SPOT_CACHE: tuple[float | None, float] = (None, 0.0)


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
        """
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
        high = spy_scanner.as_float(day.get("high"))
        low = spy_scanner.as_float(day.get("low"))
        close = spy_scanner.as_float(day.get("close"))
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


def market_snapshot(symbol: str = spy_scanner.TICKER) -> dict[str, Any]:
    quote = spy_scanner.get_quote(symbol) or {}
    history = spy_scanner.get_daily_history(symbol, days=400)
    spot = spy_scanner.as_float(quote.get("last"))
    if spot is None or not history:
        raise spy_scanner.TradierError(f"{symbol} quote or price history is unavailable")
    try:
        intraday = spy_scanner.get_intraday_history(symbol)
    except (spy_scanner.TradierError, requests.RequestException):
        intraday = []
    closes = [
        value
        for day in history
        if (value := spy_scanner.as_float(day.get("close"))) is not None
    ]
    volumes = [
        value
        for day in history
        if (value := spy_scanner.as_float(day.get("volume"))) is not None
    ]
    context = spy_scanner.directional_market_context(history, spot, intraday)
    ema12 = exponential_moving_average(closes, 12)
    ema26 = exponential_moving_average(closes, 26)
    macd = ema12 - ema26 if ema12 is not None and ema26 is not None else None
    std20 = standard_deviation(closes[-20:])
    sma20 = spy_scanner.simple_moving_average(closes, 20)
    bollinger_upper = sma20 + 2 * std20 if sma20 is not None and std20 is not None else None
    bollinger_lower = sma20 - 2 * std20 if sma20 is not None and std20 is not None else None
    atr14 = average_true_range(history)
    average_volume20 = spy_scanner.simple_moving_average(volumes, 20)
    current_volume = spy_scanner.as_float(quote.get("volume"))
    relative_volume = (
        current_volume / average_volume20
        if current_volume is not None and average_volume20
        else context.get("volume_ratio")
    )
    previous_close = spy_scanner.as_float(quote.get("prevclose"))
    change_pct = (
        (spot / previous_close - 1) * 100 if previous_close and previous_close > 0 else None
    )
    bid = spy_scanner.as_float(quote.get("bid"))
    ask = spy_scanner.as_float(quote.get("ask"))
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
        "sma200": spy_scanner.simple_moving_average(closes, 200),
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
        "day_high": spy_scanner.as_float(quote.get("high")),
        "day_low": spy_scanner.as_float(quote.get("low")),
        "history": history,
    }


def option_quality(option: dict[str, Any], spot: float) -> dict[str, Any]:
    bid = spy_scanner.as_float(option.get("bid"), 0.0) or 0.0
    ask = spy_scanner.as_float(option.get("ask"), 0.0) or 0.0
    mid = (bid + ask) / 2 if bid > 0 and ask >= bid else None
    width = ask - bid if ask >= bid else None
    width_pct = width / mid if width is not None and mid else None
    oi = spy_scanner.open_interest_value(option)
    volume = spy_scanner.option_volume_value(option)
    delta = spy_scanner.greek(option, "delta")
    theta = spy_scanner.greek(option, "theta")
    iv = spy_scanner.iv_value(option)
    strike = spy_scanner.as_float(option.get("strike"))
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
        oi >= spy_scanner.MIN_OPEN_INTEREST
        and volume >= spy_scanner.MIN_OPTION_VOLUME
        and width_pct is not None
        and width_pct <= spy_scanner.MAX_BID_ASK_PCT
    )
    score = 0.0
    score += min(oi / max(spy_scanner.MIN_OPEN_INTEREST, 1), 5) * 10
    score += min(volume / max(spy_scanner.MIN_OPTION_VOLUME, 1), 5) * 8
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
    symbol: str = spy_scanner.TICKER,
) -> list[dict[str, Any]]:
    spot_quote = spy_scanner.get_quote(symbol) or {}
    spot = spy_scanner.as_float(spot_quote.get("last"))
    if spot is None:
        raise spy_scanner.TradierError(f"{symbol} spot price is unavailable")
    expirations = spy_scanner.get_expirations(symbol)
    if expiration is None:
        expiration = next(iter(expirations), None)
    if not expiration:
        return []
    chain = spy_scanner.get_chain(symbol, expiration)
    ranked = [
        option_quality(option, spot)
        for option in chain
        if str(option.get("option_type") or "").lower() == side.lower()
    ]
    ranked = [
        item
        for item in ranked
        if item["strike"] is not None
        and abs(float(item["strike"]) / spot - 1) <= spy_scanner.STRIKE_BAND_PCT
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
    option = spy_scanner.get_quotes([symbol], include_greeks=True).get(symbol)
    underlying = str(
        (option or {}).get("root_symbol")
        or (option or {}).get("underlying")
        or spy_scanner.TICKER
    ).upper()
    spot_quote = spy_scanner.get_quote(underlying) or {}
    spot = spy_scanner.as_float(spot_quote.get("last"))
    if not option or spot is None:
        return None
    return option_quality(option, spot)


def performance_snapshot(ticker: str | None = None) -> dict[str, Any]:
    rows = spy_scanner.read_log()
    if ticker:
        rows = [
            row for row in rows
            if str(row.get("ticker") or "F").upper() == ticker.upper()
        ]
    closed = spy_scanner.closed_rows(rows)
    metrics = spy_scanner.result_metrics(closed)
    open_count = len(spy_scanner.open_rows(rows))
    strategy: dict[str, dict[str, float]] = {}
    for row in closed:
        key = row.get("play_type") or "UNKNOWN"
        bucket = strategy.setdefault(key, {"count": 0, "wins": 0, "pl": 0.0})
        bucket["count"] += 1
        bucket["wins"] += 1 if row.get("outcome") == "WIN" else 0
        bucket["pl"] += spy_scanner.realized_pl_dollars(row)
    return {
        "tracked": len(rows),
        "open": open_count,
        "closed": len(closed),
        "metrics": metrics,
        "strategy": strategy,
        "observed_at": iso_now(),
    }


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


def discord_tracker() -> spy_scanner.DiscordTracker | None:
    if not spy_scanner.DISCORD_BOT_TOKEN or not spy_scanner.DISCORD_GUILD_ID:
        return None
    tracker = spy_scanner.initialize_discord()
    return tracker if tracker.ready else None


def upgrade_request_reactions_job(connection: sqlite3.Connection) -> str:
    """Keep member upgrade requests limited to approve/decline reactions."""
    tracker = discord_tracker()
    if not tracker:
        return "waiting for Discord configuration"
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    channel = next(
        (
            item
            for item in channels
            if item.get("name") == "upgrade-requests" and item.get("type") == 0
        ),
        None,
    )
    if not channel:
        return "#upgrade-requests is missing"

    messages = tracker._request(
        "GET", f"/channels/{channel['id']}/messages?limit=100"
    )
    updated = 0
    allowed = {"✅", "❌"}
    approver_id = os.environ.get("DISCORD_ALLOWED_USER_ID", "").strip()
    for message in messages:
        author = message.get("author") or {}
        if author.get("bot") or not (message.get("content") or "").strip():
            continue
        message_id = str(message["id"])
        existing = {
            str((reaction.get("emoji") or {}).get("name") or "")
            for reaction in message.get("reactions") or []
        }
        for emoji in sorted(existing - allowed):
            tracker._request(
                "DELETE",
                f"/channels/{channel['id']}/messages/{message_id}"
                f"/reactions/{quote(emoji, safe='')}",
            )
        for emoji in allowed - existing:
            tracker._request(
                "PUT",
                f"/channels/{channel['id']}/messages/{message_id}"
                f"/reactions/{quote(emoji, safe='')}/@me",
            )
        if approver_id:
            for emoji in allowed:
                users = tracker._request(
                    "GET",
                    f"/channels/{channel['id']}/messages/{message_id}"
                    f"/reactions/{quote(emoji, safe='')}?limit=100",
                )
                for user in users:
                    if user.get("bot") or str(user.get("id")) == approver_id:
                        continue
                    tracker._request(
                        "DELETE",
                        f"/channels/{channel['id']}/messages/{message_id}"
                        f"/reactions/{quote(emoji, safe='')}/{user['id']}",
                    )
        if existing != allowed:
            updated += 1
    return f"{updated} upgrade request(s) normalized"


def upsert_dashboard(
    connection: sqlite3.Connection,
    logical_channel: str,
    state_key: str,
    content: str,
) -> bool:
    """Maintain one bot-authored dashboard message per information channel."""
    tracker = discord_tracker()
    if not tracker:
        return False
    try:
        state = json.loads(get_state(connection, "discord_dashboard_state", "{}"))
    except json.JSONDecodeError:
        state = {}
    message_id = tracker.upsert_channel_message(
        logical_channel,
        state,
        f"local-engine:{state_key}",
        content,
        search_token=f"Tradysquids {state_key}",
    )
    if not message_id:
        return False
    set_state(connection, "discord_dashboard_state", json.dumps(state))
    return True



def send_ticker_chart(
    connection: sqlite3.Connection,
    ticker: str,
    file_path: Path,
    content: str,
) -> bool:
    """Upload one fresh chart per ticker per market date."""
    tracker = discord_tracker()
    if not tracker or not file_path.exists():
        return False
    state_key = f"ticker-chart-date:{ticker}"
    today = spy_scanner.now_ct().date().isoformat()
    if get_state(connection, state_key) == today:
        return True
    response = tracker.send_channel_file("charts", file_path, content=content)
    if not response:
        return False
    set_state(connection, state_key, today)
    return True


def fetch_ticker_news(ticker: str, limit: int = 8) -> list[dict[str, str]]:
    """Fetch a general public-news digest for an integrated ticker."""
    query = quote_plus(f'"{ticker}" stock when:2d')
    response = requests.get(
        f"{GOOGLE_NEWS_RSS_URL}?q={query}&hl=en-US&gl=US&ceid=US:en",
        headers={"User-Agent": spy_scanner.SEC_USER_AGENT or "Tradysquids local monitor"},
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


def managed_ticker_news_job(connection: sqlite3.Connection) -> str:
    completed: list[str] = []
    failed: list[str] = []
    for ticker in dynamic_universe.active_symbols():
        try:
            items = fetch_ticker_news(ticker)
            lines = [
                f"## {ticker} News & Events",
                "General public-news monitor; verify the original publisher before acting.",
            ]
            lines.extend(
                f"• [{item['title']}]({item['url']})"
                for item in items
            )
            if not items:
                lines.append("No recent matching headlines were returned.")
            lines.append(
                f"Checked {iso_now()}. Headlines are informational, not automatic trade signals."
            )
            upsert_dashboard(
                connection, "news_events", f"news:{ticker}", "\n".join(lines)
            )
            store_observation(connection, f"ticker-news:{ticker}", {"items": items})
            for item in items:
                trade_intelligence.store_research_source({
                    "source_name": "Google News RSS discovery",
                    "source_url": item["url"],
                    "published_at": item.get("date", ""),
                    "ticker": ticker,
                    "claim": item["title"],
                    "confidence": "UNVERIFIED-HEADLINE",
                    "quality": "REQUIRES-ORIGINAL-SOURCE",
                    "learning_concepts": ["news-events", "research-verification"],
                    "usage_terms": "Headline discovery only; verify the original publisher and its terms.",
                    "status": "REVIEW",
                })
            completed.append(ticker)
        except Exception as exc:
            detail = " ".join(str(exc).split())[:240] or "no detail"
            failed.append(f"{ticker}:{type(exc).__name__}:{detail}")
        time.sleep(1.0)
    if failed:
        raise RuntimeError("Ticker news failed for " + ", ".join(failed))
    return (
        f"updated {', '.join(completed) if completed else 'no additional tickers'}"
        + (f" · failed {', '.join(failed)}" if failed else "")
    )


def market_is_open() -> bool:
    return bool(spy_scanner.market_is_open_now()[0])


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


def publish_change_only(
    connection: sqlite3.Connection,
    alert_key: str,
    content: str,
    logical_channel: str = "intelligence",
    minimum_minutes: int = 30,
) -> bool:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    row = connection.execute(
        "SELECT content_hash, last_sent_at FROM alerts WHERE alert_key = ?",
        (alert_key,),
    ).fetchone()
    if row and row["content_hash"] == content_hash:
        return False
    if row:
        try:
            last_sent = datetime.fromisoformat(row["last_sent_at"])
            if utc_now() - last_sent < timedelta(minutes=minimum_minutes):
                return False
        except ValueError:
            pass
    tracker = discord_tracker()
    if tracker:
        tracker.send_channel(logical_channel, content=content)
    elif spy_scanner.DISCORD_WEBHOOK_URL:
        response = requests.post(
            spy_scanner.DISCORD_WEBHOOK_URL,
            json={
                "content": content[:2000],
                "allowed_mentions": {"parse": []},
                "username": "Tradysquids Local Monitor",
            },
            timeout=20,
        )
        response.raise_for_status()
    else:
        return False
    connection.execute(
        """
        INSERT INTO alerts(alert_key, content_hash, last_sent_at, content)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(alert_key) DO UPDATE SET
            content_hash=excluded.content_hash,
            last_sent_at=excluded.last_sent_at,
            content=excluded.content
        """,
        (alert_key, content_hash, iso_now(), content),
    )
    connection.commit()
    return True


def managed_ticker_information_job(connection: sqlite3.Connection) -> str:
    completed: list[str] = []
    failed: list[str] = []
    for ticker in dynamic_universe.active_symbols():
        try:
            snapshot = market_snapshot(ticker)
            store_observation(
                connection,
                f"ticker-market:{ticker}",
                {key: value for key, value in snapshot.items() if key != "history"},
            )
            chart_path = TICKER_CHART_DIR / f"{ticker.lower()}-market-chart.png"
            spy_scanner.render_market_chart_png(
                snapshot["history"],
                float(snapshot["price"]),
                {
                    "regime": snapshot.get("regime"),
                    "rsi14": snapshot.get("rsi14"),
                },
                float(snapshot.get("support20") or snapshot["price"]),
                float(snapshot.get("resistance20") or snapshot["price"]),
                symbol=ticker,
                output_path=chart_path,
            )
            send_ticker_chart(
                connection,
                ticker,
                chart_path,
                (
                    f"{ticker} daily market chart · {spy_scanner.now_ct().date().isoformat()} "
                    f"· ${float(snapshot['price']):.2f} · {snapshot.get('regime')}"
                ),
            )
            upsert_dashboard(
                connection,
                "market_pulse",
                f"market:{ticker}",
                market_pulse_text(snapshot, ticker),
            )
            upsert_dashboard(
                connection,
                "technicals",
                f"technicals:{ticker}",
                "\n".join([
                    f"## {ticker} Technical and Strategy Status",
                    f"Regime: **{snapshot.get('regime')}**",
                    f"Qualified chart: **{'yes' if snapshot.get('qualified') else 'no'}**",
                    f"Evidence: {snapshot.get('reason') or 'No controlled setup.'}",
                    f"RSI14: **{snapshot.get('rsi14')}** · ATR14: **{spy_scanner.fmt_money(snapshot.get('atr14'))}**",
                    f"Support: **{spy_scanner.fmt_money(snapshot.get('support20'))}** · resistance: **{spy_scanner.fmt_money(snapshot.get('resistance20'))}**",
                    f"Updated {snapshot.get('observed_at')}. Educational information only.",
                ]),
            )
            completed.append(ticker)
        except Exception as exc:
            detail = " ".join(str(exc).split())[:240] or "no detail"
            failed.append(f"{ticker}:{type(exc).__name__}:{detail}")
        time.sleep(1.0)
    store_observation(
        connection,
        "market",
        {"completed": completed, "failed": failed, "observed_at": iso_now()},
    )
    if failed:
        raise RuntimeError("Ticker intelligence failed for " + ", ".join(failed))
    return (
        f"updated {', '.join(completed) if completed else 'no additional tickers'}"
        + (f" · failed {', '.join(failed)}" if failed else "")
    )



def status_job(connection: sqlite3.Connection) -> str:
    market = latest_observation("market")
    status = {
        "engine": "online",
        "updated_at": iso_now(),
        "market_data_age": data_age_text(market["observed_at"] if market else None),
        "tradier_configured": bool(spy_scanner.TRADIER_TOKEN),
        "discord_scheduled_posts": bool(
            (spy_scanner.DISCORD_BOT_TOKEN and spy_scanner.DISCORD_GUILD_ID)
            or spy_scanner.DISCORD_WEBHOOK_URL
        ),
        "news_feed_identified": bool(spy_scanner.SEC_USER_AGENT),
    }
    store_observation(connection, "status", status)
    upsert_dashboard(
        connection,
        "status",
        "system-status",
        "\n".join([
            "## Tradysquids System Status",
            "**Engine:** online",
            f"**Market data age:** {status['market_data_age']}",
            f"**Tradier:** {'configured' if status['tradier_configured'] else 'missing'}",
            f"**Discord scheduling:** {'configured' if status['discord_scheduled_posts'] else 'missing'}",
            f"**News feed ID:** {'configured' if status['news_feed_identified'] else 'missing'}",
            f"Updated {status['updated_at']}. This private card updates in place.",
        ]),
    )
    return json.dumps(status, separators=(",", ":"))


def briefing_job(connection: sqlite3.Connection) -> str:
    now = spy_scanner.now_ct()
    weekday = now.weekday() < 5
    session = ""
    if weekday and (7 <= now.hour < 8 or (now.hour == 8 and now.minute < 25)):
        session = "premarket"
    elif weekday and 11 <= now.hour < 13:
        session = "midday"
    elif weekday and 15 <= now.hour < 17:
        session = "after-market"
    if not session:
        return "outside briefing window"
    key = f"briefing:{session}:{now.date().isoformat()}"
    if get_state(connection, key) == "sent":
        return f"{session} already sent"
    symbols = dynamic_universe.active_symbols()
    quotes = spy_scanner.get_quotes(symbols, include_greeks=False) if symbols else {}
    ranked = sorted(
        symbols,
        key=lambda symbol: spy_scanner.as_float((quotes.get(symbol) or {}).get("volume"), 0) or 0,
        reverse=True,
    )
    lines = [
        f"## Tradysquids {session.replace('-', ' ').title()} Briefing",
        f"**{len(symbols)} active universe symbols** · {spy_scanner.portable_strftime(now, '%m/%d/%y %-I:%M %p CT')}",
        "### Highest-Volume Universe Names",
    ]
    for symbol in ranked[:12]:
        quote = quotes.get(symbol) or {}
        price = spy_scanner.as_float(quote.get("last"))
        change = spy_scanner.as_float(quote.get("change_percentage"))
        volume = int(spy_scanner.as_float(quote.get("volume"), 0) or 0)
        change_text = "n/a" if change is None else f"{change:+.2f}%"
        lines.append(
            f"• **{symbol}** · {spy_scanner.fmt_money(price)} · {change_text} · volume {volume:,}"
        )
    lines.extend([
        "### Broad Market Regime",
    ])
    benchmark_payload: dict[str, Any] = {}
    for benchmark in (spy_scanner.TICKER,):
        try:
            snapshot = market_snapshot(benchmark)
            benchmark_payload[benchmark] = {
                key: value for key, value in snapshot.items() if key != "history"
            }
            lines.append(
                f"• **{benchmark}** {spy_scanner.fmt_money(snapshot.get('price'))} · "
                f"{snapshot.get('regime')} · RSI14 {snapshot.get('rsi14')}"
            )
        except Exception as exc:
            lines.append(f"• **{benchmark}:** unavailable ({type(exc).__name__})")
    lines.append(
        "Quotes are timestamped research inputs, not trade instructions or guarantees."
    )
    content = "\n".join(lines)
    store_observation(
        connection,
        "briefing",
        {
            "session": session,
            "date": now.date().isoformat(),
            "symbols": symbols,
            "benchmarks": benchmark_payload,
        },
    )
    sent = upsert_dashboard(
        connection,
        "premarket" if session == "premarket" else "intelligence",
        key,
        content,
    )
    if sent:
        set_state(connection, key, "sent")
    return f"{session} {'sent' if sent else 'stored locally'}"


def weekly_review_job(connection: sqlite3.Connection) -> str:
    now = spy_scanner.now_ct()
    if now.weekday() != 4 or now.hour < 15:
        return "outside weekly review window"
    key = f"weekly-local-review:{now.strftime('%G-W%V')}"
    if get_state(connection, key) == "sent":
        return "weekly review already sent"
    snapshot = performance_snapshot()
    store_observation(connection, "weekly-performance", snapshot)
    metrics = snapshot["metrics"]
    content = "\n".join([
        "## Weekly Tradysquids System Review",
        (
            f"Closed {snapshot['closed']} · open {snapshot['open']} · "
            f"wins {int(metrics.get('wins', 0))} · losses {int(metrics.get('losses', 0))}"
        ),
        (
            f"Win rate {float(metrics.get('win_rate', 0)):.1f}% · "
            f"recorded P/L {spy_scanner.fmt_money(metrics.get('total_pnl'))}"
        ),
        "Review recorded evidence and filter quality before changing strategy rules.",
        "Historical results do not guarantee future performance.",
    ])
    sent = publish_change_only(
        connection,
        key,
        content,
        # performance_stats was retired along with the single combined
        # dashboard - this review is a general system summary across both
        # SPY 0DTE strategies, not specific to either one, so it belongs
        # with the other shared (non-split) weekly content.
        logical_channel="weekly_report",
        minimum_minutes=0,
    )
    if sent:
        set_state(connection, key, "sent")
    return f"weekly review {'sent' if sent else 'stored locally'}"


def _recent_changelog_entries(since: datetime, limit: int = 8) -> list[dict[str, Any]]:
    """COMPLETE entries from the CHANGELOG.jsonl audit trail (ai_coordination.py)
    newer than `since` - the patch log the owner asked to be able to check
    without reading raw git history. Fails open (empty list) on any read
    problem; a missing/corrupt changelog must never break the digest."""
    try:
        lines = ai_coordination.EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "COMPLETE":
            continue
        completed_at = event.get("completed_at")
        try:
            when = datetime.fromisoformat(str(completed_at))
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=since.tzinfo)
        if when < since:
            break
        entries.append(event)
        if len(entries) >= limit:
            break
    return entries


def _overshoot_rollup(rows: list[dict[str, str]], since: datetime) -> tuple[int, int, list[str]]:
    """(stop_closes, overshoots, worst_examples) for trades closed since
    `since` - reuses spy_scanner.compute_stop_overshoot so this rollup can
    never drift from what the close card itself shows."""
    stop_closes = 0
    overshoots: list[tuple[float, str]] = []
    for row in rows:
        closed_at = spy_scanner.parse_iso(row.get("closed_at"))
        if not closed_at or closed_at < since:
            continue
        if spy_scanner.stop_overshoot_target_pct(row) is None:
            continue
        stop_closes += 1
        slip = spy_scanner.compute_stop_overshoot(row)
        if slip is not None:
            overshoots.append((slip, str(row.get("trade_id") or "")))
    overshoots.sort()
    worst = [
        f"{trade_id} slipped {abs(slip):.0f} pts" for slip, trade_id in overshoots[:3]
    ]
    return stop_closes, len(overshoots), worst


def system_digest_job(connection: sqlite3.Connection) -> str:
    """Once-daily, single upserted card (never a new message per run) that
    rolls up what the owner asked to be able to check without hunting
    through Discord: trading-logic anomalies (stop/floor overshoots),
    infra health (from diagnostic_upgrade_system's existing 5-minute
    checks), and the patch log (CHANGELOG.jsonl) - all in one place,
    posted to #system-health where the rest of this system's status cards
    already live."""
    tracker = discord_tracker()
    if not tracker:
        return "Discord tracker unavailable"
    now = spy_scanner.now_ct()
    since = now - timedelta(hours=24)
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
    stop_closes, overshoot_count, worst = _overshoot_rollup(rows, since)
    health = diagnostics.diagnostics_summary()
    open_issues = health.get("open", [])
    changelog_entries = _recent_changelog_entries(since)

    lines = [
        "## Daily System Digest",
        f"**Window:** last 24h, checked {spy_scanner.portable_strftime(now, '%m/%d/%y %-I:%M %p CT')}",
        "### Trading Anomalies",
        (
            f"**Stop overshoots:** {overshoot_count} of {stop_closes} stop/floor closes"
            if stop_closes
            else "No stop/floor closes in this window."
        ),
    ]
    if worst:
        lines.append("Worst: " + " · ".join(worst))
    lines.append(spy_scanner.format_market_condition_breakdown(rows))
    lines.append("### Infra Health")
    if open_issues:
        lines.append(
            f"**{len(open_issues)} open issue(s):** "
            + " · ".join(str(issue.get("signature_key") or "unknown") for issue in open_issues[:5])
        )
    else:
        lines.append("No open infra issues (see #upgrade-review for the live checklist).")
    lines.append("### Patch Log")
    if changelog_entries:
        lines.append(f"**{len(changelog_entries)} change(s) in this window:**")
        lines.extend(
            f"- {entry.get('task', 'unlabeled change')[:140]}" for entry in changelog_entries
        )
    else:
        lines.append("No changes recorded in this window.")

    content = "\n".join(lines)
    report_state = spy_scanner.read_report_state()
    tracker.upsert_channel_message(
        "status",
        report_state,
        "system-digest",
        content,
        search_token="Daily System Digest",
    )
    spy_scanner.write_report_state(report_state)
    store_observation(
        connection,
        "system-digest",
        {"stop_closes": stop_closes, "overshoots": overshoot_count, "open_issues": len(open_issues)},
    )
    return f"{stop_closes} stop closes · {overshoot_count} overshoots · {len(open_issues)} open infra issue(s)"





def backtest_cards_job(connection: sqlite3.Connection) -> str:
    """One self-updating card per strategy in #backtest-results.

    Separate from performance reporting on purpose: daily/weekly/monthly
    cover the 15 live strategies and are untouched by this. These cards
    exist so a backtest claim is checked against live results
    continuously, instead of being quoted once and never revisited.

    Cards upsert, so a strategy has exactly one card that rewrites itself
    rather than a growing pile of snapshots.
    """
    import backtest_cards as bc

    results = bc.load_results()
    if not results:
        return "no backtest results stored yet"
    if not spy_scanner.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"

    tracker = spy_scanner.initialize_discord()
    state = spy_scanner.read_report_state()
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()

    posted = 0
    for play_type, stats in sorted(results.items()):
        forward = bc.forward_record(rows, play_type)
        body = bc.render_card(play_type, stats, forward)
        try:
            tracker.upsert_channel_message(
                bc.CHANNEL_KEY, state, bc.card_key(play_type), body,
                search_token=bc.card_key(play_type),
            )
            posted += 1
        except Exception as exc:
            print(f"backtest card {play_type} failed: {exc}", file=sys.stderr)
    spy_scanner.write_report_state(state)

    # Same information as the cards, in a form that is cheap to READ. A
    # later session can learn how every strategy is actually doing from one
    # file - no Discord fetch and, above all, no re-running a backtest,
    # which costs about 40 minutes a pass.
    try:
        import backtest_record as br

        forward = {play: bc.forward_record(rows, play) for play in results}
        record_path = br.write(results, forward)
    except Exception as exc:
        record_path = None
        print(f"strategy record file failed: {exc}", file=sys.stderr)

    store_observation(connection, "backtest-cards",
                      {"cards": posted, "record": str(record_path or ""),
                       "completed_at": iso_now()})
    return (f"{posted} backtest card(s) refreshed"
            + (f"; record -> {record_path}" if record_path else ""))


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


def new_strategy_entry_scan_job(connection: sqlite3.Connection) -> str:
    """Fast entry-only scan for the 13 promoted strategies.

    The full scan runs every 15 minutes, but these strategies read their
    signal off the newest closed bar - so a setup at 10:07 is gone by 10:15.
    Measured over 250 real sessions, a 15-minute cadence sees just 7.6% of
    signals and ORB Immediate never fires at all.

    Deliberately NOT a second spy_scanner.main() call: main() holds
    POSITION_FILE_LOCK for its whole run including chain fetches, which is
    fine every 15 minutes and would starve the exit path every 2.
    scan_new_strategy_entries takes the lock only to read the log and to
    append a row, never across network I/O, and skips any strategy already
    holding a position. Exits keep priority - owner: "we don't want to
    interfere with held positions ability to close out."
    """
    if not FULL_SCAN_ENABLED:
        return "disabled until LOCAL_FULL_SCAN_ENABLED=true"
    if not spy_scanner.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"
    result = spy_scanner.scan_new_strategy_entries(position_lock=POSITION_FILE_LOCK)
    store_observation(connection, "new-strategy-entry-scan",
                      {**result, "completed_at": iso_now()})
    if result.get("opened"):
        return f"opened {result['opened']}: {', '.join(result.get('play_types', []))}"
    return (f"{result.get('scanned', 0)} scanned · "
            f"{result.get('reason', 'no entry')}")


def full_scanner_job(connection: sqlite3.Connection) -> str:
    """This system trades SPY exclusively - a direct spy_scanner.main() call,
    not a loop over a ticker universe. See multi_ticker_scan.py's removal:
    that machinery existed only to support scanning tickers beyond SPY."""
    if not FULL_SCAN_ENABLED:
        return "disabled until LOCAL_FULL_SCAN_ENABLED=true"
    if not spy_scanner.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"
    with POSITION_FILE_LOCK:
        exit_code = spy_scanner.main(position_lock=POSITION_FILE_LOCK)
    store_observation(
        connection,
        "full-scan",
        {"results": {spy_scanner.TICKER: exit_code}, "completed_at": iso_now()},
    )
    if exit_code:
        raise RuntimeError(f"Scanner failed for {spy_scanner.TICKER}")
    return f"Options scan completed for {spy_scanner.TICKER}"


def manual_options_scan_job(connection: sqlite3.Connection) -> str:
    """Manual /scan-now trigger for the options scanner - SPY only."""
    if not FULL_SCAN_ENABLED:
        return "disabled until LOCAL_FULL_SCAN_ENABLED=true"
    if not spy_scanner.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"
    with POSITION_FILE_LOCK:
        exit_code = spy_scanner.main(position_lock=POSITION_FILE_LOCK)
    store_observation(
        connection,
        "manual-full-scan",
        {"results": {spy_scanner.TICKER: exit_code}, "completed_at": iso_now()},
    )
    if exit_code:
        raise RuntimeError(f"Scanner failed for {spy_scanner.TICKER}")
    market_open, _ = spy_scanner.market_is_open_now()
    session = "live option chains" if market_open else "market-closed routing checks"
    return f"{spy_scanner.TICKER} processed using {session}"


def manual_intelligence_job(connection: sqlite3.Connection) -> str:
    """Publish a timestamped SPY market snapshot on demand."""
    ticker = spy_scanner.TICKER
    quote = spy_scanner.get_quotes([ticker], include_greeks=False).get(ticker, {})
    tracker = discord_tracker()
    if not tracker:
        return "Discord tracker is unavailable"
    observed_at = iso_now()
    market_open, _ = spy_scanner.market_is_open_now()
    session = "MARKET OPEN" if market_open else "MARKET CLOSED / LAST QUOTES"

    price = spy_scanner.as_float(quote.get("last"))
    volume = int(spy_scanner.as_float(quote.get("volume"), 0) or 0)
    watch_lines = [
        "## Manual SPY Snapshot",
        f"**{session}**",
        f"• **{ticker}** · "
        f"{spy_scanner.fmt_money(price) if price is not None else 'quote unavailable'} "
        f"· volume {volume:,}",
        f"Updated {observed_at}.",
    ]
    upsert_dashboard(connection, "universe_watch", "manual-universe-discovery", "\n".join(watch_lines))

    benchmark_lines = [
        "## Manual Market-Regime Snapshot",
        f"**{session}**",
    ]
    try:
        snapshot = market_snapshot(ticker)
        benchmark_lines.append(
            f"• **{ticker}** {spy_scanner.fmt_money(snapshot['price'])} · "
            f"{snapshot['regime']} · RSI {float(snapshot.get('rsi14') or 0):.1f} · "
            f"support {spy_scanner.fmt_money(snapshot.get('support20'))} · "
            f"resistance {spy_scanner.fmt_money(snapshot.get('resistance20'))}"
        )
    except Exception as exc:
        benchmark_lines.append(f"• **{ticker}** unavailable · {type(exc).__name__}")
    benchmark_lines.append(
        f"Updated {observed_at}. Conditions are not an automatic trade entry."
    )
    upsert_dashboard(connection, "intelligence", "manual-market-regime", "\n".join(benchmark_lines))

    upsert_dashboard(
        connection,
        "premarket",
        "manual-session-briefing",
        "\n".join([
            "## Manual Session Briefing",
            f"**{session}**",
            f"**{ticker}** {spy_scanner.fmt_money(price) if price is not None else 'quote unavailable'}.",
            "The options scanner reports SPY plays in #scanner-feed.",
            f"Generated {observed_at}. Quotes may be stale while markets are closed.",
        ]),
    )

    headlines: list[str] = []
    try:
        items = fetch_ticker_news(ticker, limit=3)
        headlines = [f"• [{item['title']}]({item['url']})" for item in items]
    except Exception:
        pass
    upsert_dashboard(
        connection,
        "news_events",
        "manual-news-digest",
        "\n".join([
            "## Manual News and Events Digest",
            *(headlines or ["No current headlines were returned by the public feed."]),
            f"Checked {observed_at}. Verify original sources before acting.",
        ]),
    )
    store_observation(
        connection,
        "manual-intelligence",
        {"ticker": ticker, "observed_at": observed_at},
    )
    return (
        f"market regime, session briefing, SPY snapshot, and "
        f"{len(headlines)} headlines published"
    )


def _run_manual_step(
    connection: sqlite3.Connection,
    name: str,
    callback: Callable[[sqlite3.Connection], str],
) -> str:
    started = iso_now()
    cursor = connection.execute(
        "INSERT INTO job_runs(job_name, started_at, status) VALUES (?, ?, ?)",
        (f"manual-{name}", started, "RUNNING"),
    )
    connection.commit()
    try:
        detail = callback(connection)
        status = "OK"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:1000]
        status = "ERROR"
    connection.execute(
        "UPDATE job_runs SET finished_at=?, status=?, detail=? WHERE id=?",
        (iso_now(), status, detail, cursor.lastrowid),
    )
    connection.commit()
    return f"**{name}:** {status} · {detail}"


def run_manual_scan(scope: str = "all") -> str:
    """Run one owner-requested local suite and return a Discord-ready summary."""
    normalized = str(scope or "all").strip().lower()
    allowed = {"all", "options", "intelligence", "positions", "health"}
    if normalized not in allowed:
        raise ValueError(f"Unknown manual scan scope: {normalized}")
    if not MANUAL_SCAN_LOCK.acquire(blocking=False):
        raise RuntimeError("Another manual scan is already running.")
    try:
        connection = connect_db()
        try:
            steps = {
                "options": [("options scanner", manual_options_scan_job)],
                "intelligence": [
                    ("provider events", provider_event_job),
                    ("market intelligence", manual_intelligence_job),
                ],
                "positions": [("open positions", position_tracker_job)],
                "health": [("system health", status_job)],
            }
            selected = (
                [
                    *steps["intelligence"],
                    *steps["options"],
                    *steps["positions"],
                    *steps["health"],
                ]
                if normalized == "all"
                else steps[normalized]
            )
            return "\n".join(
                _run_manual_step(connection, name, callback)
                for name, callback in selected
            )
        finally:
            connection.close()
    finally:
        MANUAL_SCAN_LOCK.release()


def publish_tradingview_signal(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    """Turn a raw TradingView alert into a visible Discord card and durable
    research evidence, instead of just a queue row nobody ever sees. This is
    an independent, external read - it is never compared automatically or
    used to gate a real trade; it exists so the owner (and eventually the
    learning system) can see whether it agreed with the bot's own SPY 0DTE
    opening-range signal for the same session."""
    payload = event.get("payload") or {}
    symbol = str(event.get("symbol") or "")
    action = str(payload.get("action") or payload.get("event") or "alert").upper()
    reason = str(payload.get("reason") or "No reason provided in the alert payload.")
    price = spy_scanner.as_float(payload.get("price"))
    event_key = str(event.get("event_key") or event.get("id") or "")

    tracker = discord_tracker()
    if tracker:
        report_state = spy_scanner.read_report_state()
        lines = [
            f"## \U0001f4e1 TradingView Signal · {symbol} · {action}",
            f"**Reason:** {reason}",
            (
                f"**Price at signal:** {spy_scanner.fmt_money(price)}"
                if price is not None else "**Price at signal:** not provided"
            ),
            f"**Event key:** `{event_key}`",
            (
                f"Received {iso_now()}. External signal, independent of the bot's "
                "own opening-range read - compare, do not assume agreement."
            ),
        ]
        tracker.upsert_channel_message(
            "breaking_alerts",
            report_state,
            f"tradingview:{event_key}",
            "\n".join(lines),
            search_token=f"TradingView Signal {symbol}",
        )
        spy_scanner.write_report_state(report_state)

    trade_intelligence.store_research_source({
        "source_name": "TradingView",
        "source_url": "",
        "published_at": iso_now(),
        "ticker": symbol,
        "claim": reason,
        "confidence": "EXTERNAL-SIGNAL",
        "quality": "THIRD-PARTY",
        "learning_concepts": ["0dte-opening-range", "external-signal-comparison"],
        "usage_terms": "Compare against the bot's own SPY 0DTE decision for the same session; never auto-applied.",
        "status": "REVIEW",
    })


def provider_event_job(connection: sqlite3.Connection) -> str:
    """Consume queued provider events (currently: TradingView alerts) and
    route them to a visible Discord card + durable research evidence. This
    used to also feed a ticker-universe candidate pool so a provider event
    could grow which tickers got scanned - removed along with that pool,
    since this system trades SPY exclusively regardless of what any
    provider event names."""
    events = dynamic_universe.claim_events(limit=25)
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
            if event["provider"] == "tradingview":
                publish_tradingview_signal(connection, event)
            dynamic_universe.complete_event(event["id"])
            completed += 1
        except Exception as exc:
            dynamic_universe.complete_event(event["id"], error=str(exc))
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
    if not (spy_scanner.DISCORD_BOT_TOKEN and spy_scanner.DISCORD_GUILD_ID):
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


def _route_stream_close(
    row: dict[str, str],
    evaluation: dict[str, Any],
    report_state: dict[str, Any] | None = None,
) -> None:
    """report_state lets a caller that already holds one (e.g.
    position_tracker_job's loop) share it instead of this function doing
    its own fresh read/write. Without that, a caller which reads its own
    report_state once at the top of a loop and writes it once at the end
    would silently clobber whatever this function persisted in between -
    that's exactly how a just-closed trade's held-position card message-id
    was getting dropped from state, leaving the card impossible to find
    and delete afterward (state lost the id, and the card's own visible
    content never includes the raw trade_id to fall back to)."""
    tracker = discord_tracker()
    if not tracker:
        return
    owns_state = report_state is None
    if owns_state:
        report_state = spy_scanner.read_report_state()
    spy_scanner.post_close(row, evaluation, tracker, report_state)
    rows = spy_scanner.read_log()
    # refresh_all_summary_dashboards, not update_performance_pages directly
    # - the latter gets replaced with a no-op by a separate reconciliation
    # system once it installs, and a stream-triggered close needs to stay
    # correct regardless of whether that's happened yet.
    spy_scanner.refresh_all_summary_dashboards(tracker, report_state, rows)
    spy_scanner.sync_reports(
        tracker,
        report_state,
        rows,
        spy_scanner.now_ct(),
        market_open=spy_scanner.market_is_open_now()[0],
    )
    if owns_state:
        spy_scanner.write_report_state(report_state)


def _position_symbols() -> list[str]:
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
        return spy_scanner.symbols_for_rows(spy_scanner.open_rows(rows))


def _cached_spy_spot() -> float | None:
    global _SPY_SPOT_CACHE
    price, fetched_at = _SPY_SPOT_CACHE
    if time.monotonic() - fetched_at < STREAM_QUOTE_STALE_SECONDS:
        return price
    try:
        quote = spy_scanner.get_quote(spy_scanner.TICKER)
        price = spy_scanner.as_float(quote.get("last")) if quote else None
    except Exception:
        price = None
    _SPY_SPOT_CACHE = (price, time.monotonic())
    return price


# Delta-projection bounds. Tradier production allows 120 REST req/min (2/sec)
# across EVERYTHING, and refetches are batched to one call per staleness
# window - so a flat 0.5s bound has a ceiling of exactly 2/sec, which is the
# entire budget on its own. Tightening it to 0.25s would be 240/min, double
# the limit, and blowing the limit returns 429s precisely when the market is
# moving fast enough to need a fresh quote.
#
# So instead of refreshing every position on one clock, spend the budget
# where a decision is actually close. Between ticks the option's move is
# projected from SPY's using delta - no REST call - and that projection only
# decides WHEN TO LOOK. An exit is never taken on a projected price; the
# real quote is always fetched and re-evaluated before closing.
#
# Near a threshold the bound is unchanged at 0.5s, so nothing gets less
# fresh where it matters. Far from one it relaxes to 2s, which is where the
# budget is recovered.
STREAM_NEAR_EXIT_BAND_PCT = float(
    os.environ.get("STREAM_NEAR_EXIT_BAND_PCT", "25")
)
STREAM_FAR_STALE_SECONDS = float(
    os.environ.get("STREAM_FAR_STALE_SECONDS", "2.0")
)
# How far SPY may drift from the quote the projection is based on before
# that quote must be refetched, regardless of how recent it is or how far
# the projection thinks the position is from a threshold.
#
# The projection is linear in delta, but a 0DTE option is not: gamma makes
# the error grow with the SQUARE of the move, and the worst cases are the
# near-ATM contracts that move fastest. Measured on 2,799 real 0DTE
# contracts inside our own delta band, as percentage points of P/L error:
#
#   SPY move   median   p90     p99
#   $0.10       0.1     0.9     9.8
#   $0.25       0.4     5.5    61.0
#   $0.50       1.5    21.9   243.9
#   $1.00       6.1    87.4   975.5
#
# Past about $0.15 the p99 error exceeds the 25-point near-threshold band,
# which means a violently moving contract could be projected as "far from
# its target" while actually sitting on it. Time alone cannot bound this -
# two quiet seconds and two seconds of a news spike are not the same
# staleness. Capping the drift caps the error directly.
STREAM_MAX_SPOT_DRIFT = float(
    os.environ.get("STREAM_MAX_SPOT_DRIFT", "0.15")
)
# SPY spot at the moment each option quote was captured, so a later SPY tick
# can be projected against it.
STREAM_QUOTE_SPOT_AT: dict[str, float] = {}


def _projected_pl_pct(row: dict[str, str], option_symbol: str,
                      spot_now: float | None) -> float | None:
    """Where this position's P/L probably is right now, from SPY's move.

    Uses the last known option quote plus delta x (SPY move since that
    quote). Deliberately an estimate: 0DTE gamma means delta itself shifts,
    so this is only accurate enough to answer "is a decision close?", which
    is all it is asked.
    """
    quote = STREAM_QUOTES.get(option_symbol) or {}
    entry = spy_scanner.as_float(row.get("entry_price"))
    if not entry or spot_now is None:
        return None
    last_bid = spy_scanner.as_float(quote.get("bid"))
    if last_bid is None:
        return None
    spot_then = STREAM_QUOTE_SPOT_AT.get(option_symbol)
    delta = spy_scanner.as_float((quote.get("greeks") or {}).get("delta"))
    if delta is None:
        delta = spy_scanner.as_float(row.get("delta"))
    if spot_then is None or delta is None:
        # No basis to project from - treat as near, so it refreshes.
        return None
    projected = last_bid + (spot_now - spot_then) * delta
    return (projected - entry) / entry * 100.0


def _near_exit_threshold(row: dict[str, str], projected_pct: float | None) -> bool:
    """True when the projection is close enough to a threshold that the
    quote must be fresh. Unknown counts as near - never skip a refresh
    because something could not be computed."""
    if projected_pct is None:
        return True
    play_type = row.get("play_type") or ""
    try:
        import spy_live_new_strategies as _lns

        exits = _lns.NEW_STRATEGY_EXITS.get(play_type)
    except Exception:
        exits = None
    if not exits:
        return True          # key-levels and anything unmapped: always fresh
    target, stop, _time_stop = exits
    band = STREAM_NEAR_EXIT_BAND_PCT
    return (projected_pct >= target - band) or (projected_pct <= stop + band)


def _stream_quote_event(event: dict[str, Any]) -> None:
    """Evaluate exits immediately when a streamed quote changes (the
    row's own option OR its underlying), and push the held-positions
    card on the same tick (debounced to once per 2s per trade -
    STREAM_LAST_WRITTEN already gated the CSV write at that cadence;
    Discord now rides the same gate instead of waiting for
    position_tracker_job's separate ~90s cycle). This is the actual
    real-time path - position_tracker_job is the REST fallback for a
    missed or disconnected tick, not the live path itself.

    Reacting to underlying ticks matters: a 0DTE option's own quote can
    print far less often than SPY itself ticks, and previously a row was
    only re-evaluated when its own option symbol happened to tick - real
    bug caught live, a trade peaked at +29% but its option
    hadn't ticked again by the time price reversed, so it wasn't
    re-checked until it had already fallen to +6% (23 points of P&L
    given up past where the floor should have locked it in). Now a stale
    option quote gets actively refetched via REST before evaluating
    instead of passively waiting for it to tick on its own."""
    symbol = str(event.get("symbol") or "")
    if not symbol or not spy_scanner.market_is_open_now()[0]:
        return
    STREAM_STATS["ticks"] += 1
    STREAM_QUOTES.setdefault(symbol, {}).update(event)
    now_monotonic = time.monotonic()
    STREAM_QUOTE_RECEIVED_AT[symbol] = now_monotonic
    _tick_spot = _cached_spy_spot()
    if _tick_spot is not None:
        STREAM_QUOTE_SPOT_AT[symbol] = _tick_spot
    timestamp = spy_scanner.now_ct()

    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
        opened = spy_scanner.open_rows(rows)

    # Find which open rows this tick is relevant to, and which of their
    # option quotes have gone stale, before touching the lock again - a
    # REST refetch is network I/O and must not be made while holding
    # POSITION_FILE_LOCK (same reason position_tracker_job fetches quotes
    # before its own second lock acquisition, not during it).
    relevant: list[tuple[dict[str, str], set[str]]] = []
    stale_symbols: set[str] = set()
    for row in opened:
        required = set(spy_scanner.symbols_for_rows([row]))
        underlying_symbol = row.get("ticker", "")
        option_symbols = required - {underlying_symbol}
        if not option_symbols:
            continue
        if symbol not in option_symbols and symbol != underlying_symbol:
            continue
        relevant.append((row, option_symbols))
        _spot_now = _cached_spy_spot()
        for option_symbol in option_symbols:
            age = now_monotonic - STREAM_QUOTE_RECEIVED_AT.get(option_symbol, 0.0)
            projected = _projected_pl_pct(row, option_symbol, _spot_now)

            # SPY has moved too far for a linear projection to be trusted -
            # gamma error grows with the square of the move. Refetch on the
            # spot, whatever the clock or the projection says.
            spot_then = STREAM_QUOTE_SPOT_AT.get(option_symbol)
            if (_spot_now is not None and spot_then is not None
                    and abs(_spot_now - spot_then) > STREAM_MAX_SPOT_DRIFT):
                STREAM_STATS["drift_refetches"] += 1
                stale_symbols.add(option_symbol)
                continue

            if _near_exit_threshold(row, projected):
                bound = STREAM_QUOTE_STALE_SECONDS      # unchanged where it matters
            else:
                bound = STREAM_FAR_STALE_SECONDS
                STREAM_STATS["projection_skips"] += 1
            if age > bound:
                stale_symbols.add(option_symbol)

    if not relevant:
        return

    STREAM_STATS["relevant_ticks"] += 1
    if stale_symbols:
        STREAM_STATS["refetches"] += len(stale_symbols)
        try:
            fresh_quotes = spy_scanner.get_quotes(list(stale_symbols), include_greeks=True)
        except Exception:
            fresh_quotes = {}
        _spot_at_fetch = _cached_spy_spot()
        for option_symbol, quote in fresh_quotes.items():
            STREAM_QUOTES.setdefault(option_symbol, {}).update(quote)
            STREAM_QUOTE_RECEIVED_AT[option_symbol] = now_monotonic
            if _spot_at_fetch is not None:
                STREAM_QUOTE_SPOT_AT[option_symbol] = _spot_at_fetch

    live_updates: list[tuple[dict[str, str], dict[str, Any]]] = []
    with POSITION_FILE_LOCK:
        changed = False
        closed_events: list[tuple[dict[str, str], dict[str, Any]]] = []
        # Discord rate-limits per channel, so a card only contends with
        # other cards in the SAME channel - not with every open position.
        # Each strategy owns a held channel now, so this is normally 1 and
        # every card refreshes at the floor no matter how many strategies
        # are in a trade. Manual trades still share one channel and are
        # still paced against each other.
        channel_load: dict[str, int] = {}
        for _row, _ in relevant:
            _key = spy_scanner.held_channel_key(_row.get("play_type", ""))
            channel_load[_key] = channel_load.get(_key, 0) + 1
        for row, option_symbols in relevant:
            if not option_symbols.issubset(STREAM_QUOTES):
                continue
            _eval_started = time.monotonic()
            evaluation = spy_scanner.evaluate_open_row(
                row, STREAM_QUOTES, timestamp, underlying_spot_price=_cached_spy_spot()
            )
            STREAM_STATS["evaluations"] += 1
            STREAM_STATS["eval_seconds"] += time.monotonic() - _eval_started
            if evaluation.get("pl_pct") is None:
                continue
            signal = evaluation.get("signal")
            if signal in spy_scanner.CLOSING_SIGNALS:
                STREAM_STATS["closes"] += 1
                spy_scanner.close_row(row, evaluation, timestamp)
                closed_events.append((row, evaluation))
                changed = True
            else:
                trade_id = row.get("trade_id", "")
                last_write = STREAM_LAST_WRITTEN.get(trade_id, 0.0)
                elapsed = now_monotonic - last_write
                # Paced against the cards sharing this card's channel only.
                interval = _card_push_interval(
                    channel_load.get(
                        spy_scanner.held_channel_key(row.get("play_type", "")), 1
                    )
                )
                pl_pct = evaluation.get("pl_pct")
                last_card_pl = STREAM_LAST_CARD_PL.get(trade_id)
                jumped = (
                    last_card_pl is not None
                    and pl_pct is not None
                    and abs(pl_pct - last_card_pl) >= STREAM_CARD_FORCE_PL_MOVE
                )
                if elapsed >= interval or (jumped and elapsed >= STREAM_CARD_MIN_SECONDS):
                    STREAM_STATS["card_pushes"] += 1
                    STREAM_LAST_WRITTEN[trade_id] = now_monotonic
                    if pl_pct is not None:
                        STREAM_LAST_CARD_PL[trade_id] = pl_pct
                    changed = True
                    row["current_pl_pct"] = spy_scanner.round_or_blank(
                        evaluation.get("pl_pct"), 1
                    )
                    row["current_pl_dollars"] = spy_scanner.round_or_blank(
                        evaluation.get("pl_dollars"), 0
                    )
                    live_updates.append((row, evaluation))
        if changed:
            spy_scanner.write_log(rows)
        for row, evaluation in closed_events:
            _route_stream_close(row, evaluation)
    if live_updates:
        tracker = discord_tracker()
        if tracker:
            report_state = spy_scanner.read_report_state()
            # Each card gets its own try/except. Real incident: one held
            # position's card hit a Discord rate limit, raised after
            # exhausting retries, and that exception propagated out of this
            # loop - which meant the OTHER open positions' cards silently
            # never got attempted that tick either, and (before the fix in
            # tradier_stream.py) tore down the whole websocket besides. A
            # Discord failure on one trade's card must never block another
            # trade's card in the same batch.
            for row, evaluation in live_updates:
                try:
                    spy_scanner.sync_open_trade_cards(row, tracker, report_state, evaluation)
                except Exception as exc:
                    print(f"card update failed for {row.get('trade_id')}: {exc}",
                         file=sys.stderr)
            spy_scanner.write_report_state(report_state)


def position_tracker_job(connection: sqlite3.Connection) -> str:
    """REST safety refresh used if a stream tick is missed or disconnected.

    Also the actual driver of a live held-positions card: this runs on a
    fast interval (vs. full-options-scan's ~15-16 minutes), and this is a
    0DTE options desk - the owner wants current P/L, not a card that's
    stale for most of the time between full scans. upsert_channel_message
    hashes the rendered content and skips the Discord call when nothing
    actually changed, so this doesn't spam the API on every tick - it
    edits only when price movement actually changes what the card shows."""
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
        opened = spy_scanner.open_rows(rows)
    if not opened:
        stream_state = (
            "connected" if POSITION_STREAM and POSITION_STREAM.connected else "idle"
        )
        return f"no open positions; stream {stream_state}"
    timestamp = spy_scanner.now_ct()
    quotes = spy_scanner.get_quotes(
        spy_scanner.symbols_for_rows(opened), include_greeks=True
    )
    # SPY Key-Levels evaluates its stop/target off the underlying's own spot
    # price, not just the option premium - without this, evaluate_open_row
    # would report "SPY spot price unavailable" on every fast-path refresh
    # for any Key-Levels row (option quote alone isn't enough for it).
    spy_spot = spy_scanner.get_quote(spy_scanner.TICKER)
    underlying_spot_price = spy_scanner.as_float(spy_spot.get("last")) if spy_spot else None
    tracker = discord_tracker()
    report_state = spy_scanner.read_report_state() if tracker else {}
    closed = 0
    refreshed = 0
    live_updated = 0
    with POSITION_FILE_LOCK:
        for row in list(opened):
            evaluation = spy_scanner.evaluate_open_row(
                row, quotes, timestamp, underlying_spot_price=underlying_spot_price
            )
            if evaluation.get("pl_pct") is None:
                continue
            if evaluation.get("signal") in spy_scanner.CLOSING_SIGNALS:
                spy_scanner.close_row(row, evaluation, timestamp)
                _route_stream_close(row, evaluation, report_state if tracker else None)
                closed += 1
            else:
                row["current_pl_pct"] = spy_scanner.round_or_blank(
                    evaluation.get("pl_pct"), 1
                )
                row["current_pl_dollars"] = spy_scanner.round_or_blank(
                    evaluation.get("pl_dollars"), 0
                )
                if tracker:
                    before = report_state.get("message_hashes", {}).get(
                        f"position:updates:{row.get('trade_id', '')}"
                    )
                    spy_scanner.sync_open_trade_cards(row, tracker, report_state, evaluation)
                    after = report_state.get("message_hashes", {}).get(
                        f"position:updates:{row.get('trade_id', '')}"
                    )
                    if after != before:
                        live_updated += 1
            refreshed += 1
        if refreshed:
            spy_scanner.write_log(rows)
    if tracker:
        spy_scanner.write_report_state(report_state)
    # Flush the live-path counters so the exit path's real cost and latency
    # can be read from history instead of estimated. Written every
    # position-tracker cycle; cumulative since process start.
    _stats = dict(STREAM_STATS)
    _evals = _stats.get("evaluations") or 0
    _rel = _stats.get("relevant_ticks") or 0
    _stats["avg_eval_ms"] = round(
        (_stats.get("eval_seconds", 0.0) / _evals * 1000) if _evals else 0.0, 2)
    _stats["refetch_per_relevant_tick"] = round(
        (_stats.get("refetches", 0.0) / _rel) if _rel else 0.0, 3)
    store_observation(connection, "stream-stats",
                      {**_stats, "captured_at": iso_now()})

    stream_connected = bool(POSITION_STREAM and POSITION_STREAM.connected)
    stream_state = "connected" if stream_connected else "fallback"
    stream_error = (POSITION_STREAM.last_error if POSITION_STREAM else "") or ""
    # "connected" alone hid a socket dropping every ~90s: it reads True
    # again as soon as the reconnect lands, so 20/20 polls said connected
    # while tick counts showed real gaps (+4 and +14 in cycles that
    # otherwise ran +500). These fields make the churn visible.
    stream_health = POSITION_STREAM.health() if POSITION_STREAM else {}
    store_observation(
        connection,
        "position-tracker",
        {
            "open": len(opened) - closed,
            "closed": closed,
            "refreshed": refreshed,
            "live_updated": live_updated,
            "stream": stream_state,
            "stream_error": stream_error,
            **{f"stream_{k}": v for k, v in stream_health.items()},
        },
    )
    return f"{refreshed} refreshed · {closed} closed · {live_updated} live card update(s) · stream {stream_state}"


def closed_position_cleanup_job(connection: sqlite3.Connection) -> str:
    """Keep completed trades out of held-positions without running a market scan."""
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
    closed = spy_scanner.closed_rows(rows)
    if not closed:
        return "no closed trades to reconcile"
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    report_state = spy_scanner.read_report_state()
    pending = trade_intelligence.pending_rows(
        closed, ("journal", "result-channel")
    )
    journal_counts = spy_scanner.sync_all_trade_journals(pending, tracker)
    routed = spy_scanner.sync_closed_result_channels(pending, tracker, report_state)
    with POSITION_FILE_LOCK:
        spy_scanner.write_log(rows)
    spy_scanner.write_report_state(report_state)
    store_observation(
        connection,
        "closed-position-cleanup",
        {
            "closed_checked": len(closed),
            "changed_trades": len(pending),
            "results_routed": routed,
            "journals": journal_counts,
        },
    )
    for row in pending:
        trade_intelligence.record_event(
            row, "closed-reconciliation", str(row.get("closed_at") or row.get("trade_id")),
            extra={"results_routed": routed, "journals": journal_counts},
        )
    return f"{len(closed)} closed indexed; {len(pending)} changed; {routed} results routed"


def outcome_learning_job(connection: sqlite3.Connection) -> str:
    summary = outcome_learning.export_learning_archive()
    store_observation(
        connection,
        "outcome-learning",
        {
            "closed_trades": summary["closed_trades"],
            "evidence_ready_groups": len(summary["evidence_ready_groups"]),
            "generated_at": summary["generated_at"],
        },
    )
    tracker = discord_tracker()
    if tracker:
        report_state = spy_scanner.read_report_state()
        evidence = summary["evidence_ready_groups"]
        lines = [
            "## Learning Results",
            f"Closed trades analyzed **{summary['closed_trades']}** · "
            f"minimum sample **{summary['minimum_sample']}**",
            f"Learning Center version `{summary['learning_version']}`",
            "### Evidence-ready groups",
        ]
        if evidence:
            for item in evidence[:12]:
                lines.append(
                    f"**{item['feature']}: {item['value']}** — {item['samples']} trades · "
                    f"{item['win_rate_pct']:.0f}% wins · "
                    f"avg {spy_scanner.fmt_money(item['average_pl_dollars'])} · "
                    f"total {spy_scanner.fmt_money(item['total_pl_dollars'])}"
                )
        else:
            lines.append(
                "No group has reached the evidence threshold yet. Collection is active."
            )
        lines.extend([
            "### Guardrail",
            "Historical evidence only; this never changes scanner rules automatically.",
            f"Updated **{spy_scanner.portable_strftime(spy_scanner.now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
        ])
        tracker.upsert_channel_message(
            "learning_results",
            report_state,
            "learning-results",
            "\n".join(lines)[:2000],
        )
        spy_scanner.write_report_state(report_state)
    return (
        f"{summary['closed_trades']} closed trades; "
        f"{len(summary['evidence_ready_groups'])} evidence-ready groups"
    )


def discord_reporting_job(connection: sqlite3.Connection) -> str:
    """Refresh every result dashboard from the complete tracked trade history."""
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    report_state = spy_scanner.read_report_state()
    closed_rows = spy_scanner.closed_rows(rows)
    consumers = (
        "1m-performance", "1m-results", "5m-performance", "5m-results",
        "ticker-results", "wins-losses", "learning-results",
    )
    changed = trade_intelligence.pending_rows(closed_rows, consumers)
    # pending_rows() only ever reports rows it hasn't acknowledged yet, so a
    # trade-data reset (closed count drops, e.g. to zero) never shows up as
    # "changed" - there is nothing new to acknowledge - and the dashboards
    # would otherwise keep showing whatever totals were live before the
    # reset forever. Track the last-seen closed count so a drop still forces
    # a real refresh even when nothing is "pending" in the sync-ack sense.
    reset_detected = len(closed_rows) != int(report_state.get("last_closed_total", -1))
    if changed or reset_detected:
        spy_scanner.refresh_all_summary_dashboards(tracker, report_state, rows)
    report_state["last_closed_total"] = len(closed_rows)
    spy_scanner.sync_reports(
        tracker,
        report_state,
        rows,
        spy_scanner.now_ct(),
        market_open=spy_scanner.market_is_open_now()[0],
    )
    spy_scanner.write_report_state(report_state)
    if changed:
        outcome_learning_job(connection)
    acknowledged = (
        trade_intelligence.acknowledge_many(closed_rows, consumers) if changed else 0
    )
    closed = len(closed_rows)
    store_observation(
        connection, "discord-reporting",
        {"closed": closed, "changed_trades": len(changed), "synchronization_acknowledgements": acknowledged},
    )
    return f"daily/weekly refreshed; {closed} closed indexed; {len(changed)} changed; {acknowledged} aggregate acknowledgements committed"


def trade_intelligence_health_job(connection: sqlite3.Connection) -> str:
    health = trade_intelligence.health()
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
    closed = spy_scanner.closed_rows(rows)
    missing_learning = [row.get("trade_id") for row in rows if not row.get("learning_version")]
    missing_thesis = [row.get("trade_id") for row in rows if not row.get("thesis")]
    health.update({
        "canonical_trades": len(rows),
        "closed_trades": len(closed),
        "missing_learning_version": missing_learning,
        "missing_thesis": missing_thesis,
    })
    store_observation(connection, "trade-intelligence-health", health)
    if health["failed_syncs"] or missing_learning or missing_thesis:
        raise RuntimeError(f"trade intelligence incomplete: {health}")
    return (
        f"{len(rows)} trades checked; learning {health['learning_version']}; "
        f"{health['failed_syncs']} failed syncs; {health['pending_research']} research items awaiting review"
    )


def research_scoring_job(connection: sqlite3.Connection) -> str:
    counts = trade_intelligence.score_research_queue()
    store_observation(connection, "research-scoring", counts)
    return f"{counts['ready']} primary sources ready; {counts['needs_source']} headlines need original-source review"


def intelligence_retention_job(connection: sqlite3.Connection) -> str:
    result = trade_intelligence.apply_retention()
    store_observation(connection, "intelligence-retention", result)
    return f"{result['temporary_files_removed']} temporary files and {result['missing_pointers_removed']} stale pointers removed; canonical evidence preserved"




def discord_card_migration_job(connection: sqlite3.Connection) -> str:
    """Refresh a bounded set of legacy forum cards without delaying scans."""
    with POSITION_FILE_LOCK:
        rows = spy_scanner.read_log()
        pending = [
            dict(row)
            for row in spy_scanner.open_rows(rows)
            if row.get("discord_format_version") != spy_scanner.DISCORD_FORMAT_VERSION
        ][:5]
    if not pending:
        return "all open trade forum cards are current"
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    refreshed_ids: list[str] = []
    refreshed_threads: dict[str, str] = {}
    report_state = spy_scanner.read_report_state()
    for row in pending:
        if not row.get("discord_thread_id"):
            tracker.create_trade_thread(row, "OPEN")
        else:
            try:
                tracker.refresh_trade_thread(row)
            except spy_scanner.DiscordError as exc:
                if not spy_scanner.discord_route_is_missing(exc):
                    raise
                row["discord_thread_id"] = ""
                row["discord_status"] = ""
                row["discord_format_version"] = ""
                tracker.create_trade_thread(row, "OPEN")
        refreshed_ids.append(row.get("trade_id", ""))
        refreshed_threads[row.get("trade_id", "")] = row.get("discord_thread_id", "")
        spy_scanner.sync_open_trade_cards(
            row,
            tracker,
            report_state,
            spy_scanner.stored_open_evaluation(row),
            include_entry=True,
        )
        time.sleep(1.0)
    with POSITION_FILE_LOCK:
        latest = spy_scanner.read_log()
        refreshed = set(refreshed_ids)
        for row in latest:
            if row.get("trade_id") in refreshed:
                row["discord_thread_id"] = refreshed_threads.get(
                    row.get("trade_id", ""), row.get("discord_thread_id", "")
                )
                row["discord_format_version"] = spy_scanner.DISCORD_FORMAT_VERSION
        spy_scanner.write_log(latest)
    spy_scanner.write_report_state(report_state)
    store_observation(
        connection,
        "discord-card-migration",
        {"refreshed": refreshed_ids, "remaining_before_run": len(pending)},
    )
    return f"refreshed {len(refreshed_ids)} legacy forum card(s)"


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
        "position-tracker",
        timedelta(seconds=POSITION_SAFETY_POLL_SECONDS),
        position_tracker_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
    ),
    Job(
        "closed-position-cleanup",
        timedelta(minutes=5),
        closed_position_cleanup_job,
        retry_interval=timedelta(minutes=1),
    ),
    Job(
        "discord-reporting",
        timedelta(minutes=5),
        discord_reporting_job,
        retry_interval=timedelta(minutes=1),
    ),
    Job(
        "trade-intelligence-health",
        timedelta(minutes=5),
        trade_intelligence_health_job,
        retry_interval=timedelta(minutes=1),
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
        "managed-ticker-information",
        timedelta(minutes=60),
        managed_ticker_information_job,
        after_hours_interval=timedelta(hours=4),
        background=True,
        provider_heavy=True,
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
        "managed-ticker-news",
        timedelta(hours=2),
        managed_ticker_news_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=15),
    ),
    Job(
        "session-briefing",
        timedelta(minutes=10),
        briefing_job,
        background=True,
        provider_heavy=True,
    ),
    Job("health-snapshot", timedelta(minutes=STATUS_REFRESH_MINUTES), status_job),
    Job("weekly-review", timedelta(minutes=30), weekly_review_job),
    Job(
        "outcome-learning",
        timedelta(hours=6),
        outcome_learning_job,
    ),
    Job(
        "discord-card-migration",
        timedelta(minutes=5),
        discord_card_migration_job,
        background=True,
        provider_heavy=True,
        retry_interval=timedelta(minutes=5),
    ),
    Job(
        "backtest-cards",
        timedelta(hours=6),
        backtest_cards_job,
        background=True,
        retry_interval=timedelta(minutes=30),
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
    Job(
        "new-strategy-entry-scan",
        timedelta(minutes=1),
        new_strategy_entry_scan_job,
        market_hours_only=True,
        background=True,
        # Deliberately NOT provider_heavy. That lock serialises the heavy
        # jobs so they cannot stampede the provider, and full-options-scan
        # holds it for a median 38s, p90 128s and up to 369s. Queueing a
        # 3-call job behind a 6-minute one skips ~6 cycles, which overruns
        # the 2-bar lookback and loses exactly the signals this job exists
        # to catch. A normal cycle is three requests (quote, intraday,
        # daily) and only spends more when a signal actually fires; 429s
        # already retry with backoff.
        retry_interval=timedelta(minutes=1),
    ),
    Job(
        "full-options-scan",
        timedelta(minutes=15),
        full_scanner_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
    ),
    Job(
        "system-digest",
        timedelta(hours=24),
        system_digest_job,
        background=True,
        retry_interval=timedelta(hours=1),
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
        market_open, _ = spy_scanner.market_is_open_now()
        return market_open
    return True


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
    connection.execute(
        "UPDATE job_runs SET finished_at=?, status=?, detail=? WHERE id=?",
        (iso_now(), status, detail, cursor.lastrowid),
    )
    set_state(connection, f"job:{job.name}", utc_now().isoformat())
    set_state(connection, f"job-error:{job.name}", "1" if status == "ERROR" else "0")
    connection.commit()
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
    global POSITION_STREAM
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
    POSITION_STREAM = tradier_stream.TradierPositionStream(
        spy_scanner.TRADIER_TOKEN,
        spy_scanner.TRADIER_BASE_URL,
        _position_symbols,
        _stream_quote_event,
    )
    threading.Thread(
        target=POSITION_STREAM.run_forever,
        name="tradier-position-stream",
        daemon=True,
    ).start()
    print(
        "Open paper positions use one live Tradier quote stream; "
        "REST checks are a one-minute safety fallback."
    )
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
