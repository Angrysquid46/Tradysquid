"""
Ford (F) options scanner + Discord trade tracker.

Purpose
-------
- Read-only Tradier market data.
- Tracks each play in CSV, a static HTML dashboard, and one Discord forum post.
- Reprices open plays on each scheduled run and routes closed results to Discord.

Required GitHub Actions secrets
-------------------------------
TRADIER_TOKEN
TRADIER_BASE_URL
DISCORD_WEBHOOK_URL          # fallback alerts
DISCORD_BOT_TOKEN            # TradeBot REST authentication
DISCORD_GUILD_ID             # Tradysquids server ID

Expected Discord channel names
------------------------------
Forum: trade-journal
Text: scanner-feed, qualified-trades, entry-alerts, position-updates,
      exit-alerts, wins, losses, scratches, daily-recap, weekly-report,
      performance-stats, strategy-breakdown, scanner-status, api-errors,
      workflow-log, admin-notes, welcome, strategy-rules, risk-management,
      server-guide

Expected forum status tags
--------------------------
WATCHING, QUALIFIED, OPEN, HOLDING, TARGET HIT, STOP WARNING,
WIN, LOSS, SCRATCH, EXPIRED
Emoji prefixes are fine. Matching ignores emoji and punctuation.
"""

from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TICKER = "F"
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "").strip()
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

REPO_ROOT = Path(__file__).resolve().parent
STATE_DIR = REPO_ROOT / "state"
DOCS_DIR = REPO_ROOT / "docs"
LOG_PATH = STATE_DIR / "ford-plays-log.csv"
DASHBOARD_PATH = DOCS_DIR / "index.html"
REPORT_STATE_PATH = STATE_DIR / "discord-report-state.json"

MARKET_TZ = ZoneInfo("America/Chicago")
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)

# Candidate screening
MIN_OPEN_INTEREST = int(os.environ.get("MIN_OPEN_INTEREST", "25"))
SPREAD_SHORT_DELTA_MIN = float(os.environ.get("SPREAD_SHORT_DELTA_MIN", "0.10"))
SPREAD_SHORT_DELTA_MAX = float(os.environ.get("SPREAD_SHORT_DELTA_MAX", "0.35"))
SINGLE_LEG_DELTA_MIN = float(os.environ.get("SINGLE_LEG_DELTA_MIN", "0.35"))
SINGLE_LEG_DELTA_MAX = float(os.environ.get("SINGLE_LEG_DELTA_MAX", "0.65"))
STRIKE_BAND_PCT = float(os.environ.get("STRIKE_BAND_PCT", "0.20"))
MAX_NEW_PLAYS_PER_SCAN = int(os.environ.get("MAX_NEW_PLAYS_PER_SCAN", "4"))
REENTRY_COOLDOWN_MINUTES = int(os.environ.get("REENTRY_COOLDOWN_MINUTES", "90"))

# Management rules
SPREAD_STOP_MULTIPLE = float(os.environ.get("SPREAD_STOP_MULTIPLE", "2.0"))
SPREAD_TAKE_PROFIT_PCT = float(os.environ.get("SPREAD_TAKE_PROFIT_PCT", "0.50"))
SINGLE_TAKE_PROFIT_PCT = float(os.environ.get("SINGLE_TAKE_PROFIT_PCT", "0.225"))
SINGLE_STOP_PCT = float(os.environ.get("SINGLE_STOP_PCT", "0.225"))
SCRATCH_BAND_PCT = float(os.environ.get("SCRATCH_BAND_PCT", "5.0"))

# Discord update throttling
DISCORD_PL_CHANGE_THRESHOLD = float(os.environ.get("DISCORD_PL_CHANGE_THRESHOLD", "10.0"))
DISCORD_HEARTBEAT_MINUTES = int(os.environ.get("DISCORD_HEARTBEAT_MINUTES", "60"))
DISCORD_SYNC_EXISTING_OPEN = os.environ.get("DISCORD_SYNC_EXISTING_OPEN", "true").lower() == "true"
DISCORD_FORMAT_VERSION = "6"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Tradysquids-TradeBot/1.0"})

LOG_HEADER = [
    "trade_id",
    "timestamp",
    "action",
    "play_type",
    "ticker",
    "call_or_put",
    "strike",
    "expiration",
    "option_symbol",
    "short_symbol",
    "long_symbol",
    "cost_or_credit",
    "entry_price",
    "delta_at_entry",
    "theta_at_entry",
    "iv_at_entry",
    "pop_estimate",
    "max_profit",
    "max_risk",
    "breakeven",
    "open_interest_at_entry",
    "bid_ask_width_at_entry",
    "outcome",
    "pct_gain_loss",
    "closed_at",
    "last_mark",
    "current_pl_dollars",
    "current_pl_pct",
    "max_favorable_pct",
    "max_adverse_pct",
    "last_signal",
    "last_evaluated_at",
    "discord_thread_id",
    "discord_status",
    "discord_format_version",
    "last_discord_signal",
    "last_discord_pl_pct",
    "last_discord_update_at",
]

CHANNEL_NAMES = {
    "forum": "trade-journal",
    "scanner_feed": "scanner-feed",
    "qualified": "qualified-trades",
    "entry": "entry-alerts",
    "updates": "position-updates",
    "exit": "exit-alerts",
    "wins": "wins",
    "losses": "losses",
    "scratches": "scratches",
    "daily_recap": "daily-recap",
    "weekly_report": "weekly-report",
    "performance_stats": "performance-stats",
    "strategy_breakdown": "strategy-breakdown",
    "status": "scanner-status",
    "errors": "api-errors",
    "workflow_log": "workflow-log",
    "admin_notes": "admin-notes",
    "welcome": "welcome",
    "strategy_rules": "strategy-rules",
    "risk_management": "risk-management",
    "server_guide": "server-guide",
}

TAG_KEYS = {
    "WATCHING",
    "QUALIFIED",
    "OPEN",
    "HOLDING",
    "TARGET HIT",
    "STOP WARNING",
    "WIN",
    "LOSS",
    "SCRATCH",
    "EXPIRED",
}

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def now_ct() -> datetime:
    return datetime.now(MARKET_TZ)


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_blank(value: float | None, digits: int = 2) -> str:
    return "" if value is None else str(round(value, digits))


def fmt_money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def fmt_strike(value: Any) -> str:
    return f"{float(value):g}"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=MARKET_TZ)
        return parsed.astimezone(MARKET_TZ)
    except ValueError:
        return None


def normalized_name(value: str) -> str:
    # Remove emoji/punctuation, preserve words and spaces.
    clean = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().upper()
    return re.sub(r"\s+", " ", clean)


def split_chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def read_report_state() -> dict[str, Any]:
    default = {
        "messages": {},
        "daily_report_date": "",
        "weekly_report_key": "",
        "guide_version": "",
    }
    if not REPORT_STATE_PATH.exists():
        return default
    try:
        loaded = json.loads(REPORT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    if not isinstance(loaded, dict):
        return default
    default.update(loaded)
    if not isinstance(default.get("messages"), dict):
        default["messages"] = {}
    return default


def write_report_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def market_is_open_now() -> tuple[bool, datetime]:
    now = now_ct()
    if now.weekday() >= 5:
        return False, now
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_time <= now <= close_time, now


def days_to_expiry(expiration: str) -> int:
    return (datetime.strptime(expiration, "%Y-%m-%d").date() - now_ct().date()).days


def option_symbol(ticker: str, expiration: str, call_or_put: str, strike: float) -> str:
    exp = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    cp = "C" if call_or_put.lower() == "call" else "P"
    strike_code = f"{int(round(float(strike) * 1000)):08d}"
    return f"{ticker.upper()}{exp}{cp}{strike_code}"


def format_spread_strike(sell_strike: float, buy_strike: float) -> str:
    return f"SELL {fmt_strike(sell_strike)} / BUY {fmt_strike(buy_strike)}"


def parse_spread_strikes(value: str) -> tuple[float, float]:
    match = re.search(r"SELL\s*([\d.]+)\s*/\s*BUY\s*([\d.]+)", value, re.IGNORECASE)
    if match:
        return float(match.group(1)), float(match.group(2))
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"Unrecognized spread strike format: {value!r}")
    return float(parts[0]), float(parts[1])


def parse_entry_price(row: dict[str, str]) -> float:
    direct = as_float(row.get("entry_price"))
    if direct is not None:
        return direct
    raw = (row.get("cost_or_credit") or "").replace("credit", "").strip()
    return as_float(raw, 0.0) or 0.0


def row_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("play_type", ""),
        row.get("call_or_put", ""),
        row.get("strike", ""),
        row.get("expiration", ""),
    )


def trade_title(row: dict[str, str]) -> str:
    trade_id = row.get("trade_id") or "F-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        return (
            f"F #{sequence} | {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)} "
            f"{kind} CREDIT | {expiration}"
        )

    strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
    return f"F #{sequence} | BUY {strike} {kind} | {expiration}"


