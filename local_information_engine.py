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

import ford_scan
import dynamic_universe
import multi_ticker_scan
import outcome_learning
import requests
import ticker_registry
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
    os.environ.get("POSITION_SAFETY_POLL_SECONDS", "300")
)
FORD_NEWS_URL = "https://shareholder.ford.com/news/default.aspx"
FORD_NEWS_FEED_URL = (
    "https://shareholder.ford.com/feed/PressRelease.svc/GetPressReleaseList"
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
POSITION_STREAM: tradier_stream.TradierPositionStream | None = None


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
        high = ford_scan.as_float(day.get("high"))
        low = ford_scan.as_float(day.get("low"))
        close = ford_scan.as_float(day.get("close"))
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


def market_snapshot(symbol: str = ford_scan.TICKER) -> dict[str, Any]:
    quote = ford_scan.get_quote(symbol) or {}
    history = ford_scan.get_daily_history(symbol, days=400)
    spot = ford_scan.as_float(quote.get("last"))
    if spot is None or not history:
        raise ford_scan.TradierError(f"{symbol} quote or price history is unavailable")
    try:
        intraday = ford_scan.get_intraday_history(symbol)
    except (ford_scan.TradierError, requests.RequestException):
        intraday = []
    closes = [
        value
        for day in history
        if (value := ford_scan.as_float(day.get("close"))) is not None
    ]
    volumes = [
        value
        for day in history
        if (value := ford_scan.as_float(day.get("volume"))) is not None
    ]
    context = ford_scan.directional_market_context(history, spot, intraday)
    ema12 = exponential_moving_average(closes, 12)
    ema26 = exponential_moving_average(closes, 26)
    macd = ema12 - ema26 if ema12 is not None and ema26 is not None else None
    std20 = standard_deviation(closes[-20:])
    sma20 = ford_scan.simple_moving_average(closes, 20)
    bollinger_upper = sma20 + 2 * std20 if sma20 is not None and std20 is not None else None
    bollinger_lower = sma20 - 2 * std20 if sma20 is not None and std20 is not None else None
    atr14 = average_true_range(history)
    average_volume20 = ford_scan.simple_moving_average(volumes, 20)
    current_volume = ford_scan.as_float(quote.get("volume"))
    relative_volume = (
        current_volume / average_volume20
        if current_volume is not None and average_volume20
        else context.get("volume_ratio")
    )
    previous_close = ford_scan.as_float(quote.get("prevclose"))
    change_pct = (
        (spot / previous_close - 1) * 100 if previous_close and previous_close > 0 else None
    )
    bid = ford_scan.as_float(quote.get("bid"))
    ask = ford_scan.as_float(quote.get("ask"))
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
        "sma200": ford_scan.simple_moving_average(closes, 200),
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
        "day_high": ford_scan.as_float(quote.get("high")),
        "day_low": ford_scan.as_float(quote.get("low")),
        "history": history,
    }


