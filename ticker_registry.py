"""Persistent ticker registry for the shared scanner universe."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import spy_scanner

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "ticker-registry.db"
CONFIG_PATH = ROOT / "config" / "tickers.json"

DESK_CHANNELS = {
    "dashboard": "{ticker}-dashboard",
    "options_setups": "{ticker}-options-setups",
    "charts": "{ticker}-charts",
    "news_events": "{ticker}-news-events",
    "research_performance": "{ticker}-research-performance",
}


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker):
        raise ValueError("Ticker must contain 1–10 letters, numbers, periods, or hyphens.")
    return ticker


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            added_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resume_on TEXT NOT NULL DEFAULT '',
            category_id TEXT NOT NULL DEFAULT '',
            channels_json TEXT NOT NULL DEFAULT '{}',
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO tickers(ticker, status, added_at, updated_at, note)
        VALUES ('F', 'ACTIVE', ?, ?, 'Protected founding strategy')
        """,
        (now_text(), now_text()),
    )
    if DB_PATH == ROOT / "state" / "ticker-registry.db" and CONFIG_PATH.exists():
        try:
            configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            configured = {}
        for item in configured.get("tickers") or []:
            ticker = str(item.get("ticker") or "").strip().upper()
            status = str(item.get("status") or "ACTIVE").strip().upper()
            if (
                not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker)
                or status not in {"ACTIVE", "PAUSED", "ARCHIVED"}
            ):
                continue
            connection.execute(
                """
                INSERT INTO tickers(
                    ticker, status, added_at, updated_at, resume_on, note
                ) VALUES (?, ?, ?, ?, ?, 'Loaded from tracked configuration')
                ON CONFLICT(ticker) DO UPDATE SET
                    status=excluded.status,
                    resume_on=excluded.resume_on
                """,
                (
                    ticker,
                    status,
                    now_text(),
                    now_text(),
                    str(item.get("resume_on") or ""),
                ),
            )
    connection.commit()
    return connection