def format_expiration(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (TypeError, ValueError):
        return value or "—"


def entry_alert_text(row: dict[str, str], include_link: str = "") -> str:
    trade_id = row.get("trade_id") or "F-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    entry = parse_entry_price(row)

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        setup = (
            f"🔴 SELL 1 F {fmt_strike(sell_strike)} {kind} | "
            f"🟢 BUY 1 F {fmt_strike(buy_strike)} {kind}"
        )
        entry_text = f"${entry:.2f} CR"
        stop_text = f"${entry * SPREAD_STOP_MULTIPLE:.2f} DB"
        target_text = f"${entry * (1 - SPREAD_TAKE_PROFIT_PCT):.2f} DB"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        setup = f"🟢 BUY 1 F {strike} {kind}"
        entry_text = f"${entry:.2f}"
        stop_text = f"${entry * (1 - SINGLE_STOP_PCT):.2f}"
        target_text = f"${entry * (1 + SINGLE_TAKE_PROFIT_PCT):.2f}"

    lines = [
        f"**F #{sequence}** • {setup}",
        f"ENTRY {entry_text} • STOP {stop_text} • TP {target_text}",
    ]
    if include_link:
        lines.append(f"[Journal]({include_link})")
    return "\n".join(lines)[:2000]


def position_update_text(row: dict[str, str], evaluation: dict[str, Any]) -> str:
    return "\n".join([
        f"📊 **{row.get('trade_id')} • {evaluation.get('signal', 'HOLD')}**",
        f"Mark: {fmt_money(as_float(evaluation.get('mark')))}",
        f"P/L: {fmt_money(as_float(evaluation.get('pl_dollars')))} ({fmt_pct(as_float(evaluation.get('pl_pct')))})",
        f"MFE: {fmt_pct(as_float(row.get('max_favorable_pct')))} | MAE: {fmt_pct(as_float(row.get('max_adverse_pct')))}",
    ])


def close_alert_text(row: dict[str, str], evaluation: dict[str, Any], include_link: str = "") -> str:
    outcome = row.get("outcome", "CLOSED")
    icon = {"WIN": "🏆", "LOSS": "🔴", "SCRATCH": "➖"}.get(outcome, "📕")
    lines = [
        f"{icon} **{row.get('trade_id')} • {outcome}**",
        f"Final P/L: {fmt_money(as_float(evaluation.get('pl_dollars')))} ({fmt_pct(as_float(evaluation.get('pl_pct')))})",
        f"Exit reason: {evaluation.get('signal', 'CLOSE')}",
        f"MFE: {fmt_pct(as_float(row.get('max_favorable_pct')))} | MAE: {fmt_pct(as_float(row.get('max_adverse_pct')))}",
    ]
    if include_link:
        lines.append(f"🔗 {include_link}")
    return "\n".join(lines)[:2000]

def thread_link(thread_id: str) -> str:
    if not thread_id or not DISCORD_GUILD_ID:
        return ""
    return f"https://discord.com/channels/{DISCORD_GUILD_ID}/{thread_id}"

# ---------------------------------------------------------------------------
# Tradier market data
# ---------------------------------------------------------------------------


class TradierError(RuntimeError):
    pass


def tradier_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TRADIER_TOKEN:
        raise TradierError("TRADIER_TOKEN is not configured")
    try:
        response = SESSION.get(
            f"{TRADIER_BASE_URL}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise TradierError(f"Tradier request failed: {exc}") from exc
    if not response.ok:
        body = response.text[:500].replace(TRADIER_TOKEN, "[REDACTED]")
        raise TradierError(f"Tradier HTTP {response.status_code} for {path}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise TradierError(f"Tradier returned invalid JSON for {path}") from exc


def get_quotes(symbols: list[str], include_greeks: bool = True) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(symbol for symbol in symbols if symbol))
    quote_map: dict[str, dict[str, Any]] = {}
    for chunk in split_chunks(unique, 50):
        data = tradier_get(
            "/markets/quotes",
            {"symbols": ",".join(chunk), "greeks": str(include_greeks).lower()},
        )
        quotes = data.get("quotes", {}).get("quote")
        if not quotes:
            continue
        if isinstance(quotes, dict):
            quotes = [quotes]
        for quote in quotes:
            symbol = quote.get("symbol")
            if symbol:
                quote_map[symbol] = quote
    return quote_map


def get_quote(symbol: str) -> dict[str, Any] | None:
    return get_quotes([symbol], include_greeks=False).get(symbol)


def get_expirations(symbol: str) -> list[str]:
    data = tradier_get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    values = data.get("expirations", {}).get("date")
    if values is None:
        return []
    return [values] if isinstance(values, str) else list(values)


def get_strikes(symbol: str, expiration: str) -> list[float]:
    data = tradier_get("/markets/options/strikes", {"symbol": symbol, "expiration": expiration})
    values = data.get("strikes", {}).get("strike")
    if values is None:
        return []
    if isinstance(values, (int, float)):
        return [float(values)]
    return [float(value) for value in values]


def get_chain(symbol: str, expiration: str) -> list[dict[str, Any]]:
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )
    values = data.get("options", {}).get("option")
    if values is None:
        return []
    return [values] if isinstance(values, dict) else list(values)

# ---------------------------------------------------------------------------
# CSV state and migration
# ---------------------------------------------------------------------------


def blank_row() -> dict[str, str]:
    return {column: "" for column in LOG_HEADER}


def read_log() -> list[dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows = [migrate_row(row) for row in raw_rows]
    assign_missing_trade_ids(rows)
    return rows


def write_log(rows: list[dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in LOG_HEADER})


def migrate_row(raw: dict[str, Any]) -> dict[str, str]:
    row = blank_row()
    for key, value in raw.items():
        if key in row and value is not None:
            row[key] = str(value)

    row["ticker"] = row.get("ticker") or TICKER
    row["outcome"] = (row.get("outcome") or "OPEN").upper()
    row["entry_price"] = round_or_blank(parse_entry_price(row), 4)
    row["discord_status"] = row.get("discord_status") or row["outcome"]
    row["last_signal"] = row.get("last_signal") or ("HOLD" if row["outcome"] == "OPEN" else row["outcome"])

    try:
        if row.get("play_type") == "SPREAD":
            sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
            row["strike"] = format_spread_strike(sell_strike, buy_strike)
            row["short_symbol"] = row.get("short_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], sell_strike
            )
            row["long_symbol"] = row.get("long_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], buy_strike
            )
        elif row.get("strike") and row.get("expiration") and row.get("call_or_put"):
            row["option_symbol"] = row.get("option_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], float(row["strike"])
            )
    except (ValueError, TypeError):
        pass

    fill_trade_math(row)
    return row


def assign_missing_trade_ids(rows: list[dict[str, str]]) -> None:
    used: set[str] = {row["trade_id"] for row in rows if row.get("trade_id")}
    next_sequence: dict[str, int] = {}
    for row in rows:
        trade_id = row.get("trade_id", "")
        match = re.fullmatch(r"F-(\d{8})-(\d{3,})", trade_id)
        if match:
            day_key, sequence = match.group(1), int(match.group(2))
            next_sequence[day_key] = max(next_sequence.get(day_key, 1), sequence + 1)

    for row in rows:
        if row.get("trade_id"):
            continue
        timestamp = parse_iso(row.get("timestamp")) or now_ct()
        day_key = timestamp.strftime("%Y%m%d")
        sequence = next_sequence.get(day_key, 1)
        candidate = f"F-{day_key}-{sequence:03d}"
        while candidate in used:
            sequence += 1
            candidate = f"F-{day_key}-{sequence:03d}"
        row["trade_id"] = candidate
        used.add(candidate)
        next_sequence[day_key] = sequence + 1


def next_trade_id(rows: list[dict[str, str]], timestamp: datetime) -> str:
    day_key = timestamp.strftime("%Y%m%d")
    highest = 0
    pattern = re.compile(rf"F-{day_key}-(\d+)$")
    for row in rows:
        match = pattern.match(row.get("trade_id", ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"F-{day_key}-{highest + 1:03d}"


def fill_trade_math(row: dict[str, str]) -> None:
    entry = parse_entry_price(row)
    delta = abs(as_float(row.get("delta_at_entry"), 0.0) or 0.0)
    kind = row.get("call_or_put", "").lower()
    play_type = row.get("play_type", "").upper()

    if play_type == "SPREAD":
        try:
            short_strike, long_strike = parse_spread_strikes(row.get("strike", ""))
        except ValueError:
            return
        width = abs(short_strike - long_strike)
        max_profit = max(entry, 0) * 100
        max_risk = max(width - entry, 0) * 100
        breakeven = short_strike - entry if kind == "put" else short_strike + entry
        row["max_profit"] = row.get("max_profit") or round_or_blank(max_profit, 2)
        row["max_risk"] = row.get("max_risk") or round_or_blank(max_risk, 2)
        row["breakeven"] = row.get("breakeven") or round_or_blank(breakeven, 2)
        row["pop_estimate"] = row.get("pop_estimate") or round_or_blank((1 - delta) * 100, 1)
    else:
        strike = as_float(row.get("strike"))
        if strike is None:
            return
        max_risk = entry * 100
        breakeven = strike + entry if kind == "call" else strike - entry
        row["max_risk"] = row.get("max_risk") or round_or_blank(max_risk, 2)
        if kind == "put":
            row["max_profit"] = row.get("max_profit") or round_or_blank(max((strike - entry) * 100, 0), 2)
        else:
            row["max_profit"] = row.get("max_profit") or "UNLIMITED"
        row["breakeven"] = row.get("breakeven") or round_or_blank(breakeven, 2)
        row["pop_estimate"] = row.get("pop_estimate") or round_or_blank(delta * 100, 1)


def open_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("outcome") == "OPEN"]


def recently_tracked(rows: list[dict[str, str]], candidate: dict[str, Any], now: datetime) -> bool:
    key = (
        candidate["play_type"],
        candidate["call_or_put"],
        candidate["strike"],
        candidate["expiration"],
    )
    cooldown = timedelta(minutes=REENTRY_COOLDOWN_MINUTES)
    for row in reversed(rows):
        if row_key(row) != key:
            continue
        if row.get("outcome") == "OPEN":
            return True
        event_time = parse_iso(row.get("closed_at")) or parse_iso(row.get("timestamp"))
        if event_time and now - event_time < cooldown:
            return True
    return False

# ---------------------------------------------------------------------------
# Candidate scan
# ---------------------------------------------------------------------------


def pick_expirations(expirations: list[str], today: date) -> tuple[list[str], list[str]]:
    near: list[str] = []
    swing: list[str] = []
    for expiration in expirations:
        expiry_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        days_out = (expiry_date - today).days
        if 0 < days_out <= 8:
            near.append(expiration)
        elif 14 <= days_out <= 42:
            swing.append(expiration)
    return sorted(near), sorted(swing)


def filter_strikes(strikes: list[float], spot: float) -> list[float]:
    low = spot * (1 - STRIKE_BAND_PCT)
    high = spot * (1 + STRIKE_BAND_PCT)
    return sorted(strike for strike in strikes if low <= strike <= high)


def option_has_liquidity(option: dict[str, Any]) -> bool:
    bid = as_float(option.get("bid"), 0.0) or 0.0
    open_interest = int(as_float(option.get("open_interest"), 0.0) or 0)
    return bid > 0 and open_interest >= MIN_OPEN_INTEREST


def greek(option: dict[str, Any], key: str) -> float | None:
    return as_float((option.get("greeks") or {}).get(key))


def iv_value(option: dict[str, Any]) -> float | None:
    greeks = option.get("greeks") or {}
    return as_float(greeks.get("mid_iv") or greeks.get("smv_vol") or greeks.get("bid_iv"))


def scan_credit_spreads(chain: list[dict[str, Any]], kind: str, expiration: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    liquid = {float(option["strike"]): option for option in chain if option_has_liquidity(option)}
    strikes = sorted(liquid)
    for index, short_strike in enumerate(strikes):
        short_option = liquid[short_strike]
        delta = abs(greek(short_option, "delta") or 0.0)
        if not SPREAD_SHORT_DELTA_MIN <= delta <= SPREAD_SHORT_DELTA_MAX:
            continue
        if kind == "call":
            long_strike = strikes[index + 1] if index + 1 < len(strikes) else None
        else:
            long_strike = strikes[index - 1] if index > 0 else None
        if long_strike is None:
            continue
        long_option = liquid[long_strike]
        short_bid = as_float(short_option.get("bid"), 0.0) or 0.0
        short_ask = as_float(short_option.get("ask"), 0.0) or 0.0
        long_bid = as_float(long_option.get("bid"), 0.0) or 0.0
        long_ask = as_float(long_option.get("ask"), 0.0) or 0.0
        credit = short_bid - long_ask
        width = abs(short_strike - long_strike)
        if credit <= 0 or width <= 0 or credit >= width:
            continue
        short_oi = int(as_float(short_option.get("open_interest"), 0.0) or 0)
        long_oi = int(as_float(long_option.get("open_interest"), 0.0) or 0)
        combined_width = max(short_ask - short_bid, 0) + max(long_ask - long_bid, 0)
        theta = -(greek(short_option, "theta") or 0.0) + (greek(long_option, "theta") or 0.0)
        reward_risk = credit / max(width - credit, 0.01)
        score = (1 - delta) * 100 + reward_risk * 20 + math.log1p(min(short_oi, long_oi)) - combined_width * 25
        candidates.append(
            {
                "play_type": "SPREAD",
                "call_or_put": kind,
                "strike": format_spread_strike(short_strike, long_strike),
                "sell_strike": short_strike,
                "buy_strike": long_strike,
                "expiration": expiration,
                "entry_price": round(credit, 2),
                "cost_or_credit": f"{round(credit, 2)} credit",
                "delta": round(greek(short_option, "delta") or 0.0, 4),
                "theta": round(theta, 4),
                "iv": round(iv_value(short_option) or 0.0, 4),
                "pop": round((1 - delta) * 100, 1),
                "max_profit": round(credit * 100, 2),
                "max_risk": round((width - credit) * 100, 2),
                "breakeven": round(short_strike - credit if kind == "put" else short_strike + credit, 2),
                "open_interest": min(short_oi, long_oi),
                "bid_ask_width": round(combined_width, 2),
                "short_symbol": short_option.get("symbol") or option_symbol(TICKER, expiration, kind, short_strike),
                "long_symbol": long_option.get("symbol") or option_symbol(TICKER, expiration, kind, long_strike),
                "score": score,
            }
        )
    return candidates


def scan_single_legs(chain: list[dict[str, Any]], kind: str, expiration: str, play_type: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for option in chain:
        if not option_has_liquidity(option):
            continue
        delta_signed = greek(option, "delta") or 0.0
        delta = abs(delta_signed)
        if not SINGLE_LEG_DELTA_MIN <= delta <= SINGLE_LEG_DELTA_MAX:
            continue
        ask = as_float(option.get("ask"), 0.0) or 0.0
        bid = as_float(option.get("bid"), 0.0) or 0.0
        if ask <= 0:
            continue
        strike = float(option["strike"])
        open_interest = int(as_float(option.get("open_interest"), 0.0) or 0)
        spread_width = max(ask - bid, 0)
        score = (1 - abs(delta - 0.50)) * 50 + math.log1p(open_interest) * 2 - (spread_width / ask) * 20
        max_profit: str | float
        if kind == "call":
            max_profit = "UNLIMITED"
        else:
            max_profit = round(max((strike - ask) * 100, 0), 2)
        candidates.append(
            {
                "play_type": play_type,
                "call_or_put": kind,
                "strike": fmt_strike(strike),
                "expiration": expiration,
                "entry_price": round(ask, 2),
                "cost_or_credit": str(round(ask, 2)),
                "delta": round(delta_signed, 4),
                "theta": round(greek(option, "theta") or 0.0, 4),
                "iv": round(iv_value(option) or 0.0, 4),
                "pop": round(delta * 100, 1),
                "max_profit": max_profit,
                "max_risk": round(ask * 100, 2),
                "breakeven": round(strike + ask if kind == "call" else strike - ask, 2),
                "open_interest": open_interest,
                "bid_ask_width": round(spread_width, 2),
                "option_symbol": option.get("symbol") or option_symbol(TICKER, expiration, kind, strike),
                "score": score,
            }
        )
    return candidates


def candidate_to_row(candidate: dict[str, Any], rows: list[dict[str, str]], timestamp: datetime) -> dict[str, str]:
    row = blank_row()
    row.update(
        {
            "trade_id": next_trade_id(rows, timestamp),
            "timestamp": timestamp.isoformat(),
            "action": "SELL open" if candidate["play_type"] == "SPREAD" else "BUY open",
            "play_type": candidate["play_type"],
            "ticker": TICKER,
            "call_or_put": candidate["call_or_put"],
            "strike": candidate["strike"],
            "expiration": candidate["expiration"],
            "option_symbol": candidate.get("option_symbol", ""),
            "short_symbol": candidate.get("short_symbol", ""),
            "long_symbol": candidate.get("long_symbol", ""),
            "cost_or_credit": candidate["cost_or_credit"],
            "entry_price": str(candidate["entry_price"]),
            "delta_at_entry": str(candidate["delta"]),
            "theta_at_entry": str(candidate["theta"]),
            "iv_at_entry": str(candidate["iv"]),
            "pop_estimate": str(candidate["pop"]),
            "max_profit": str(candidate["max_profit"]),
            "max_risk": str(candidate["max_risk"]),
            "breakeven": str(candidate["breakeven"]),
            "open_interest_at_entry": str(candidate["open_interest"]),
            "bid_ask_width_at_entry": str(candidate["bid_ask_width"]),
            "outcome": "OPEN",
            "last_mark": str(candidate["entry_price"]),
            "current_pl_dollars": "0.0",
            "current_pl_pct": "0.0",
            "max_favorable_pct": "0.0",
            "max_adverse_pct": "0.0",
            "last_signal": "HOLD",
            "last_evaluated_at": timestamp.isoformat(),
            "discord_status": "OPEN",
        }
    )
    return row

# ---------------------------------------------------------------------------
# Open-play evaluation
# ---------------------------------------------------------------------------


def symbols_for_rows(rows: list[dict[str, str]]) -> list[str]:
    symbols: list[str] = [TICKER]
    for row in rows:
        if row.get("play_type") == "SPREAD":
            symbols.extend([row.get("short_symbol", ""), row.get("long_symbol", "")])
        else:
            symbols.append(row.get("option_symbol", ""))
    return [symbol for symbol in symbols if symbol]


def conservative_option_exit(quote: dict[str, Any]) -> float:
    bid = as_float(quote.get("bid"), 0.0) or 0.0
    ask = as_float(quote.get("ask"), 0.0) or 0.0
    last = as_float(quote.get("last"), 0.0) or 0.0
    if bid > 0:
        return bid
    if bid >= 0 and ask > 0:
        return (bid + ask) / 2
    return last


def evaluate_open_row(row: dict[str, str], quotes: dict[str, dict[str, Any]], timestamp: datetime) -> dict[str, Any]:
    entry = parse_entry_price(row)
    expiring_soon = days_to_expiry(row["expiration"]) <= 1
    play_type = row.get("play_type")

    if play_type == "SPREAD":
        short_quote = quotes.get(row.get("short_symbol", ""))
        long_quote = quotes.get(row.get("long_symbol", ""))
        if not short_quote or not long_quote:
            return {"signal": "HOLD", "note": "missing live leg quote", "pl_dollars": None, "pl_pct": None}
        short_ask = as_float(short_quote.get("ask"), as_float(short_quote.get("last"), 0.0)) or 0.0
        long_bid = as_float(long_quote.get("bid"), as_float(long_quote.get("last"), 0.0)) or 0.0
        cost_to_close = max(short_ask - long_bid, 0.0)
        pnl = entry - cost_to_close
        pnl_pct = (pnl / entry * 100) if entry else 0.0
        signal = "HOLD"
        if cost_to_close >= entry * SPREAD_STOP_MULTIPLE:
            signal = "STOP OUT"
        elif pnl >= entry * SPREAD_TAKE_PROFIT_PCT:
            signal = "TAKE PROFIT"
        elif expiring_soon:
            signal = "EXPIRY CLOSE"
        mark = cost_to_close
        details = {
            "cost_to_close": round(cost_to_close, 4),
            "short_delta": greek(short_quote, "delta"),
            "net_theta": -(greek(short_quote, "theta") or 0.0) + (greek(long_quote, "theta") or 0.0),
            "iv": iv_value(short_quote),
        }
    else:
        quote = quotes.get(row.get("option_symbol", ""))
        if not quote:
            return {"signal": "HOLD", "note": "missing live option quote", "pl_dollars": None, "pl_pct": None}
        mark = conservative_option_exit(quote)
        pnl = mark - entry
        pnl_pct = (pnl / entry * 100) if entry else 0.0
        signal = "HOLD"
        if pnl_pct <= -(SINGLE_STOP_PCT * 100):
            signal = "STOP OUT"
        elif pnl_pct >= SINGLE_TAKE_PROFIT_PCT * 100:
            signal = "TAKE PROFIT"
        elif expiring_soon:
            signal = "EXPIRY CLOSE"
        details = {
            "delta": greek(quote, "delta"),
            "theta": greek(quote, "theta"),
            "iv": iv_value(quote),
        }

    result = {
        "signal": signal,
        "mark": round(mark, 4),
        "pl_dollars": round(pnl * 100, 2),
        "pl_pct": round(pnl_pct, 1),
        **details,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result


def apply_evaluation_to_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> None:
    pnl_pct = as_float(evaluation.get("pl_pct"))
    row["last_evaluated_at"] = timestamp.isoformat()
    row["last_signal"] = evaluation.get("signal", "HOLD")
    row["last_mark"] = round_or_blank(as_float(evaluation.get("mark")), 4)
    row["current_pl_dollars"] = round_or_blank(as_float(evaluation.get("pl_dollars")), 2)
    row["current_pl_pct"] = round_or_blank(pnl_pct, 1)

    if pnl_pct is not None:
        current_mfe = as_float(row.get("max_favorable_pct"), pnl_pct)
        current_mae = as_float(row.get("max_adverse_pct"), pnl_pct)
        row["max_favorable_pct"] = round_or_blank(max(current_mfe or pnl_pct, pnl_pct), 1)
        row["max_adverse_pct"] = round_or_blank(min(current_mae or pnl_pct, pnl_pct), 1)


def close_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> str:
    signal = evaluation.get("signal")
    pnl_pct = as_float(evaluation.get("pl_pct"), 0.0) or 0.0
    if signal == "TAKE PROFIT":
        outcome = "WIN"
    elif signal == "STOP OUT":
        outcome = "LOSS"
    elif abs(pnl_pct) <= SCRATCH_BAND_PCT:
        outcome = "SCRATCH"
    else:
        outcome = "WIN" if pnl_pct > 0 else "LOSS"
    row["outcome"] = outcome
    row["pct_gain_loss"] = round_or_blank(pnl_pct, 1)
    row["closed_at"] = timestamp.isoformat()
    row["discord_status"] = outcome
    return outcome

# ---------------------------------------------------------------------------
# Discord REST client
# ---------------------------------------------------------------------------


class DiscordError(RuntimeError):
    pass


class DiscordTracker:
    API_BASE = "https://discord.com/api/v10"

    def __init__(self, token: str, guild_id: str):
        self.token = token
        self.guild_id = guild_id
        self.ready = False
        self.channels: dict[str, str] = {}
        self.tag_ids: dict[str, str] = {}
        self.forum_id = ""

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.guild_id)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.enabled:
            raise DiscordError("Discord bot token or guild ID is missing")
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
        }
        url = f"{self.API_BASE}{path}"
        for attempt in range(4):
            try:
                response = SESSION.request(method, url, headers=headers, json=payload, timeout=20)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise DiscordError(f"Discord request failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429:
                try:
                    retry_after = float(response.json().get("retry_after", 1.0))
                except (ValueError, TypeError):
                    retry_after = 1.0
                time.sleep(min(retry_after + 0.25, 10))
                continue
            if not response.ok:
                body = response.text[:700].replace(self.token, "[REDACTED]")
                raise DiscordError(f"Discord HTTP {response.status_code} for {path}: {body}")
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise DiscordError(f"Discord rate limit retries exhausted for {path}")

    def discover(self) -> None:
        if not self.enabled:
            return
        guild_channels = self._request("GET", f"/guilds/{self.guild_id}/channels")
        by_name: dict[str, dict[str, Any]] = {}
        for channel in guild_channels:
            name = channel.get("name")
            if name and name.lower() not in by_name:
                by_name[name.lower()] = channel

        forum = next(
            (channel for channel in guild_channels
             if channel.get("name", "").lower() == CHANNEL_NAMES["forum"] and channel.get("type") == 15),
            None,
        )
        if not forum:
            raise DiscordError(
                "Could not find a Discord forum channel named 'trade-journal'. "
                "Confirm it is a Forum channel, not a normal text channel."
            )
        self.forum_id = forum["id"]

        for key, channel_name in CHANNEL_NAMES.items():
            channel = by_name.get(channel_name)
            if channel:
                self.channels[key] = channel["id"]

        for tag in forum.get("available_tags") or []:
            normalized = normalized_name(tag.get("name", ""))
            for key in TAG_KEYS:
                if normalized == key or normalized.endswith(f" {key}") or key in normalized:
                    self.tag_ids.setdefault(key, tag["id"])

        missing_tags = sorted(key for key in ("OPEN", "WIN", "LOSS", "SCRATCH") if key not in self.tag_ids)
        if missing_tags:
            raise DiscordError(f"Missing required trade-journal forum tags: {', '.join(missing_tags)}")
        self.ready = True

    def send_channel(
        self,
        logical_name: str,
        *,
        content: str = "",
        embed: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return None
        payload: dict[str, Any] = {"allowed_mentions": {"parse": []}}
        if content:
            payload["content"] = content[:2000]
        if embed:
            payload["embeds"] = [embed]
        return self._request("POST", f"/channels/{channel_id}/messages", payload)

    def upsert_channel_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        state_key: str,
        content: str,
    ) -> None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return
        messages = state.setdefault("messages", {})
        message_id = str(messages.get(state_key) or "")
        payload = {
            "content": content[:2000],
            "embeds": [],
            "allowed_mentions": {"parse": []},
        }
        if message_id:
            try:
                self._request(
                    "PATCH",
                    f"/channels/{channel_id}/messages/{message_id}",
                    payload,
                )
                return
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        created = self._request("POST", f"/channels/{channel_id}/messages", payload)
        if isinstance(created, dict) and created.get("id"):
            messages[state_key] = created["id"]

    def create_trade_thread(self, row: dict[str, str], status: str = "OPEN") -> str:
        if not self.ready:
            return ""
        tag_id = self.tag_ids.get(status) or self.tag_ids.get("OPEN")
        payload = {
            "name": trade_title(row)[:100],
            "auto_archive_duration": 1440,
            "applied_tags": [tag_id] if tag_id else [],
            "message": {
                "content": entry_alert_text(row),
                "allowed_mentions": {"parse": []},
            },
        }
        created = self._request("POST", f"/channels/{self.forum_id}/threads", payload)
        thread_id = created.get("id", "")
        if thread_id:
            row["discord_thread_id"] = thread_id
            row["discord_status"] = status
            row["discord_format_version"] = DISCORD_FORMAT_VERSION
            row["last_discord_signal"] = "OPEN"
            row["last_discord_pl_pct"] = row.get("current_pl_pct") or "0.0"
            row["last_discord_update_at"] = now_ct().isoformat()
        return thread_id

    def refresh_trade_thread(self, row: dict[str, str]) -> None:
        thread_id = row.get("discord_thread_id", "")
        if not self.ready or not thread_id:
            return
        self._request("PATCH", f"/channels/{thread_id}", {"name": trade_title(row)[:100]})
        self._request(
            "PATCH",
            f"/channels/{thread_id}/messages/{thread_id}",
            {"content": entry_alert_text(row), "embeds": [], "allowed_mentions": {"parse": []}},
        )
        row["discord_format_version"] = DISCORD_FORMAT_VERSION

    def send_thread(self, thread_id: str, content: str) -> None:
        if not self.ready or not thread_id:
            return
        self._request(
            "POST",
            f"/channels/{thread_id}/messages",
            {"content": content[:2000], "allowed_mentions": {"parse": []}},
        )

    def set_thread_status(self, thread_id: str, status: str, archive: bool = False) -> None:
        if not self.ready or not thread_id:
            return
        payload: dict[str, Any] = {}
        tag_id = self.tag_ids.get(status)
        if tag_id:
            payload["applied_tags"] = [tag_id]
        if archive:
            payload["archived"] = True
        if payload:
            self._request("PATCH", f"/channels/{thread_id}", payload)


def safe_discord_call(label: str, callback: Any) -> None:
    try:
        callback()
    except DiscordError as exc:
        print(f"Discord {label} failed: {exc}", file=sys.stderr)


def embed_field(name: str, value: Any, inline: bool = True) -> dict[str, Any]:
    rendered = str(value) if value not in (None, "") else "—"
    return {"name": name[:256], "value": rendered[:1024], "inline": inline}


def setup_embed(row: dict[str, str]) -> dict[str, Any]:
    play_type = row.get("play_type", "")
    kind = row.get("call_or_put", "").upper()
    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row["strike"])
        legs = f"SELL {fmt_strike(sell_strike)} {kind}\nBUY {fmt_strike(buy_strike)} {kind}"
        strategy = f"{kind} credit spread"
        entry = f"${parse_entry_price(row):.2f} credit"
    else:
        legs = f"BUY {row.get('strike')} {kind}"
        strategy = f"{play_type.title()} long {kind.lower()}"
        entry = f"${parse_entry_price(row):.2f} debit"

    max_profit = row.get("max_profit", "")
    if max_profit and max_profit != "UNLIMITED":
        max_profit = fmt_money(as_float(max_profit))
    max_risk = fmt_money(as_float(row.get("max_risk")))
    theta = as_float(row.get("theta_at_entry"))
    iv = as_float(row.get("iv_at_entry"))
    iv_text = "—" if iv is None else f"{iv * 100:.1f}%"

    return {
        "title": f"📈 {row.get('trade_id')} | Opened",
        "description": "",
        "color": 0x5865F2,
        "fields": [
            embed_field("Strategy", strategy),
            embed_field("Expiration", row.get("expiration")),
            embed_field("Entry", entry),
            embed_field("Legs", legs, False),
            embed_field("Maximum profit", max_profit),
            embed_field("Maximum risk", max_risk),
            embed_field("Break-even", f"${as_float(row.get('breakeven'), 0):.2f}"),
            embed_field("Delta", row.get("delta_at_entry")),
            embed_field("Estimated POP", f"{as_float(row.get('pop_estimate'), 0):.1f}%"),
            embed_field("Theta", "—" if theta is None else f"{theta:+.4f}/day"),
            embed_field("IV", iv_text),
            embed_field("Entry OI", row.get("open_interest_at_entry")),
            embed_field("Bid/ask width", f"${as_float(row.get('bid_ask_width_at_entry'), 0):.2f}"),
            embed_field(
                "Management",
                "50% credit capture / 2× credit stop" if play_type == "SPREAD" else "+22.5% target / -22.5% stop",
                False,
            ),
        ],
        "footer": {"text": "Tradysquids TradeBot"},
        "timestamp": row.get("timestamp") or now_ct().isoformat(),
    }


def update_embed(row: dict[str, str], evaluation: dict[str, Any]) -> dict[str, Any]:
    signal = evaluation.get("signal", "HOLD")
    pnl_pct = as_float(evaluation.get("pl_pct"))
    color = 0x57F287 if (pnl_pct or 0) > 0 else 0xED4245 if (pnl_pct or 0) < 0 else 0xFEE75C
    return {
        "title": f"{row.get('trade_id')} | {signal}",
        "color": color,
        "fields": [
            embed_field("Current mark", fmt_money((as_float(evaluation.get("mark"), 0) or 0) * 100)),
            embed_field("Open P&L", fmt_money(as_float(evaluation.get("pl_dollars")))),
            embed_field("Return", fmt_pct(pnl_pct)),
            embed_field("MFE", fmt_pct(as_float(row.get("max_favorable_pct")))),
            embed_field("MAE", fmt_pct(as_float(row.get("max_adverse_pct")))),
            embed_field("Action", signal),
        ],
        "footer": {"text": "15-minute position update"},
        "timestamp": now_ct().isoformat(),
    }


def close_embed(row: dict[str, str], evaluation: dict[str, Any]) -> dict[str, Any]:
    outcome = row.get("outcome", "CLOSED")
    colors = {"WIN": 0x57F287, "LOSS": 0xED4245, "SCRATCH": 0x95A5A6}
    return {
        "title": f"{row.get('trade_id')} | {outcome}",
        "description": f"Closed by scanner rule: **{evaluation.get('signal', 'CLOSE')}**",
        "color": colors.get(outcome, 0x95A5A6),
        "fields": [
            embed_field("Realized P&L", fmt_money(as_float(evaluation.get("pl_dollars")))),
            embed_field("Return", fmt_pct(as_float(evaluation.get("pl_pct")))),
            embed_field("MFE", fmt_pct(as_float(row.get("max_favorable_pct")))),
            embed_field("MAE", fmt_pct(as_float(row.get("max_adverse_pct")))),
            embed_field("Opened", (row.get("timestamp") or "")[:16].replace("T", " ")),
            embed_field("Closed", (row.get("closed_at") or "")[:16].replace("T", " ")),
        ],
        "footer": {"text": "Tradysquids TradeBot"},
        "timestamp": row.get("closed_at") or now_ct().isoformat(),
    }


def notify_webhook(lines: list[str], title: str | None = None) -> None:
    if not DISCORD_WEBHOOK_URL or not lines:
        return
    content = (f"**{title}**\n" if title else "") + "\n".join(lines)
    try:
        response = SESSION.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content[:1900], "allowed_mentions": {"parse": []}},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Discord webhook fallback failed: {exc}", file=sys.stderr)


def sync_existing_open_threads(rows: list[dict[str, str]], discord: DiscordTracker) -> int:
    if not DISCORD_SYNC_EXISTING_OPEN or not discord.ready:
        return 0
    created = 0
    for row in open_rows(rows):
        try:
            if row.get("discord_thread_id"):
                if row.get("discord_format_version") != DISCORD_FORMAT_VERSION:
                    discord.refresh_trade_thread(row)
                continue
            thread_id = discord.create_trade_thread(row, "OPEN")
            if thread_id:
                created += 1
                link = thread_link(thread_id)
                discord.send_channel("entry", content=entry_alert_text(row, link))
        except DiscordError as exc:
            print(f"Could not sync Discord thread for {row.get('trade_id')}: {exc}", file=sys.stderr)
    return created

def should_post_update(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> bool:
    signal = evaluation.get("signal", "HOLD")
    previous_signal = row.get("last_discord_signal") or ""
    if signal != previous_signal:
        return True
    current_pct = as_float(evaluation.get("pl_pct"))
    previous_pct = as_float(row.get("last_discord_pl_pct"))
    if current_pct is not None and previous_pct is not None:
        if abs(current_pct - previous_pct) >= DISCORD_PL_CHANGE_THRESHOLD:
            return True
    previous_update = parse_iso(row.get("last_discord_update_at"))
    return previous_update is None or timestamp - previous_update >= timedelta(minutes=DISCORD_HEARTBEAT_MINUTES)


def post_material_update(row: dict[str, str], evaluation: dict[str, Any], discord: DiscordTracker, timestamp: datetime) -> None:
    if not discord.ready or not row.get("discord_thread_id") or not should_post_update(row, evaluation, timestamp):
        return
    content = position_update_text(row, evaluation)
    discord.send_thread(row["discord_thread_id"], content)
    discord.send_channel(
        "updates",
        content=f"{content}\n🔗 {thread_link(row['discord_thread_id'])}",
    )
    status = "HOLDING"
    if evaluation.get("signal") == "TAKE PROFIT":
        status = "TARGET HIT"
    elif evaluation.get("signal") == "STOP OUT":
        status = "STOP WARNING"
    discord.set_thread_status(row["discord_thread_id"], status)
    row["discord_status"] = status
    row["last_discord_signal"] = evaluation.get("signal", "HOLD")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 1)
    row["last_discord_update_at"] = timestamp.isoformat()

def post_close(row: dict[str, str], evaluation: dict[str, Any], discord: DiscordTracker) -> None:
    if not discord.ready:
        return
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    content = close_alert_text(row, evaluation, link)
    if thread_id:
        discord.send_thread(thread_id, close_alert_text(row, evaluation))
        discord.set_thread_status(thread_id, row["outcome"], archive=True)
    discord.send_channel("exit", content=content)
    result_channel = {"WIN": "wins", "LOSS": "losses", "SCRATCH": "scratches"}.get(row["outcome"])
    if result_channel:
        discord.send_channel(result_channel, content=content)
    row["discord_status"] = row["outcome"]
    row["last_discord_signal"] = evaluation.get("signal", "CLOSE")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 1)
    row["last_discord_update_at"] = row.get("closed_at") or now_ct().isoformat()


def post_new_trade(row: dict[str, str], discord: DiscordTracker) -> None:
    if not discord.ready:
        return
    thread_id = discord.create_trade_thread(row, "OPEN")
    link = thread_link(thread_id)
    content = entry_alert_text(row, link)
    discord.send_channel("qualified", content=content)
    discord.send_channel("entry", content=content)


# ---------------------------------------------------------------------------
# Discord server pages and performance reporting
# ---------------------------------------------------------------------------


def closed_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}
    ]