def option_quality(option: dict[str, Any], spot: float) -> dict[str, Any]:
    bid = ford_scan.as_float(option.get("bid"), 0.0) or 0.0
    ask = ford_scan.as_float(option.get("ask"), 0.0) or 0.0
    mid = (bid + ask) / 2 if bid > 0 and ask >= bid else None
    width = ask - bid if ask >= bid else None
    width_pct = width / mid if width is not None and mid else None
    oi = ford_scan.open_interest_value(option)
    volume = ford_scan.option_volume_value(option)
    delta = ford_scan.greek(option, "delta")
    theta = ford_scan.greek(option, "theta")
    iv = ford_scan.iv_value(option)
    strike = ford_scan.as_float(option.get("strike"))
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
        oi >= ford_scan.MIN_OPEN_INTEREST
        and volume >= ford_scan.MIN_OPTION_VOLUME
        and width_pct is not None
        and width_pct <= ford_scan.MAX_BID_ASK_PCT
    )
    score = 0.0
    score += min(oi / max(ford_scan.MIN_OPEN_INTEREST, 1), 5) * 10
    score += min(volume / max(ford_scan.MIN_OPTION_VOLUME, 1), 5) * 8
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
    symbol: str = ford_scan.TICKER,
) -> list[dict[str, Any]]:
    spot_quote = ford_scan.get_quote(symbol) or {}
    spot = ford_scan.as_float(spot_quote.get("last"))
    if spot is None:
        raise ford_scan.TradierError("Ford spot price is unavailable")
    expirations = ford_scan.get_expirations(symbol)
    if expiration is None:
        _, swing = ford_scan.pick_expirations(expirations, ford_scan.now_ct().date())
        expiration = swing[0] if swing else next(iter(expirations), None)
    if not expiration:
        return []
    chain = ford_scan.get_chain(symbol, expiration)
    ranked = [
        option_quality(option, spot)
        for option in chain
        if str(option.get("option_type") or "").lower() == side.lower()
    ]
    ranked = [
        item
        for item in ranked
        if item["strike"] is not None
        and abs(float(item["strike"]) / spot - 1) <= ford_scan.STRIKE_BAND_PCT
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
    option = ford_scan.get_quotes([symbol], include_greeks=True).get(symbol)
    underlying = str(
        (option or {}).get("root_symbol")
        or (option or {}).get("underlying")
        or ford_scan.TICKER
    ).upper()
    spot_quote = ford_scan.get_quote(underlying) or {}
    spot = ford_scan.as_float(spot_quote.get("last"))
    if not option or spot is None:
        return None
    return option_quality(option, spot)


def performance_snapshot(ticker: str | None = None) -> dict[str, Any]:
    rows = ford_scan.read_log()
    if ticker:
        rows = [
            row for row in rows
            if str(row.get("ticker") or "F").upper() == ticker.upper()
        ]
    closed = ford_scan.closed_rows(rows)
    metrics = ford_scan.result_metrics(closed)
    open_count = len(ford_scan.open_rows(rows))
    strategy: dict[str, dict[str, float]] = {}
    for row in closed:
        key = row.get("play_type") or "UNKNOWN"
        bucket = strategy.setdefault(key, {"count": 0, "wins": 0, "pl": 0.0})
        bucket["count"] += 1
        bucket["wins"] += 1 if row.get("outcome") == "WIN" else 0
        bucket["pl"] += ford_scan.realized_pl_dollars(row)
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


def market_alert_text(snapshot: dict[str, Any], ticker: str = "F") -> str:
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


def discord_tracker() -> ford_scan.DiscordTracker | None:
    if not ford_scan.DISCORD_BOT_TOKEN or not ford_scan.DISCORD_GUILD_ID:
        return None
    tracker = ford_scan.initialize_discord()
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


def upsert_ticker_dashboard(
    connection: sqlite3.Connection,
    ticker: str,
    channel_key: str,
    card_key: str,
    content: str,
) -> bool:
    item = ticker_registry.get(ticker)
    channel_id = str((item or {}).get("channels", {}).get(channel_key) or "")
    tracker = discord_tracker()
    if not tracker or not channel_id:
        return False
    state_name = "dynamic_ticker_discord_state"
    try:
        state = json.loads(get_state(connection, state_name, "{}"))
    except json.JSONDecodeError:
        state = {}
    messages = state.setdefault("messages", {})
    state_key = f"{ticker}:{channel_key}:{card_key}"
    message_id = str(messages.get(state_key) or "")
    payload = {
        "content": "",
        "embeds": [ford_scan.discord_card(content[:6000])],
        "allowed_mentions": {"parse": []},
    }
    if message_id:
        try:
            tracker._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
        except ford_scan.DiscordError as exc:
            if "HTTP 404" not in str(exc):
                raise
            message_id = ""
    if not message_id:
        created = tracker._request("POST", f"/channels/{channel_id}/messages", payload)
        message_id = str((created or {}).get("id") or "")
        if message_id:
            messages[state_key] = message_id
    set_state(connection, state_name, json.dumps(state))
    return bool(message_id)


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
    today = ford_scan.now_ct().date().isoformat()
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
        headers={"User-Agent": ford_scan.SEC_USER_AGENT or "Tradysquids local monitor"},
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
    return bool(ford_scan.market_is_open_now()[0])


def technicals_text(snapshot: dict[str, Any], ticker: str = "F") -> str:
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


def market_pulse_text(snapshot: dict[str, Any], ticker: str = "F") -> str:
    session = "live" if market_is_open() else "closed; showing the latest available quote"
    return (
        "## Tradysquids Market Pulse\n"
        f"Market is **{session}**.\n"
        + market_alert_text(snapshot, ticker).replace(f"## {ticker} Local Market Monitor\n", "")
    )


def options_dashboard_text(
    snapshot: dict[str, Any], options: list[dict[str, Any]], ticker: str = "F"
) -> str:
    lines = [
        "## Tradysquids Options Chain",
        (
            "**Live scan**" if market_is_open()
            else "**Market closed — quotes are the last available snapshot, not tradable prices.**"
        ),
        f"{ticker} spot **${float(snapshot['price']):.2f}** · ranked for liquidity and conservative delta.",
    ]
    if not options:
        lines.append("No contract currently passes the available chain filters.")
    for item in options[:5]:
        delta = item.get("delta")
        if delta is None:
            lines.append(f"• `{item.get('symbol')}` · Greeks unavailable")
            continue
        width = item.get("width_pct")
        width_text = "n/a" if width is None else f"{float(width) * 100:.1f}%"
        lines.append(
            f"• `{item.get('symbol')}` · ${float(item.get('strike') or 0):.2f} "
            f"· bid/ask ${float(item.get('bid') or 0):.2f}/${float(item.get('ask') or 0):.2f} "
            f"· Δ {float(delta):.2f} · OI {int(item.get('open_interest') or 0)} "
            f"· vol {int(item.get('volume') or 0)} · spread {width_text} "
            f"· {'LIQUIDITY PASS' if item.get('liquidity_pass') else 'LIQUIDITY WATCH'}"
        )
    lines.extend([
        f"Updated {snapshot.get('observed_at')}.",
        "Liquidity status is not a full trade qualification. Ranking is informational, not a recommendation or guarantee.",
    ])
    return "\n".join(lines)


def fetch_ford_news() -> list[dict[str, str]]:
    response = requests.get(
        FORD_NEWS_FEED_URL,
        params={
            "languageId": 1,
            "bodyType": 0,
            "pressReleaseDateFilter": 3,
            "categoryId": "",
            "includeTags": "true",
            "pageSize": 20,
            "pageNumber": 0,
            "tagList": "",
        },
        headers={"User-Agent": ford_scan.SEC_USER_AGENT or "Tradysquids local monitor"},
        timeout=25,
    )
    response.raise_for_status()
    rows = response.json().get("GetPressReleaseListResult") or []
    items = []
    for row in rows:
        title = " ".join(str(row.get("Headline") or "").split())
        href = str(row.get("LinkToDetailPage") or row.get("LinkToUrl") or "")
        if not title or not href:
            continue
        items.append({
            "id": str(row.get("PressReleaseId") or hashlib.sha256(href.encode()).hexdigest()[:20]),
            "title": title,
            "url": urljoin(FORD_NEWS_URL, href),
            "date": str(row.get("PressReleaseDate") or ""),
        })
    return items


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
    elif ford_scan.DISCORD_WEBHOOK_URL:
        response = requests.post(
            ford_scan.DISCORD_WEBHOOK_URL,
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


def market_job(connection: sqlite3.Connection) -> str:
    snapshot = market_snapshot()
    store_observation(
        connection,
        "market",
        {key: value for key, value in snapshot.items() if key != "history"},
    )
    previous_regime = get_state(connection, "last_regime")
    previous_price = ford_scan.as_float(get_state(connection, "last_price"))
    price = float(snapshot["price"])
    regime_changed = bool(previous_regime and previous_regime != snapshot["regime"])
    level_cross = False
    if previous_price is not None:
        level_cross = (
            previous_price < snapshot["resistance20"] <= price
            or previous_price > snapshot["support20"] >= price
        )
    unusual_volume = (snapshot.get("relative_volume") or 0) >= 1.75
    if regime_changed or level_cross or unusual_volume:
        reason = []
        if regime_changed:
            reason.append(f"regime changed from {previous_regime} to {snapshot['regime']}")
        if level_cross:
            reason.append("price crossed a tracked 20-day level")
        if unusual_volume:
            reason.append("relative volume reached at least 1.75x")
        publish_change_only(
            connection,
            "material-market-change",
            market_alert_text(snapshot) + "\n**Alert reason:** " + "; ".join(reason),
            minimum_minutes=15,
        )
    set_state(connection, "last_regime", str(snapshot["regime"]))
    set_state(connection, "last_price", str(price))
    upsert_dashboard(connection, "market_pulse", "market-pulse", market_pulse_text(snapshot))
    upsert_dashboard(connection, "technicals", "technicals", technicals_text(snapshot))
    upsert_dashboard(
        connection,
        "research_summary",
        "research-summary",
        "\n".join([
            "## Tradysquids Research Summary",
            f"Current regime: **{snapshot.get('regime')}** · qualified: **{'yes' if snapshot.get('qualified') else 'no'}**",
            f"System read: {snapshot.get('reason') or 'No controlled setup.'}",
            "Tracked failures: " + (", ".join(snapshot.get("failures") or []) or "none"),
            f"Updated {snapshot.get('observed_at')}. This is evidence tracking, not financial advice.",
        ]),
    )
    return f"F ${price:.2f} · {snapshot['regime']}"


def options_job(connection: sqlite3.Connection) -> str:
    market = latest_observation("market")
    snapshot = market["payload"] if market else market_snapshot()
    options = ranked_option_chain("call", limit=8)
    store_observation(connection, "options-chain", {"options": options})
    upsert_dashboard(
        connection,
        "options_chain",
        "options-chain",
        options_dashboard_text(snapshot, options),
    )
    risk_lines = [
        "## Tradysquids Risk Desk",
        "The scanner does not remove risk and does not guarantee a profitable trade.",
        f"Ford regime: **{snapshot.get('regime')}** · ATR14 **${float(snapshot.get('atr14') or 0):.2f}**.",
        "Only consider contracts that pass configured liquidity, spread, DTE, and delta rules.",
        "Avoid chasing entries, use a defined maximum loss, and verify quotes before any order.",
        (
            f"Best current liquidity candidate: `{options[0].get('symbol')}` "
            f"({'passes' if options[0].get('liquidity_pass') else 'does not pass'} rules)."
            if options else "No eligible contract is available."
        ),
        f"Updated {iso_now()}. Educational information only.",
    ]
    upsert_dashboard(connection, "risk_desk", "risk-desk", "\n".join(risk_lines))
    return f"{len(options)} ranked calls"


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
            ford_scan.render_market_chart_png(
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
                    f"{ticker} daily market chart · {ford_scan.now_ct().date().isoformat()} "
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
                    f"RSI14: **{snapshot.get('rsi14')}** · ATR14: **{ford_scan.fmt_money(snapshot.get('atr14'))}**",
                    f"Support: **{ford_scan.fmt_money(snapshot.get('support20'))}** · resistance: **{ford_scan.fmt_money(snapshot.get('resistance20'))}**",
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


def news_job(connection: sqlite3.Connection) -> str:
    try:
        items = fetch_ford_news()
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 429:
            raise
        cached = latest_observation("news")
        items = list((cached or {}).get("payload", {}).get("items") or [])
        if not items:
            raise
        upsert_dashboard(
            connection,
            "news_events",
            "news-digest",
            "\n".join([
                "## Tradysquids Ford News & Events",
                f"Official source: [Ford Investor Relations]({FORD_NEWS_URL})",
                *[f"• [{item['title']}]({item['url']})" for item in items[:8]],
                (
                    f"Ford temporarily rate-limited this check at {iso_now()}; "
                    "showing the last successful official results. The next scheduled check will retry."
                ),
            ]),
        )
        return f"Ford rate limited request · using {len(items)} cached official items"
    previous_raw = get_state(connection, "seen_news", "")
    previous = set(json.loads(previous_raw or "[]"))
    fresh = [item for item in items if item["id"] not in previous]
    if not previous_raw:
        fresh = []
    store_observation(connection, "news", {"items": items, "new": fresh})
    for item in reversed(fresh[:5]):
        publish_change_only(
            connection,
            f"ford-news:{item['id']}",
            "\n".join([
                "## New official Ford news",
                f"**[{item['title']}]({item['url']})**",
                "News can move price outside market hours; trading availability is separate.",
                "Review the source before treating it as material. Educational information only.",
            ]),
            logical_channel="news_events",
            minimum_minutes=0,
        )
    digest = [
        "## Tradysquids Ford News & Events",
        f"Official source: [Ford Investor Relations]({FORD_NEWS_URL})",
    ]
    digest.extend(f"• [{item['title']}]({item['url']})" for item in items[:8])
    digest.append(f"Checked {iso_now()}. New items are posted once; this digest updates in place.")
    upsert_dashboard(connection, "news_events", "news-digest", "\n".join(digest))
    set_state(connection, "seen_news", json.dumps([item["id"] for item in items]))
    return f"{len(items)} official items · {len(fresh)} new"


def filings_job(connection: sqlite3.Connection) -> str:
    filings = ford_scan.fetch_recent_ford_filings()
    previous = set(json.loads(get_state(connection, "seen_filings", "[]")))
    fresh = [item for item in filings if item["id"] not in previous]
    store_observation(connection, "filings", {"filings": filings, "new": fresh})
    if fresh:
        lines = ["## New Ford SEC filing"]
        for filing in fresh[:5]:
            lines.append(
                f"**{filing['date']} · {filing['form']}** · [Open filing]({filing['url']})"
            )
        lines.append(
            "A filing is an information event, not an automatic trade signal."
        )
        publish_change_only(
            connection,
            f"filings:{fresh[0]['id']}",
            "\n".join(lines),
            logical_channel="sec_filings",
            minimum_minutes=0,
        )
    digest = ["## Tradysquids SEC Filing Monitor"]
    digest.extend(
        f"• **{item['date']} · {item['form']}** · [Open filing]({item['url']})"
        for item in filings[:8]
    )
    digest.append(f"Checked {iso_now()}. New filings are posted once; this digest updates in place.")
    upsert_dashboard(connection, "sec_filings", "sec-filings", "\n".join(digest))
    set_state(connection, "seen_filings", json.dumps([item["id"] for item in filings]))
    return f"{len(filings)} recent · {len(fresh)} new"


def status_job(connection: sqlite3.Connection) -> str:
    market = latest_observation("market")
    status = {
        "engine": "online",
        "updated_at": iso_now(),
        "market_data_age": data_age_text(market["observed_at"] if market else None),
        "tradier_configured": bool(ford_scan.TRADIER_TOKEN),
        "discord_scheduled_posts": bool(
            (ford_scan.DISCORD_BOT_TOKEN and ford_scan.DISCORD_GUILD_ID)
            or ford_scan.DISCORD_WEBHOOK_URL
        ),
        "sec_monitor": bool(ford_scan.SEC_USER_AGENT),
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
            f"**SEC monitor:** {'configured' if status['sec_monitor'] else 'missing'}",
            f"Updated {status['updated_at']}. This private card updates in place.",
        ]),
    )
    return json.dumps(status, separators=(",", ":"))


def briefing_job(connection: sqlite3.Connection) -> str:
    now = ford_scan.now_ct()
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
    quotes = ford_scan.get_quotes(symbols, include_greeks=False) if symbols else {}
    ranked = sorted(
        symbols,
        key=lambda symbol: ford_scan.as_float((quotes.get(symbol) or {}).get("volume"), 0) or 0,
        reverse=True,
    )
    lines = [
        f"## Tradysquids {session.replace('-', ' ').title()} Briefing",
        f"**{len(symbols)} active universe symbols** · {ford_scan.portable_strftime(now, '%m/%d/%y %-I:%M %p CT')}",
        "### Highest-Volume Universe Names",
    ]
    for symbol in ranked[:12]:
        quote = quotes.get(symbol) or {}
        price = ford_scan.as_float(quote.get("last"))
        change = ford_scan.as_float(quote.get("change_percentage"))
        volume = int(ford_scan.as_float(quote.get("volume"), 0) or 0)
        change_text = "n/a" if change is None else f"{change:+.2f}%"
        lines.append(
            f"• **{symbol}** · {ford_scan.fmt_money(price)} · {change_text} · volume {volume:,}"
        )
    lines.extend([
        "### Broad Market Regime",
    ])
    benchmark_payload: dict[str, Any] = {}
    for benchmark in ("SPY", "QQQ"):
        try:
            snapshot = market_snapshot(benchmark)
            benchmark_payload[benchmark] = {
                key: value for key, value in snapshot.items() if key != "history"
            }
            lines.append(
                f"• **{benchmark}** {ford_scan.fmt_money(snapshot.get('price'))} · "
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
    now = ford_scan.now_ct()
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
            f"recorded P/L {ford_scan.fmt_money(metrics.get('total_pnl'))}"
        ),
        "Review recorded evidence and filter quality before changing strategy rules.",
        "Historical results do not guarantee future performance.",
    ])
    sent = publish_change_only(
        connection,
        key,
        content,
        logical_channel="performance_stats",
        minimum_minutes=0,
    )
    if sent:
        set_state(connection, key, "sent")
    return f"weekly review {'sent' if sent else 'stored locally'}"