def export_tracked_config() -> None:
    if DB_PATH != ROOT / "state" / "ticker-registry.db":
        return
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT ticker, status, resume_on FROM tickers ORDER BY ticker"
        ).fetchall()
    finally:
        connection.close()
    payload = {
        "version": 1,
        "tickers": [
            {
                "ticker": row["ticker"],
                "status": row["status"],
                "resume_on": row["resume_on"],
            }
            for row in rows
        ],
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    try:
        result["channels"] = json.loads(result.pop("channels_json") or "{}")
    except json.JSONDecodeError:
        result["channels"] = {}
    return result


def get(ticker: str) -> dict[str, Any] | None:
    ticker = normalize_ticker(ticker)
    connection = connect()
    try:
        return row_dict(
            connection.execute("SELECT * FROM tickers WHERE ticker=?", (ticker,)).fetchone()
        )
    finally:
        connection.close()


def all_tickers() -> list[dict[str, Any]]:
    connection = connect()
    try:
        return [
            row_dict(row) or {}
            for row in connection.execute(
                "SELECT * FROM tickers ORDER BY CASE ticker WHEN 'F' THEN 0 ELSE 1 END, ticker"
            )
        ]
    finally:
        connection.close()


def active_tickers() -> list[str]:
    refresh_daily_pauses()
    return [
        str(item["ticker"])
        for item in all_tickers()
        if item.get("status") == "ACTIVE"
    ]


def save(
    ticker: str,
    *,
    status: str,
    resume_on: str = "",
    category_id: str = "",
    channels: dict[str, str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    existing = get(ticker)
    connection = connect()
    try:
        connection.execute(
            """
            INSERT INTO tickers(
                ticker, status, added_at, updated_at, resume_on,
                category_id, channels_json, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                status=excluded.status,
                updated_at=excluded.updated_at,
                resume_on=excluded.resume_on,
                category_id=CASE
                    WHEN excluded.category_id='' THEN tickers.category_id
                    ELSE excluded.category_id
                END,
                channels_json=CASE
                    WHEN excluded.channels_json='{}' THEN tickers.channels_json
                    ELSE excluded.channels_json
                END,
                note=excluded.note
            """,
            (
                ticker,
                status,
                existing["added_at"] if existing else now_text(),
                now_text(),
                resume_on,
                category_id,
                json.dumps(channels or {}, sort_keys=True),
                note,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    export_tracked_config()
    return get(ticker) or {}


def next_market_date() -> str:
    day = date.today() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def pause(ticker: str, *, today_only: bool) -> dict[str, Any]:
    existing = get(ticker)
    if not existing:
        raise ValueError(f"{normalize_ticker(ticker)} is not integrated.")
    if existing["ticker"] == "SPY":
        raise ValueError("SPY is protected and cannot be paused from Discord.")
    return save(
        ticker,
        status="PAUSED",
        resume_on=next_market_date() if today_only else "",
        note="Paused through Discord",
    )


def resume(ticker: str) -> dict[str, Any]:
    existing = get(ticker)
    if not existing:
        raise ValueError(f"{normalize_ticker(ticker)} is not integrated.")
    return save(ticker, status="ACTIVE", note="Enabled through Discord")


def archive(ticker: str) -> dict[str, Any]:
    existing = get(ticker)
    if not existing:
        raise ValueError(f"{normalize_ticker(ticker)} is not integrated.")
    if existing["ticker"] == "SPY":
        raise ValueError("SPY is protected and cannot be removed.")
    return save(ticker, status="ARCHIVED", note="Archived through Discord")


def refresh_daily_pauses() -> None:
    today = date.today().isoformat()
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE tickers
            SET status='ACTIVE', resume_on='', updated_at=?
            WHERE status='PAUSED' AND resume_on<>'' AND resume_on<=?
            """,
            (now_text(), today),
        )
        connection.commit()
    finally:
        connection.close()
    export_tracked_config()


def provision_discord_desk(ticker: str) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    tracker = spy_scanner.DiscordTracker(
        spy_scanner.DISCORD_BOT_TOKEN, spy_scanner.DISCORD_GUILD_ID
    )
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category_name = f"TICKER • {ticker}"
    category = next(
        (
            item for item in channels
            if item.get("type") == 4
            and str(item.get("name") or "").casefold() == category_name.casefold()
        ),
        None,
    )
    if not category:
        category = tracker._request(
            "POST",
            f"/guilds/{tracker.guild_id}/channels",
            {"name": category_name, "type": 4},
        )
        channels.append(category)

    created: dict[str, str] = {}
    lower = ticker.lower().replace(".", "-")
    topics = {
        "dashboard": f"{ticker} live price, trend, levels, and chart context.",
        "options_setups": f"{ticker} option structures, liquidity, filters, and risk.",
        "charts": f"Scheduled and requested {ticker} charts.",
        "news_events": f"{ticker} news, filings, earnings, dividends, and events.",
        "research_performance": f"{ticker} research evidence and strategy performance.",
    }
    for key, template in DESK_CHANNELS.items():
        name = template.format(ticker=lower)
        channel = next(
            (
                item for item in channels
                if item.get("type") == 0
                and str(item.get("name") or "").casefold() == name.casefold()
            ),
            None,
        )
        if not channel:
            channel = tracker._request(
                "POST",
                f"/guilds/{tracker.guild_id}/channels",
                {
                    "name": name,
                    "type": 0,
                    "parent_id": category["id"],
                    "topic": topics[key],
                },
            )
            channels.append(channel)
        elif str(channel.get("parent_id") or "") != str(category["id"]):
            channel = tracker._request(
                "PATCH",
                f"/channels/{channel['id']}",
                {"parent_id": category["id"], "topic": topics[key]},
            )
        created[key] = str(channel["id"])

    return save(
        ticker,
        status="ACTIVE",
        category_id=str(category["id"]),
        channels=created,
        note="Discord desk provisioned",
    )


def rename_category(ticker: str, archived: bool) -> None:
    item = get(ticker)
    if not item or not item.get("category_id"):
        return
    tracker = spy_scanner.DiscordTracker(
        spy_scanner.DISCORD_BOT_TOKEN, spy_scanner.DISCORD_GUILD_ID
    )
    tracker._request(
        "PATCH",
        f"/channels/{item['category_id']}",
        {"name": f"{'ARCHIVED' if archived else 'TICKER'} • {item['ticker']}"},
    )