def rows_closed_on(rows: list[dict[str, str]], target_date: date) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in closed_rows(rows):
        closed_at = parse_iso(row.get("closed_at"))
        if closed_at and closed_at.date() == target_date:
            selected.append(row)
    return selected


def rows_closed_between(
    rows: list[dict[str, str]],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in closed_rows(rows):
        closed_at = parse_iso(row.get("closed_at"))
        if closed_at and start_date <= closed_at.date() <= end_date:
            selected.append(row)
    return selected


def result_metrics(rows: list[dict[str, str]]) -> dict[str, float]:
    wins = [row for row in rows if row.get("outcome") == "WIN"]
    losses = [row for row in rows if row.get("outcome") == "LOSS"]
    scratches = [row for row in rows if row.get("outcome") == "SCRATCH"]
    decided = wins + losses

    pct_values = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in rows)
        if value is not None
    ]
    dollar_values = [
        value for value in (as_float(row.get("current_pl_dollars")) for row in rows)
        if value is not None
    ]
    win_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in wins)
        if value is not None
    ]
    loss_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in losses)
        if value is not None
    ]

    return {
        "wins": float(len(wins)),
        "losses": float(len(losses)),
        "scratches": float(len(scratches)),
        "closed": float(len(rows)),
        "win_rate": (len(wins) / len(decided) * 100) if decided else 0.0,
        "total_pnl": sum(dollar_values),
        "average_pct": (sum(pct_values) / len(pct_values)) if pct_values else 0.0,
        "average_win_pct": (sum(win_pcts) / len(win_pcts)) if win_pcts else 0.0,
        "average_loss_pct": (sum(loss_pcts) / len(loss_pcts)) if loss_pcts else 0.0,
        "expectancy_pct": (
            sum(as_float(row.get("pct_gain_loss"), 0.0) or 0.0 for row in decided) / len(decided)
        ) if decided else 0.0,
    }