def full_scanner_job(connection: sqlite3.Connection) -> str:
    if not FULL_SCAN_ENABLED:
        return "disabled until LOCAL_FULL_SCAN_ENABLED=true"
    if not ford_scan.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"
    tickers = multi_ticker_scan.configured_active_tickers()
    with POSITION_FILE_LOCK:
        result = multi_ticker_scan.main(tickers)
    results = dict(multi_ticker_scan.LAST_RESULTS)
    store_observation(
        connection,
        "full-scan",
        {"results": results, "completed_at": iso_now()},
    )
    failed = [ticker for ticker, ticker_result in results.items() if ticker_result]
    if failed:
        raise RuntimeError(f"Scanner failed for: {', '.join(failed)}")
    if result:
        raise RuntimeError("Scanner returned failure without per-ticker results")
    return f"Options scan completed for {', '.join(results) or 'no active tickers'}"


def manual_options_scan_job(connection: sqlite3.Connection) -> str:
    """Scan every currently active symbol instead of the scheduled rotating batch."""
    if not FULL_SCAN_ENABLED:
        return "disabled until LOCAL_FULL_SCAN_ENABLED=true"
    if not ford_scan.DISCORD_BOT_TOKEN:
        return "waiting for local DISCORD_BOT_TOKEN"
    tickers = dynamic_universe.active_symbols()
    with POSITION_FILE_LOCK:
        result = multi_ticker_scan.main(tickers)
    results = dict(multi_ticker_scan.LAST_RESULTS)
    store_observation(
        connection,
        "manual-full-scan",
        {"results": results, "completed_at": iso_now()},
    )
    failed = [ticker for ticker, exit_code in results.items() if exit_code]
    if failed:
        raise RuntimeError(f"Scanner failed for: {', '.join(failed)}")
    if result:
        raise RuntimeError("Scanner returned failure without per-ticker results")
    market_open, _ = ford_scan.market_is_open_now()
    session = "live option chains" if market_open else "market-closed routing checks"
    return (
        f"{len(tickers)} active tickers processed using {session}: "
        f"{', '.join(tickers) or 'none'}"
    )


