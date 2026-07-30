"""Local Ford information engine.

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
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import ford_scan
import requests
from run_with_env import load_env

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "local-information.db"
LOCK_HOST = "127.0.0.1"
LOCK_PORT = int(os.environ.get("LOCAL_ENGINE_LOCK_PORT", "8765"))
POLL_SECONDS = int(os.environ.get("LOCAL_ENGINE_POLL_SECONDS", "30"))
MARKET_REFRESH_MINUTES = int(os.environ.get("LOCAL_MARKET_REFRESH_MINUTES", "5"))
FILINGS_REFRESH_MINUTES = int(os.environ.get("LOCAL_FILINGS_REFRESH_MINUTES", "30"))
STATUS_REFRESH_MINUTES = int(os.environ.get("LOCAL_STATUS_REFRESH_MINUTES", "15"))
FULL_SCAN_ENABLED = os.environ.get("LOCAL_FULL_SCAN_ENABLED", "false").lower() == "true"


def utc_now() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
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


def market_snapshot() -> dict[str, Any]:
    quote = ford_scan.get_quote(ford_scan.TICKER) or {}
    history = ford_scan.get_daily_history(ford_scan.TICKER, days=400)
    spot = ford_scan.as_float(quote.get("last"))
    if spot is None or not history:
        raise ford_scan.TradierError("Ford quote or price history is unavailable")
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
    context = ford_scan.directional_market_context(history, spot)
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
        "symbol": ford_scan.TICKER,
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
    side: str = "call", limit: int = 8, expiration: str | None = None
) -> list[dict[str, Any]]:
    spot_quote = ford_scan.get_quote(ford_scan.TICKER) or {}
    spot = ford_scan.as_float(spot_quote.get("last"))
    if spot is None:
        raise ford_scan.TradierError("Ford spot price is unavailable")
    expirations = ford_scan.get_expirations(ford_scan.TICKER)
    if expiration is None:
        _, swing = ford_scan.pick_expirations(expirations, ford_scan.now_ct().date())
        expiration = swing[0] if swing else next(iter(expirations), None)
    if not expiration:
        return []
    chain = ford_scan.get_chain(ford_scan.TICKER, expiration)
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
    spot_quote = ford_scan.get_quote(ford_scan.TICKER) or {}
    spot = ford_scan.as_float(spot_quote.get("last"))
    if not option or spot is None:
        return None
    return option_quality(option, spot)


def performance_snapshot() -> dict[str, Any]:
    rows = ford_scan.read_log()
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


def market_alert_text(snapshot: dict[str, Any]) -> str:
    def number(key: str, digits: int = 2, suffix: str = "") -> str:
        value = snapshot.get(key)
        return "Unavailable" if value is None else f"{float(value):.{digits}f}{suffix}"

    return "\n".join(
        [
            "## Ford Local Market Monitor",
            (
                f"**F ${number('price')}** · **{number('change_pct', 2, '%')}** · "
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
    return f"F ${price:.2f} · {snapshot['regime']}"


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
            minimum_minutes=0,
        )
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
    return json.dumps(status, separators=(",", ":"))


def briefing_job(connection: sqlite3.Connection) -> str:
    now = ford_scan.now_ct()
    weekday = now.weekday() < 5
    session = ""
    if weekday and (7 <= now.hour < 8 or (now.hour == 8 and now.minute < 25)):
        session = "premarket"
    elif weekday and 15 <= now.hour < 17:
        session = "after-market"
    if not session:
        return "outside briefing window"
    key = f"briefing:{session}:{now.date().isoformat()}"
    if get_state(connection, key) == "sent":
        return f"{session} already sent"
    snapshot = market_snapshot()
    content = (
        f"## Ford {session.replace('-', ' ').title()} Briefing\n"
        + market_alert_text(snapshot).replace("## Ford Local Market Monitor\n", "")
    )
    store_observation(
        connection,
        "briefing",
        {
            "session": session,
            "date": now.date().isoformat(),
            "market": {k: v for k, v in snapshot.items() if k != "history"},
        },
    )
    sent = publish_change_only(
        connection,
        key,
        content,
        logical_channel="intelligence",
        minimum_minutes=0,
    )
    if sent:
        set_state(connection, key, "sent")
        ford_scan.render_market_chart(snapshot["history"], snapshot["price"])
        tracker = discord_tracker()
        if tracker and ford_scan.CHART_SCREENSHOT_PATH.exists():
            tracker.send_channel_file(
                "charts",
                ford_scan.CHART_SCREENSHOT_PATH,
                content=(
                    f"Ford {session.replace('-', ' ')} chart · "
                    f"{now.date().isoformat()} · ${snapshot['price']:.2f}"
                ),
            )
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
        "## Weekly Ford System Review",
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
    result = ford_scan.main()
    store_observation(
        connection,
        "full-scan",
        {"exit_code": result, "completed_at": iso_now()},
    )
    if result:
        raise RuntimeError(f"Ford scanner exited with code {result}")
    return "Ford options scan completed locally"


@dataclass
class Job:
    name: str
    interval: timedelta
    callback: Callable[[sqlite3.Connection], str]
    market_hours_only: bool = False


JOBS = [
    Job("market-monitor", timedelta(minutes=MARKET_REFRESH_MINUTES), market_job),
    Job("filings-monitor", timedelta(minutes=FILINGS_REFRESH_MINUTES), filings_job),
    Job("health-snapshot", timedelta(minutes=STATUS_REFRESH_MINUTES), status_job),
    Job("session-briefing", timedelta(minutes=15), briefing_job),
    Job("weekly-review", timedelta(minutes=30), weekly_review_job),
    Job(
        "full-options-scan",
        timedelta(minutes=15),
        full_scanner_job,
        market_hours_only=True,
    ),
]


def due(connection: sqlite3.Connection, job: Job, now: datetime) -> bool:
    last = get_state(connection, f"job:{job.name}")
    if last:
        try:
            if now - datetime.fromisoformat(last) < job.interval:
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
    connection.commit()
    print(f"{job.name}: {status} · {detail}")


def acquire_instance_lock() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        listener.bind((LOCK_HOST, LOCK_PORT))
        listener.listen(1)
    except OSError as exc:
        listener.close()
        raise RuntimeError(
            "The local information engine is already running."
        ) from exc
    return listener


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
    connection = connect_db()
    try:
        with instance_lock:
            while True:
                current = utc_now()
                for job in JOBS:
                    if due(connection, job, current):
                        run_job(connection, job)
                time.sleep(max(POLL_SECONDS, 10))
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