def compact_result_line(row: dict[str, str]) -> str:
    trade_id = row.get("trade_id", "F-UNKNOWN")
    outcome = row.get("outcome", "CLOSED")
    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    dollars = as_float(row.get("current_pl_dollars"))
    play_type = row.get("play_type", "")
    kind = row.get("call_or_put", "").upper()
    result = f"{pct:+.1f}%"
    if dollars is not None:
        result += f" / {fmt_money(dollars)}"
    return f"• **{trade_id}** {play_type} {kind} · {outcome} · {result}"


def format_performance_stats(rows: list[dict[str, str]]) -> str:
    completed = closed_rows(rows)
    metrics = result_metrics(completed)
    open_count = len(open_rows(rows))
    return "\n".join([
        "## Performance",
        (
            f"**{int(metrics['wins'])}W-{int(metrics['losses'])}L-"
            f"{int(metrics['scratches'])}S** · "
            f"Win rate **{metrics['win_rate']:.1f}%**"
        ),
        f"Total P/L **{fmt_money(metrics['total_pnl'])}** · Open **{open_count}**",
        (
            f"Avg win **{metrics['average_win_pct']:+.1f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.1f}%** · "
            f"Expectancy **{metrics['expectancy_pct']:+.1f}%**"
        ),
        f"Updated {now_ct().strftime('%m/%d/%y %-I:%M %p CT')}",
    ])[:2000]