def manual_intelligence_job(connection: sqlite3.Connection) -> str:
    """Publish a timestamped broad-market and universe snapshot on demand."""
    symbols = dynamic_universe.active_symbols()
    quotes = ford_scan.get_quotes(symbols, include_greeks=False) if symbols else {}
    tracker = discord_tracker()
    if not tracker:
        return "Discord tracker is unavailable"
    observed_at = iso_now()
    market_open, _ = ford_scan.market_is_open_now()
    session = "MARKET OPEN" if market_open else "MARKET CLOSED / LAST QUOTES"

    ranked = sorted(
        symbols,
        key=lambda symbol: ford_scan.as_float((quotes.get(symbol) or {}).get("volume"), 0)
        or 0,
        reverse=True,
    )
    universe_lines = [
        "## Manual Universe Discovery",
        f"**{session}** · **{len(symbols)} active symbols**",
    ]
    for symbol in ranked[:30]:
        quote = quotes.get(symbol) or {}
        price = ford_scan.as_float(quote.get("last"))
        volume = int(ford_scan.as_float(quote.get("volume"), 0) or 0)
        universe_lines.append(
            f"• **{symbol}** · "
            f"{ford_scan.fmt_money(price) if price is not None else 'quote unavailable'} "
            f"· volume {volume:,}"
        )
    if len(ranked) > 30:
        universe_lines.append(f"• …and {len(ranked) - 30} more active symbols")
    universe_lines.append(
        f"Updated {observed_at}. Discovery ranking is informational only."
    )
    tracker.send_channel("universe_watch", content="\n".join(universe_lines))

    benchmark_lines = [
        "## Manual Market-Regime Snapshot",
        f"**{session}**",
    ]
    for benchmark in ("SPY", "QQQ"):
        try:
            snapshot = market_snapshot(benchmark)
            benchmark_lines.append(
                f"• **{benchmark}** {ford_scan.fmt_money(snapshot['price'])} · "
                f"{snapshot['regime']} · RSI {float(snapshot.get('rsi14') or 0):.1f} · "
                f"support {ford_scan.fmt_money(snapshot.get('support20'))} · "
                f"resistance {ford_scan.fmt_money(snapshot.get('resistance20'))}"
            )
        except Exception as exc:
            benchmark_lines.append(
                f"• **{benchmark}** unavailable · {type(exc).__name__}"
            )
    benchmark_lines.append(
        f"Updated {observed_at}. Conditions are not an automatic trade entry."
    )
    tracker.send_channel("intelligence", content="\n".join(benchmark_lines))

    tracker.send_channel(
        "premarket",
        content="\n".join([
            "## Manual Session Briefing",
            f"**{session}**",
            f"Universe refreshed: **{len(symbols)} symbols**.",
            f"Highest current stock-volume names: **{', '.join(ranked[:10]) or 'none'}**.",
            "The options scanner reports each ticker separately in #scanner-feed.",
            f"Generated {observed_at}. Quotes may be stale while markets are closed.",
        ]),
    )

    headlines: list[str] = []
    for symbol in ranked[:8]:
        try:
            items = fetch_ticker_news(symbol, limit=1)
            if items:
                headlines.append(
                    f"• **{symbol}** · [{items[0]['title']}]({items[0]['url']})"
                )
        except Exception:
            continue
    tracker.send_channel(
        "news_events",
        content="\n".join([
            "## Manual News and Events Digest",
            *(headlines or ["No current headlines were returned by the public feed."]),
            f"Checked {observed_at}. Verify original sources before acting.",
        ]),
    )
    store_observation(
        connection,
        "manual-intelligence",
        {"symbols": symbols, "ranked": ranked, "observed_at": observed_at},
    )
    return (
        f"market regime, session briefing, universe watch, and "
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
    allowed = {"all", "discovery", "options", "intelligence", "positions", "health"}
    if normalized not in allowed:
        raise ValueError(f"Unknown manual scan scope: {normalized}")
    if not MANUAL_SCAN_LOCK.acquire(blocking=False):
        raise RuntimeError("Another manual scan is already running.")
    try:
        connection = connect_db()
        try:
            steps = {
                "discovery": [
                    ("provider events", provider_event_job),
                    ("universe discovery", universe_refresh_job),
                ],
                "options": [("options scanner", manual_options_scan_job)],
                "intelligence": [("market intelligence", manual_intelligence_job)],
                "positions": [("open positions", position_tracker_job)],
                "health": [("system health", status_job)],
            }
            selected = (
                [
                    *steps["discovery"],
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


def provider_event_job(connection: sqlite3.Connection) -> str:
    events = dynamic_universe.claim_events(limit=25)
    completed = 0
    for event in events:
        try:
            dynamic_universe.upsert_candidates([
                dynamic_universe.Candidate(
                    event["symbol"],
                    event["provider"],
                    score=100 + float(event["priority"]),
                    reason=f"{event['provider']} {event['event_type']}",
                    ttl_minutes=240,
                )
            ])
            store_observation(
                connection,
                f"provider-event:{event['provider']}",
                {
                    "symbol": event["symbol"],
                    "event_type": event["event_type"],
                    "payload": event["payload"],
                },
            )
            dynamic_universe.complete_event(event["id"])
            completed += 1
        except Exception as exc:
            dynamic_universe.complete_event(event["id"], error=str(exc))
    return f"{completed}/{len(events)} provider events processed"


def universe_refresh_job(connection: sqlite3.Connection) -> str:
    """Refresh stock liquidity for the full universe in one batched quote call."""
    symbols = dynamic_universe.initialize()
    if not symbols:
        return "empty universe"
    quotes = ford_scan.get_quotes(symbols, include_greeks=False)
    candidates: list[dynamic_universe.Candidate] = []
    for symbol in symbols:
        quote = quotes.get(symbol) or {}
        price = ford_scan.as_float(quote.get("last"))
        volume = ford_scan.as_float(quote.get("volume"))
        if price is None:
            continue
        score = min((volume or 0) / 1_000_000, 20) * 5
        candidates.append(dynamic_universe.Candidate(
            symbol,
            "tradier_liquidity",
            score=score,
            last_price=price,
            average_volume=volume,
            reason="batched Tradier liquidity refresh",
            ttl_minutes=180,
        ))
    updated = dynamic_universe.upsert_candidates(candidates)
    store_observation(
        connection,
        "universe-refresh",
        {"symbols": len(symbols), "updated": updated, "at": iso_now()},
    )
    return f"{updated}/{len(symbols)} universe quotes refreshed"


def _route_stream_close(
    row: dict[str, str], evaluation: dict[str, Any]
) -> None:
    tracker = discord_tracker()
    if not tracker:
        return
    report_state = ford_scan.read_report_state()
    ford_scan.post_close(row, evaluation, tracker, report_state)
    rows = ford_scan.read_log()
    ford_scan.update_performance_pages(tracker, report_state, rows)
    ford_scan.sync_reports(
        tracker,
        report_state,
        rows,
        ford_scan.now_ct(),
        market_open=ford_scan.market_is_open_now()[0],
    )
    ford_scan.write_report_state(report_state)


def _position_symbols() -> list[str]:
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
        return ford_scan.symbols_for_rows(ford_scan.open_rows(rows))


def _stream_quote_event(event: dict[str, Any]) -> None:
    """Evaluate exits immediately when a streamed option quote changes."""
    symbol = str(event.get("symbol") or "")
    if not symbol or not ford_scan.market_is_open_now()[0]:
        return
    STREAM_QUOTES.setdefault(symbol, {}).update(event)
    timestamp = ford_scan.now_ct()
    now_monotonic = time.monotonic()
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
        changed = False
        closed_events: list[tuple[dict[str, str], dict[str, Any]]] = []
        for row in ford_scan.open_rows(rows):
            required = set(ford_scan.symbols_for_rows([row]))
            option_symbols = required - {row.get("ticker", "")}
            if symbol not in option_symbols or not option_symbols.issubset(STREAM_QUOTES):
                continue
            evaluation = ford_scan.evaluate_open_row(row, STREAM_QUOTES, timestamp)
            if evaluation.get("pl_pct") is None:
                continue
            signal = evaluation.get("signal")
            if signal in {"STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE"}:
                ford_scan.close_row(row, evaluation, timestamp)
                closed_events.append((row, evaluation))
                changed = True
            else:
                trade_id = row.get("trade_id", "")
                last_write = STREAM_LAST_WRITTEN.get(trade_id, 0.0)
                if now_monotonic - last_write >= 2:
                    STREAM_LAST_WRITTEN[trade_id] = now_monotonic
                    changed = True
        if changed:
            ford_scan.write_log(rows)
        for row, evaluation in closed_events:
            _route_stream_close(row, evaluation)


def position_tracker_job(connection: sqlite3.Connection) -> str:
    """REST safety refresh used if a stream tick is missed or disconnected."""
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
        opened = ford_scan.open_rows(rows)
    if not opened:
        stream_state = (
            "connected" if POSITION_STREAM and POSITION_STREAM.connected else "idle"
        )
        return f"no open positions; stream {stream_state}"
    timestamp = ford_scan.now_ct()
    quotes = ford_scan.get_quotes(
        ford_scan.symbols_for_rows(opened), include_greeks=True
    )
    closed = 0
    refreshed = 0
    with POSITION_FILE_LOCK:
        for row in list(opened):
            evaluation = ford_scan.evaluate_open_row(row, quotes, timestamp)
            if evaluation.get("pl_pct") is None:
                continue
            if evaluation.get("signal") in {
                "STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE"
            }:
                ford_scan.close_row(row, evaluation, timestamp)
                _route_stream_close(row, evaluation)
                closed += 1
            else:
                row["current_pl_pct"] = ford_scan.round_or_blank(
                    evaluation.get("pl_pct"), 1
                )
                row["current_pl_dollars"] = ford_scan.round_or_blank(
                    evaluation.get("pl_dollars"), 0
                )
            refreshed += 1
        if refreshed:
            ford_scan.write_log(rows)
    store_observation(
        connection,
        "position-tracker",
        {"open": len(opened) - closed, "closed": closed, "refreshed": refreshed},
    )
    stream_state = (
        "connected" if POSITION_STREAM and POSITION_STREAM.connected else "fallback"
    )
    return f"{refreshed} refreshed · {closed} closed · stream {stream_state}"


def closed_position_cleanup_job(connection: sqlite3.Connection) -> str:
    """Keep completed trades out of held-positions without running a market scan."""
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
    closed = ford_scan.closed_rows(rows)
    if not closed:
        return "no closed trades to reconcile"
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    report_state = ford_scan.read_report_state()
    journal_counts = ford_scan.sync_all_trade_journals(rows, tracker)
    routed = ford_scan.sync_closed_result_channels(closed, tracker, report_state)
    with POSITION_FILE_LOCK:
        ford_scan.write_log(rows)
    ford_scan.write_report_state(report_state)
    store_observation(
        connection,
        "closed-position-cleanup",
        {
            "closed_checked": len(closed),
            "results_routed": routed,
            "journals": journal_counts,
        },
    )
    for row in closed:
        trade_intelligence.record_event(
            row, "closed-reconciliation", str(row.get("closed_at") or row.get("trade_id")),
            extra={"results_routed": routed, "journals": journal_counts},
        )
    return f"{len(closed)} closed checked; {routed} results routed"


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
        report_state = ford_scan.read_report_state()
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
                    f"avg {ford_scan.fmt_money(item['average_pl_dollars'])} · "
                    f"total {ford_scan.fmt_money(item['total_pl_dollars'])}"
                )
        else:
            lines.append(
                "No group has reached the evidence threshold yet. Collection is active."
            )
        lines.extend([
            "### Guardrail",
            "Historical evidence only; this never changes scanner rules automatically.",
            f"Updated **{ford_scan.portable_strftime(ford_scan.now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
        ])
        tracker.upsert_channel_message(
            "learning_results",
            report_state,
            "learning-results",
            "\n".join(lines)[:2000],
        )
        ford_scan.write_report_state(report_state)
    return (
        f"{summary['closed_trades']} closed trades; "
        f"{len(summary['evidence_ready_groups'])} evidence-ready groups"
    )


def discord_reporting_job(connection: sqlite3.Connection) -> str:
    """Refresh every result dashboard from the complete tracked trade history."""
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    report_state = ford_scan.read_report_state()
    ford_scan.update_performance_pages(tracker, report_state, rows)
    ford_scan.sync_reports(
        tracker,
        report_state,
        rows,
        ford_scan.now_ct(),
        market_open=ford_scan.market_is_open_now()[0],
    )
    ford_scan.write_report_state(report_state)
    outcome_learning_job(connection)
    consumers = (
        "performance-dashboard", "ticker-results", "strategy-results", "wins-losses",
        "play-style-results", "daily-weekly", "learning-results",
    )
    for row in ford_scan.closed_rows(rows):
        version = str(row.get("closed_at") or row.get("last_evaluated_at") or "")
        for consumer in consumers:
            trade_intelligence.acknowledge(str(row.get("trade_id") or ""), consumer, version)
    closed = len(ford_scan.closed_rows(rows))
    store_observation(connection, "discord-reporting", {"closed": closed})
    return f"performance, strategy, ticker, daily, and weekly refreshed from {closed} closed trades"


def trade_intelligence_health_job(connection: sqlite3.Connection) -> str:
    health = trade_intelligence.health()
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
    closed = ford_scan.closed_rows(rows)
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


PLAYBOOK_SPECS = [
    ("regular-call", "Regular Long Call", "REGULAR", "call"),
    ("regular-put", "Regular Long Put", "REGULAR", "put"),
    ("swing-call", "Swing Long Call", "SWING", "call"),
    ("swing-put", "Swing Long Put", "SWING", "put"),
    ("bull-put-spread", "Bull Put Credit Spread", "SPREAD", "put"),
    ("bear-call-spread", "Bear Call Credit Spread", "SPREAD", "call"),
]


def playbook_card_text(
    title: str,
    play_type: str,
    direction: str,
    rows: list[dict[str, str]],
    rotation_day: date,
) -> str:
    matches = [
        row for row in rows
        if str(row.get("play_type") or "").upper() == play_type
        and str(row.get("call_or_put") or "").lower() == direction
    ]
    matches.sort(key=lambda row: row.get("closed_at") or row.get("timestamp") or "")
    example = matches[rotation_day.toordinal() % len(matches)] if matches else None
    bullish = direction == "call" if play_type != "SPREAD" else direction == "put"
    thesis = (
        "bullish evidence: price/trend confirmation and a controlled upside setup"
        if bullish
        else "bearish evidence: downside confirmation and a controlled decline setup"
    )
    if play_type == "SPREAD":
        dte = f"{ford_scan.MIN_DTE}–{ford_scan.MAX_DTE} DTE"
        entry = "SELL TO OPEN the short leg and BUY TO OPEN the protective long leg for one net credit."
        risk = (
            f"Target: BUY TO CLOSE near {ford_scan.SPREAD_TAKE_PROFIT_PCT:.0%} credit capture. "
            f"Stop: BUY TO CLOSE if cost reaches {ford_scan.SPREAD_STOP_MULTIPLE:g}× entry credit. "
            f"Close no later than {ford_scan.SPREAD_EXIT_DTE} DTE."
        )
        stat_reason = (
            f"Short-leg |delta| {ford_scan.SPREAD_SHORT_DELTA_MIN:.2f}–"
            f"{ford_scan.SPREAD_SHORT_DELTA_MAX:.2f}; liquid adjacent protection; "
            "credit and maximum loss must pass the risk cap."
        )
    else:
        dte = (
            f"{ford_scan.REGULAR_MIN_DTE}–{ford_scan.REGULAR_MAX_DTE} DTE"
            if play_type == "REGULAR"
            else f"{ford_scan.MIN_DTE}–{ford_scan.MAX_DTE} DTE"
        )
        entry = "BUY TO OPEN one contract near the recorded ask after every scanner gate passes."
        risk = (
            f"Target: SELL TO CLOSE at approximately +{ford_scan.SINGLE_TAKE_PROFIT_PCT:.0%}. "
            f"Stop: SELL TO CLOSE at approximately -{ford_scan.SINGLE_STOP_PCT:.0%}; "
            "also close near expiration."
        )
        stat_reason = (
            f"|Delta| {ford_scan.SINGLE_LEG_DELTA_MIN:.2f}–{ford_scan.SINGLE_LEG_DELTA_MAX:.2f}; "
            f"premium at most {ford_scan.fmt_money(ford_scan.MAX_RISK_PER_TRADE)}; "
            "open interest, volume, and bid/ask spread must pass liquidity gates."
        )
    lines = [
        f"## {title}",
        f"**Structure:** {dte} · paper trading · one-contract examples",
        "### Why this play is selected",
        f"The scanner requires {thesis}. {stat_reason}",
        "Delta estimates directional sensitivity; IV affects option pricing; theta is time decay; "
        "open interest, volume, and spread indicate whether entry and exit are practical.",
        "### Entry",
        entry,
        "### Stop, target, and close",
        risk,
    ]
    if example:
        metrics = ford_scan.result_metrics([example])
        reason = example.get("setup_reason") or example.get("market_regime") or thesis
        lines.extend([
            "### Rotating recorded example",
            f"**{example.get('trade_id', 'Tracked trade')}** · {example.get('ticker', '—')} · "
            f"{example.get('strike', '—')} · exp {example.get('expiration', '—')}",
            f"Selected because: {reason}",
            f"Entry {example.get('entry_price') or '—'} · exit {example.get('exit_price') or '—'} · "
            f"{example.get('outcome', 'CLOSED')} · net {ford_scan.fmt_metric_money(metrics, 'total_pnl')}",
        ])
    else:
        lines.extend([
            "### Rotating recorded example",
            "No completed example of this exact play type is recorded yet; this card will fill automatically.",
        ])
    lines.extend([
        "### Review prompt",
        "Was the direction correct? Did liquidity, delta, IV, and DTE support the entry? "
        "Was the planned exit followed instead of improvised?",
        "Educational paper-trade walkthrough; not financial advice.",
    ])
    return "\n".join(lines)[:2000]


def examples_reviews_job(connection: sqlite3.Connection) -> str:
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    report_state = ford_scan.read_report_state()
    today = ford_scan.now_ct().date()
    for key, title, play_type, direction in PLAYBOOK_SPECS:
        tracker.upsert_channel_message(
            "examples_reviews",
            report_state,
            f"playbook:{key}",
            playbook_card_text(title, play_type, direction, rows, today),
            search_token=title,
        )
    ford_scan.write_report_state(report_state)
    store_observation(
        connection,
        "examples-reviews",
        {"cards": len(PLAYBOOK_SPECS), "closed_examples": len(ford_scan.closed_rows(rows))},
    )
    return f"{len(PLAYBOOK_SPECS)} strategy playbook cards refreshed"


def discord_card_migration_job(connection: sqlite3.Connection) -> str:
    """Refresh a bounded set of legacy forum cards without delaying scans."""
    with POSITION_FILE_LOCK:
        rows = ford_scan.read_log()
        pending = [
            dict(row)
            for row in ford_scan.open_rows(rows)
            if row.get("discord_format_version") != ford_scan.DISCORD_FORMAT_VERSION
        ][:5]
    if not pending:
        return "all open trade forum cards are current"
    tracker = discord_tracker()
    if not tracker:
        raise RuntimeError("Discord tracker is unavailable")
    refreshed_ids: list[str] = []
    refreshed_threads: dict[str, str] = {}
    report_state = ford_scan.read_report_state()
    for row in pending:
        if not row.get("discord_thread_id"):
            tracker.create_trade_thread(row, "OPEN")
        else:
            try:
                tracker.refresh_trade_thread(row)
            except ford_scan.DiscordError as exc:
                if not ford_scan.discord_route_is_missing(exc):
                    raise
                row["discord_thread_id"] = ""
                row["discord_status"] = ""
                row["discord_format_version"] = ""
                tracker.create_trade_thread(row, "OPEN")
        refreshed_ids.append(row.get("trade_id", ""))
        refreshed_threads[row.get("trade_id", "")] = row.get("discord_thread_id", "")
        ford_scan.sync_open_trade_cards(
            row,
            tracker,
            report_state,
            ford_scan.stored_open_evaluation(row),
            include_entry=True,
        )
        time.sleep(1.0)
    with POSITION_FILE_LOCK:
        latest = ford_scan.read_log()
        refreshed = set(refreshed_ids)
        for row in latest:
            if row.get("trade_id") in refreshed:
                row["discord_thread_id"] = refreshed_threads.get(
                    row.get("trade_id", ""), row.get("discord_thread_id", "")
                )
                row["discord_format_version"] = ford_scan.DISCORD_FORMAT_VERSION
        ford_scan.write_log(latest)
    ford_scan.write_report_state(report_state)
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
        "examples-and-reviews",
        timedelta(hours=12),
        examples_reviews_job,
        retry_interval=timedelta(minutes=5),
    ),
    Job(
        "dynamic-universe-refresh",
        timedelta(minutes=60),
        universe_refresh_job,
        after_hours_interval=timedelta(hours=2),
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
        "full-options-scan",
        timedelta(minutes=15),
        full_scanner_job,
        market_hours_only=True,
        background=True,
        provider_heavy=True,
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
        market_open, _ = ford_scan.market_is_open_now()
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
        ford_scan.TRADIER_TOKEN,
        ford_scan.TRADIER_BASE_URL,
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
        "REST checks are a five-minute safety fallback."
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