def format_strategy_breakdown(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        label = f"{row.get('play_type', 'PLAY')} {row.get('call_or_put', '').upper()}".strip()
        groups.setdefault(label, []).append(row)

    lines = ["## Strategy Breakdown"]
    if not groups:
        lines.append("No completed trades yet.")
    else:
        ranked: list[tuple[float, str]] = []
        for label, group in groups.items():
            metrics = result_metrics(group)
            line = (
                f"**{label}** · {int(metrics['wins'])}W-{int(metrics['losses'])}L-"
                f"{int(metrics['scratches'])}S · {metrics['win_rate']:.0f}% · "
                f"{metrics['expectancy_pct']:+.1f}% avg"
            )
            ranked.append((metrics["expectancy_pct"], line))
        for _, line in sorted(ranked, key=lambda item: item[0], reverse=True):
            lines.append(line)
    lines.append(f"Updated {now_ct().strftime('%m/%d/%y %-I:%M %p CT')}")
    return "\n".join(lines)[:2000]


def format_daily_recap(rows: list[dict[str, str]], report_date: date) -> str:
    completed = rows_closed_on(rows, report_date)
    metrics = result_metrics(completed)
    lines = [
        f"## Daily Recap · {report_date.strftime('%m/%d/%y')}",
        (
            f"**{int(metrics['wins'])}W-{int(metrics['losses'])}L-"
            f"{int(metrics['scratches'])}S** · "
            f"P/L **{fmt_money(metrics['total_pnl'])}**"
        ),
    ]
    if completed:
        lines.extend(compact_result_line(row) for row in completed[-12:])
    else:
        lines.append("No trades closed.")
    lines.append(f"Open trades carried forward: **{len(open_rows(rows))}**")
    return "\n".join(lines)[:2000]


def format_weekly_report(rows: list[dict[str, str]], report_date: date) -> str:
    monday = report_date - timedelta(days=report_date.weekday())
    completed = rows_closed_between(rows, monday, report_date)
    metrics = result_metrics(completed)
    lines = [
        f"## Weekly Report · {monday.strftime('%m/%d')}–{report_date.strftime('%m/%d/%y')}",
        (
            f"**{int(metrics['wins'])}W-{int(metrics['losses'])}L-"
            f"{int(metrics['scratches'])}S** · "
            f"Win rate **{metrics['win_rate']:.1f}%**"
        ),
        (
            f"P/L **{fmt_money(metrics['total_pnl'])}** · "
            f"Expectancy **{metrics['expectancy_pct']:+.1f}%**"
        ),
        (
            f"Avg win **{metrics['average_win_pct']:+.1f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.1f}%**"
        ),
    ]
    if completed:
        best = max(completed, key=lambda row: as_float(row.get("pct_gain_loss"), -math.inf) or -math.inf)
        worst = min(completed, key=lambda row: as_float(row.get("pct_gain_loss"), math.inf) or math.inf)
        lines.append(f"Best: {compact_result_line(best)[2:]}")
        lines.append(f"Worst: {compact_result_line(worst)[2:]}")
    else:
        lines.append("No trades closed this week.")
    return "\n".join(lines)[:2000]


def static_server_pages() -> dict[str, str]:
    return {
        "welcome": "\n".join([
            "# Tradysquids TradeBot",
            "Ford options scans, entries, lifecycle updates, and results.",
            "Start with **#entry-alerts**. Open any linked journal thread for the full trade history.",
        ]),
        "strategy_rules": "\n".join([
            "# Strategy Rules",
            "• Ford only",
            f"• Credit-spread short delta: {SPREAD_SHORT_DELTA_MIN:.2f}–{SPREAD_SHORT_DELTA_MAX:.2f}",
            f"• Long-option delta: {SINGLE_LEG_DELTA_MIN:.2f}–{SINGLE_LEG_DELTA_MAX:.2f}",
            f"• Minimum open interest: {MIN_OPEN_INTEREST}",
            f"• Maximum new entries per scan: {MAX_NEW_PLAYS_PER_SCAN}",
            f"• Duplicate-entry cooldown: {REENTRY_COOLDOWN_MINUTES} minutes",
        ]),
        "risk_management": "\n".join([
            "# Risk Management",
            f"• Credit spreads: target {SPREAD_TAKE_PROFIT_PCT * 100:.0f}% credit capture",
            f"• Credit spreads: stop at {SPREAD_STOP_MULTIPLE:.1f}× entry credit",
            f"• Long options: target +{SINGLE_TAKE_PROFIT_PCT * 100:.1f}%",
            f"• Long options: stop -{SINGLE_STOP_PCT * 100:.1f}%",
            "• Every spread is defined-risk",
        ]),
        "server_guide": "\n".join([
            "# Server Guide",
            "**scanner-feed** — meaningful scan summaries",
            "**qualified-trades** — new qualified setups",
            "**entry-alerts** — compact entries",
            "**trade-journal** — one thread per trade",
            "**position-updates** — material P/L and signal changes",
            "**exit-alerts** — every closure",
            "**wins / losses / scratches** — final routing",
            "**performance** channels — daily, weekly, and strategy statistics",
            "**scanner-status / workflow-log / api-errors** — system health",
        ]),
        "admin_notes": "\n".join([
            "# Admin Notes",
            "Reserved for manual configuration changes, overrides, and maintenance notes.",
        ]),
    }


def ensure_static_server_pages(
    discord: DiscordTracker,
    state: dict[str, Any],
) -> None:
    if not discord.ready:
        return
    for logical_name, content in static_server_pages().items():
        discord.upsert_channel_message(
            logical_name,
            state,
            f"page:{logical_name}",
            content,
        )
    state["guide_version"] = "1"


def update_scanner_status(
    discord: DiscordTracker,
    state: dict[str, Any],
    *,
    market_open: bool,
    summary: str,
    rows: list[dict[str, str]],
    timestamp: datetime,
) -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    status = "🟢 MARKET OPEN" if market_open else "⚫ MARKET CLOSED"
    content = "\n".join([
        f"## {status}",
        summary,
        f"Open trades **{len(open_rows(rows))}** · Trigger **{event_name}** · Run **#{run_number}**",
        f"Last check {timestamp.strftime('%m/%d/%y %-I:%M:%S %p CT')}",
    ])
    discord.upsert_channel_message("status", state, "scanner-status", content)


def post_workflow_log(
    discord: DiscordTracker,
    *,
    timestamp: datetime,
    result: str,
) -> None:
    if not discord.ready:
        return
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    icon = "✅" if result.startswith("OK") else "⚠️"
    discord.send_channel(
        "workflow_log",
        content=(
            f"{icon} `{timestamp.strftime('%m/%d %H:%M:%S CT')}` "
            f"#{run_number} {event_name} · {result}"
        ),
    )


def update_performance_pages(
    discord: DiscordTracker,
    state: dict[str, Any],
    rows: list[dict[str, str]],
) -> None:
    if not discord.ready:
        return
    discord.upsert_channel_message(
        "performance_stats",
        state,
        "performance-stats",
        format_performance_stats(rows),
    )
    discord.upsert_channel_message(
        "strategy_breakdown",
        state,
        "strategy-breakdown",
        format_strategy_breakdown(rows),
    )


def post_reports_if_due(
    discord: DiscordTracker,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
) -> None:
    if not discord.ready:
        return

    report_date = timestamp.date()
    date_key = report_date.isoformat()
    if state.get("daily_report_date") != date_key:
        discord.send_channel(
            "daily_recap",
            content=format_daily_recap(rows, report_date),
        )
        state["daily_report_date"] = date_key

    iso_year, iso_week, _ = report_date.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    if report_date.weekday() == 4 and state.get("weekly_report_key") != week_key:
        discord.send_channel(
            "weekly_report",
            content=format_weekly_report(rows, report_date),
        )
        state["weekly_report_key"] = week_key


# ---------------------------------------------------------------------------
# Dashboard

# ---------------------------------------------------------------------------


def render_dashboard(
    spot_quote: dict[str, Any] | None,
    rows: list[dict[str, str]],
    latest_summary: str,
) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    last = as_float((spot_quote or {}).get("last"))
    previous_close = as_float((spot_quote or {}).get("prevclose"))
    change = last - previous_close if last is not None and previous_close is not None else None
    change_pct = change / previous_close * 100 if change is not None and previous_close else None

    def esc(value: Any) -> str:
        return html.escape(str(value))

    open_items: list[str] = []
    watch_items: list[str] = []
    closed_items: list[str] = []

    for row in rows:
        outcome = row.get("outcome", "OPEN")
        kind = row.get("call_or_put", "").upper()
        if row.get("play_type") == "SPREAD":
            sell_strike, buy_strike = parse_spread_strikes(row["strike"])
            title = f"{esc(row['trade_id'])} · {kind} CREDIT {sell_strike:g}/{buy_strike:g} · {esc(row['expiration'])}"
            legs = f"<div class='legrow'><b>SELL</b> {sell_strike:g} {kind}</div><div class='legrow'><b>BUY</b> {buy_strike:g} {kind}</div>"
        else:
            title = f"{esc(row['trade_id'])} · {esc(row['play_type'])} {kind} {esc(row['strike'])} · {esc(row['expiration'])}"
            legs = ""

        risk_line = (
            f"Entry {esc(row.get('cost_or_credit',''))} · Max profit {esc(row.get('max_profit','—'))} · "
            f"Max risk {esc(row.get('max_risk','—'))} · BE {esc(row.get('breakeven','—'))}"
        )
        watch_items.append(
            f"<div class='play-group'><div class='play-title'>{title}</div>"
            f"<div class='plsub'>{risk_line}</div>{legs}</div>"
        )

        if outcome == "OPEN":
            pnl_pct = as_float(row.get("current_pl_pct"))
            pnl_dollars = as_float(row.get("current_pl_dollars"))
            pnl_class = "pos" if (pnl_pct or 0) > 0 else "neg" if (pnl_pct or 0) < 0 else "zero"
            open_items.append(
                f"<div class='play-group'><div class='play-head'><div class='play-title'>{title}</div>"
                f"<div class='pl {pnl_class}'>{fmt_money(pnl_dollars)} ({fmt_pct(pnl_pct)})</div></div>"
                f"<div class='plsub'>Signal: <b>{esc(row.get('last_signal','HOLD'))}</b> · "
                f"MFE {fmt_pct(as_float(row.get('max_favorable_pct')))} · MAE {fmt_pct(as_float(row.get('max_adverse_pct')))}</div>"
                f"{legs}</div>"
            )
        else:
            badge_class = "badge-win" if outcome == "WIN" else "badge-loss" if outcome == "LOSS" else "badge-scratch"
            closed_items.append(
                f"<div class='play-group closed'><div class='play-head'><div class='play-title'>{title}</div>"
                f"<div><span class='badge {badge_class}'>{esc(outcome)}</span> "
                f"<span class='pl'>{fmt_pct(as_float(row.get('pct_gain_loss')))}</span></div></div>"
                f"<div class='plsub'>Opened {esc((row.get('timestamp') or '')[:16].replace('T',' '))} · "
                f"Closed {esc((row.get('closed_at') or '')[:16].replace('T',' '))} · "
                f"MFE {fmt_pct(as_float(row.get('max_favorable_pct')))} · MAE {fmt_pct(as_float(row.get('max_adverse_pct')))}</div></div>"
            )

    closed_rows = [row for row in rows if row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}]
    wins = sum(row.get("outcome") == "WIN" for row in closed_rows)
    losses = sum(row.get("outcome") == "LOSS" for row in closed_rows)
    scratches = sum(row.get("outcome") == "SCRATCH" for row in closed_rows)
    win_rate = wins / (wins + losses) * 100 if wins + losses else None

    spot_html = "<div class='muted'>Quote unavailable</div>"
    if last is not None:
        direction = "up" if (change or 0) > 0 else "down" if (change or 0) < 0 else "flat"
        spot_html = f"<div class='price'>${last:.2f}</div><div class='chg {direction}'>{change:+.2f} ({change_pct:+.2f}%)</div>" if change is not None else f"<div class='price'>${last:.2f}</div>"

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta http-equiv='refresh' content='900'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<style>
:root {{ color-scheme: dark; }}
body {{ font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0f1117; color:#e7e9ee; padding:20px; max-width:900px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .sub,.plsub,.muted,.footer {{ color:#9aa3b2; }} .sub {{ font-size:13px; margin-bottom:16px; }}
.card,.play-group {{ background:#171a22; border:1px solid #2a3040; border-radius:12px; }} .card {{ padding:16px; margin-bottom:16px; }}
.card h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:#9aa3b2; margin:0 0 10px; }}
.price {{ font-size:30px; font-weight:750; }} .chg,.pl {{ font-weight:700; }} .up,.pos {{ color:#3ddc97; }} .down,.neg {{ color:#ff6b6b; }} .flat,.zero {{ color:#b8bfcc; }}
.tabs {{ display:flex; flex-wrap:wrap; gap:6px; margin:0 0 14px; border-bottom:1px solid #2a3040; }}
.tab-btn {{ border:0; background:none; color:#8c95a5; padding:10px 12px; cursor:pointer; font-weight:700; border-bottom:2px solid transparent; }}
.tab-btn.active {{ color:#fff; border-bottom-color:#7c6cf2; }} .tab-panel {{ display:none; }} .tab-panel.active {{ display:block; }}
.play-group {{ border-left:4px solid #7c6cf2; padding:12px 14px; margin-bottom:10px; }} .play-group.closed {{ border-left-color:#657080; }}
.play-head {{ display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; }} .play-title {{ font-size:13px; font-weight:750; }}
.plsub,.legrow {{ font-size:12px; margin-top:5px; }} .badge {{ border-radius:999px; padding:2px 8px; font-size:11px; font-weight:800; }}
.badge-win {{ background:#173d2e; color:#57e5a1; }} .badge-loss {{ background:#462328; color:#ff8a91; }} .badge-scratch {{ background:#343945; color:#c1c7d0; }}
.footer {{ font-size:11px; margin-top:10px; }}
</style></head><body>
<h1>Tradysquids · Ford Options Desk</h1>
<div class='sub'>Tradier market data · refreshed every 15 minutes · last build {now_ct().strftime('%Y-%m-%d %H:%M %Z')}</div>
<div class='card'><h2>Ford spot</h2>{spot_html}</div>
<div class='tabs'>
<button class='tab-btn active' data-tab='open'>Open ({len(open_items)})</button>
<button class='tab-btn' data-tab='watch'>All plays ({len(watch_items)})</button>
<button class='tab-btn' data-tab='closed'>Closed · {wins}W-{losses}L-{scratches}S ({'—' if win_rate is None else f'{win_rate:.0f}%'})</button>
</div>
<div id='tab-open' class='tab-panel active'>{''.join(open_items) if open_items else "<div class='muted'>No open plays.</div>"}</div>
<div id='tab-watch' class='tab-panel'>{''.join(watch_items) if watch_items else "<div class='muted'>No plays logged.</div>"}</div>
<div id='tab-closed' class='tab-panel'>{''.join(reversed(closed_items)) if closed_items else "<div class='muted'>No closed results.</div>"}</div>
<div class='card'><h2>Latest run</h2><div class='muted'>{esc(latest_summary)}</div><div class='footer'>GitHub Actions schedule: every 15 minutes. GitHub can delay scheduled jobs; protective exits must not rely on this scanner.</div></div>
<script>
document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {{
 document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
 document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
 btn.classList.add('active'); document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}}));
</script></body></html>"""
    DASHBOARD_PATH.write_text(html_doc, encoding="utf-8")

# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def initialize_discord() -> DiscordTracker:
    tracker = DiscordTracker(DISCORD_BOT_TOKEN, DISCORD_GUILD_ID)
    if tracker.enabled:
        tracker.discover()
    return tracker


def scan_candidates(spot_price: float) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    expirations = get_expirations(TICKER)
    near_expirations, swing_expirations = pick_expirations(expirations, now_ct().date())
    candidate_expirations: list[tuple[str, str]] = []
    if near_expirations:
        candidate_expirations.append((near_expirations[0], "NEAR"))
    if swing_expirations:
        candidate_expirations.append((swing_expirations[0], "SWING"))

    candidates: list[dict[str, Any]] = []
    quote_map: dict[str, dict[str, Any]] = {}
    for expiration, bucket in candidate_expirations:
        allowed_strikes = set(filter_strikes(get_strikes(TICKER, expiration), spot_price))
        chain = [option for option in get_chain(TICKER, expiration) if float(option.get("strike", -1)) in allowed_strikes]
        for option in chain:
            if option.get("symbol"):
                quote_map[option["symbol"]] = option
        calls = [option for option in chain if option.get("option_type") == "call"]
        puts = [option for option in chain if option.get("option_type") == "put"]
        if bucket == "NEAR":
            candidates.extend(scan_credit_spreads(calls, "call", expiration))
            candidates.extend(scan_credit_spreads(puts, "put", expiration))
            candidates.extend(scan_single_legs(calls, "call", expiration, "REGULAR"))
            candidates.extend(scan_single_legs(puts, "put", expiration, "REGULAR"))
        else:
            candidates.extend(scan_single_legs(calls, "call", expiration, "SWING"))
            candidates.extend(scan_single_legs(puts, "put", expiration, "SWING"))
    return candidates, quote_map


def report_error(discord: DiscordTracker | None, message: str) -> None:
    safe_message = message.replace(TRADIER_TOKEN, "[REDACTED]").replace(DISCORD_BOT_TOKEN, "[REDACTED]")
    print(safe_message, file=sys.stderr)
    if discord and discord.ready:
        safe_discord_call("error alert", lambda: discord.send_channel("errors", content=f"🚨 **Ford scanner error**\n```{safe_message[:1500]}```"))
    notify_webhook([safe_message[:1500]], title="Ford scanner error")


def main() -> int:
    timestamp = now_ct()
    rows = read_log()
    write_log(rows)  # immediately migrate old CSV headers/IDs safely

    discord: DiscordTracker | None = None
    try:
        discord = initialize_discord()
    except DiscordError as exc:
        report_error(None, f"TradeBot setup failed: {exc}")
        discord = DiscordTracker("", "")

    report_state = read_report_state()
    safe_discord_call(
        "server pages",
        lambda: ensure_static_server_pages(discord, report_state),
    )
    safe_discord_call(
        "performance pages",
        lambda: update_performance_pages(discord, report_state, rows),
    )

    backfilled = sync_existing_open_threads(rows, discord)
    if backfilled:
        write_log(rows)
        safe_discord_call(
            "backfill status",
            lambda: discord.send_channel(
                "status",
                content=f"✅ TradeBot imported {backfilled} existing OPEN play(s) into #trade-journal.",
            ),
        )
        print(f"Discord backfill: created {backfilled} open-trade forum thread(s).")

    is_open, timestamp = market_is_open_now()
    if not is_open:
        closed_summary = (
            f"Market closed · maintenance sync complete · "
            f"{len(open_rows(rows))} open trade(s)"
        )
        safe_discord_call(
            "closed status",
            lambda: update_scanner_status(
                discord,
                report_state,
                market_open=False,
                summary=closed_summary,
                rows=rows,
                timestamp=timestamp,
            ),
        )
        safe_discord_call(
            "performance pages",
            lambda: update_performance_pages(discord, report_state, rows),
        )
        if timestamp.hour >= MARKET_CLOSE[0]:
            safe_discord_call(
                "scheduled reports",
                lambda: post_reports_if_due(discord, report_state, rows, timestamp),
            )
        safe_discord_call(
            "workflow log",
            lambda: post_workflow_log(
                discord,
                timestamp=timestamp,
                result=f"OK · market closed · {len(open_rows(rows))} open",
            ),
        )
        render_dashboard(None, rows, f"Market closed at {timestamp.strftime('%-I:%M %p %Z')}; maintenance sync only.")
        write_log(rows)
        write_report_state(report_state)
        print(f"Market closed ({timestamp.isoformat()}); maintenance sync complete.")
        return 0

    try:
        spot = get_quote(TICKER)
        if not spot or as_float(spot.get("last")) is None:
            raise TradierError("Ford spot quote was unavailable")
        spot_price = float(spot["last"])

        # Reprice every existing open play in one or more batched quote calls.
        currently_open = open_rows(rows)
        open_quote_map = get_quotes(symbols_for_rows(currently_open), include_greeks=True)
        closed_count = 0
        material_updates = 0
        for row in list(currently_open):
            evaluation = evaluate_open_row(row, open_quote_map, timestamp)
            if evaluation.get("pl_pct") is None:
                continue
            signal = evaluation.get("signal")
            if signal in {"STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE"}:
                close_row(row, evaluation, timestamp)
                safe_discord_call("close routing", lambda r=row, e=evaluation: post_close(r, e, discord))
                closed_count += 1
            else:
                before = row.get("last_discord_update_at")
                safe_discord_call("position update", lambda r=row, e=evaluation: post_material_update(r, e, discord, timestamp))
                if row.get("last_discord_update_at") != before:
                    material_updates += 1

        # Scan for new candidates and choose the highest-quality unique set.
        candidates, candidate_quote_map = scan_candidates(spot_price)
        eligible = [candidate for candidate in candidates if not recently_tracked(rows, candidate, timestamp)]
        eligible.sort(key=lambda candidate: candidate.get("score", 0), reverse=True)
        selected = eligible[:MAX_NEW_PLAYS_PER_SCAN]

        new_rows: list[dict[str, str]] = []
        for candidate in selected:
            row = candidate_to_row(candidate, rows, timestamp)
            rows.append(row)
            new_rows.append(row)
            safe_discord_call("new trade post", lambda r=row: post_new_trade(r, discord))

        # Give newly opened rows their initial zero-P&L values and preserve all state.
        all_quotes = {**open_quote_map, **candidate_quote_map}
        for row in new_rows:
            evaluation = evaluate_open_row(row, all_quotes, timestamp)
            if evaluation.get("pl_pct") is None:
                row["current_pl_pct"] = "0.0"
                row["current_pl_dollars"] = "0.0"

        write_log(rows)
        summary = (
            f"Spot ${spot_price:.2f} · {len(new_rows)} new play(s) · "
            f"{closed_count} closed · {material_updates} material update(s) · "
            f"{len(open_rows(rows))} open total."
        )
        render_dashboard(spot, rows, summary)
        safe_discord_call(
            "open status",
            lambda: update_scanner_status(
                discord,
                report_state,
                market_open=True,
                summary=summary,
                rows=rows,
                timestamp=timestamp,
            ),
        )
        safe_discord_call(
            "performance pages",
            lambda: update_performance_pages(discord, report_state, rows),
        )
        safe_discord_call(
            "workflow log",
            lambda: post_workflow_log(
                discord,
                timestamp=timestamp,
                result=f"OK · {summary}",
            ),
        )

        if discord.ready and (new_rows or closed_count):
            safe_discord_call("scanner feed", lambda: discord.send_channel("scanner_feed", content=f"📡 **Ford scan complete**\n{summary}"))
        elif not discord.ready and (new_rows or closed_count):
            notify_webhook([summary], title="Ford options scan")

        write_report_state(report_state)
        print(summary)
        return 0
    except (TradierError, DiscordError, requests.RequestException, ValueError, KeyError) as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        report_error(discord, error_text)
        safe_discord_call(
            "workflow error log",
            lambda: post_workflow_log(
                discord,
                timestamp=now_ct(),
                result=f"ERROR · {error_text[:120]}",
            ),
        )
        write_log(rows)
        write_report_state(report_state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
