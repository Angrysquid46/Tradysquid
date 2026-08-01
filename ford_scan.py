"""
Tradysquids dynamic options scanner + Discord paper-trade tracker.

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
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TICKER = os.environ.get("SCAN_TICKER", "F").strip().upper() or "F"
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "").strip()
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()

REPO_ROOT = Path(__file__).resolve().parent
SCANNER_CONFIG_PATH = REPO_ROOT / "config" / "scanner.json"


def configured(name: str, default: Any) -> Any:
    try:
        payload = json.loads(SCANNER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return payload.get(name, default)


STATE_DIR = REPO_ROOT / "state"
DOCS_DIR = REPO_ROOT / "docs"
LOG_PATH = STATE_DIR / "ford-plays-log.csv"
DASHBOARD_PATH = DOCS_DIR / "index.html"
REPORT_STATE_PATH = STATE_DIR / "discord-report-state.json"
CHART_PATH = DOCS_DIR / "ford-market-chart.svg"
CHART_SCREENSHOT_PATH = DOCS_DIR / "ford-market-chart.png"
TRADE_SNAPSHOT_DIR = DOCS_DIR / "trade-snapshots"
INTRADAY_SNAPSHOT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CHART_PUBLIC_URL = os.environ.get(
    "CHART_PUBLIC_URL",
    "https://angrysquid46.github.io/Tradysquid/ford-market-chart.svg",
).strip()

FORD_CIK = "0000037996"
FORD_IR_EVENTS_URL = "https://shareholder.ford.com/events/default.aspx"
SEC_FORMS = {"8-K", "10-Q", "10-K", "DEFA14A"}

MARKET_TZ = ZoneInfo("America/Chicago")
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)

# Candidate screening
MIN_OPEN_INTEREST = int(os.environ.get("MIN_OPEN_INTEREST", "100"))
MIN_OPTION_VOLUME = int(os.environ.get("MIN_OPTION_VOLUME", "1"))
MAX_BID_ASK_PCT = float(os.environ.get("MAX_BID_ASK_PCT", "0.25"))
# Retained only so legacy credit-spread rows/functions remain readable; new scans do not use them.
SPREAD_SHORT_DELTA_MIN = float(os.environ.get("SPREAD_SHORT_DELTA_MIN", "0.10"))
SPREAD_SHORT_DELTA_MAX = float(os.environ.get("SPREAD_SHORT_DELTA_MAX", "0.25"))
SINGLE_LEG_DELTA_MIN = float(os.environ.get("SINGLE_LEG_DELTA_MIN", "0.20"))
SINGLE_LEG_DELTA_MAX = float(os.environ.get("SINGLE_LEG_DELTA_MAX", "0.80"))
MAX_RISK_PER_TRADE = float(os.environ.get(
    "MAX_RISK_PER_TRADE", configured("max_position_risk_dollars", 100)
))
MAX_CONTRACT_ASK = float(os.environ.get(
    "MAX_CONTRACT_ASK", configured("max_contract_ask", 1.00)
))
MIN_SPREAD_CREDIT = float(os.environ.get("MIN_SPREAD_CREDIT", "0.05"))
STRIKE_BAND_PCT = float(os.environ.get("STRIKE_BAND_PCT", "0.12"))
MIN_DTE = int(os.environ.get("MIN_DTE", "21"))
MAX_DTE = int(os.environ.get("MAX_DTE", "45"))
REGULAR_MIN_DTE = int(os.environ.get("REGULAR_MIN_DTE", "7"))
REGULAR_MAX_DTE = int(os.environ.get("REGULAR_MAX_DTE", "20"))
REENTRY_COOLDOWN_MINUTES = int(os.environ.get("REENTRY_COOLDOWN_MINUTES", "1440"))

# Conservative directional-regime gate
RSI_MIN = float(os.environ.get("RSI_MIN", "45"))
RSI_MAX = float(os.environ.get("RSI_MAX", "68"))
MAX_EXTENSION_ABOVE_SMA20_PCT = float(os.environ.get("MAX_EXTENSION_ABOVE_SMA20_PCT", "0.05"))

# Management rules
SPREAD_STOP_MULTIPLE = float(os.environ.get(
    "SPREAD_STOP_MULTIPLE", configured("spread_stop_multiple", 2.0)
))
SPREAD_TAKE_PROFIT_PCT = float(os.environ.get(
    "SPREAD_TAKE_PROFIT_PCT", configured("spread_profit_target_pct", 0.50)
))
SPREAD_EXIT_DTE = int(os.environ.get("SPREAD_EXIT_DTE", "5"))
SINGLE_TAKE_PROFIT_PCT = float(os.environ.get(
    "SINGLE_TAKE_PROFIT_PCT", configured("single_leg_profit_target_pct", 0.20)
))
SINGLE_STOP_PCT = float(os.environ.get(
    "SINGLE_STOP_PCT", configured("single_leg_stop_pct", 0.15)
))
SCRATCH_BAND_PCT = float(os.environ.get("SCRATCH_BAND_PCT", "5.0"))

# Discord update throttling
DISCORD_PL_CHANGE_THRESHOLD = float(os.environ.get("DISCORD_PL_CHANGE_THRESHOLD", "10.0"))
DISCORD_HEARTBEAT_MINUTES = int(os.environ.get("DISCORD_HEARTBEAT_MINUTES", "15"))
DISCORD_SYNC_EXISTING_OPEN = os.environ.get("DISCORD_SYNC_EXISTING_OPEN", "true").lower() == "true"
DISCORD_MIGRATE_LEGACY_MESSAGES = os.environ.get(
    "DISCORD_MIGRATE_LEGACY_MESSAGES", "false"
).lower() == "true"
DISCORD_FORMAT_VERSION = "10"

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
    "exit_price",
    "entry_contract_value",
    "exit_contract_value",
    "result_price_source",
    "delta_at_entry",
    "theta_at_entry",
    "iv_at_entry",
    "pop_estimate",
    "max_profit",
    "max_risk",
    "breakeven",
    "open_interest_at_entry",
    "bid_ask_width_at_entry",
    "option_volume_at_entry",
    "setup_score",
    "setup_reason",
    "market_regime",
    "outcome",
    "pct_gain_loss",
    "realized_pl_dollars",
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
    "premarket": "premarket",
    "breaking_alerts": "breaking-alerts",
    "universe_watch": "universe-watch",
    "charts": "charts-and-levels",
    "intelligence": "market-regime",
    "market_pulse": "market-regime",
    "technicals": "charts-and-levels",
    "options_chain": "scanner-feed",
    "risk_desk": "scanner-controls",
    "news_events": "news-and-events",
    "sec_filings": "news-and-events",
    "research_summary": "strategy-results",
    "qualified": "new-positions",
    "entry": "new-positions",
    "updates": "held-positions",
    "exit": "held-positions",
    "wins": "wins",
    "losses": "losses",
    "scratches": "losses",
    "expired": "losses",
    "daily_recap": "performance-dashboard",
    "weekly_report": "performance-dashboard",
    "performance_stats": "performance-dashboard",
    "strategy_breakdown": "strategy-results",
    "ticker_results": "ticker-results",
    "learning_results": "learning-results",
    "examples_reviews": "examples-and-reviews",
    "status": "system-health",
    "errors": "provider-status",
    "workflow_log": "workflow-log",
    "admin_notes": "scanner-controls",
    "welcome": "welcome",
    "strategy_rules": "rules-and-risk",
    "risk_management": "rules-and-risk",
    "server_guide": "how-to-use-tradebot",
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

AUTOMATED_CHANNEL_KEYS = [
    "scanner_feed",
    "premarket",
    "breaking_alerts",
    "universe_watch",
    "charts",
    "intelligence",
    "market_pulse",
    "technicals",
    "options_chain",
    "risk_desk",
    "news_events",
    "sec_filings",
    "research_summary",
    "qualified",
    "entry",
    "updates",
    "exit",
    "wins",
    "losses",
    "scratches",
    "expired",
    "daily_recap",
    "weekly_report",
    "performance_stats",
    "strategy_breakdown",
    "ticker_results",
    "learning_results",
    "examples_reviews",
    "status",
    "errors",
    "workflow_log",
]

SYSTEM_CHANNEL_KEYS = {
    "status",
    "errors",
    "workflow_log",
    "admin_notes",
}

MANUAL_CHANNEL_KEYS = [
    "welcome",
    "strategy_rules",
    "risk_management",
    "server_guide",
    "admin_notes",
]

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def now_ct() -> datetime:
    return datetime.now(MARKET_TZ)


def portable_strftime(value: datetime, format_string: str) -> str:
    """Support GNU's non-padded hour token on Windows as well as Linux."""
    rendered = value.strftime(format_string.replace("%-I", "%I"))
    return re.sub(r"(?<!\d)0(\d)(?=:)", r"\1", rendered)


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
    """Display one-contract and aggregate dollar values as whole dollars."""
    if value is None:
        return "—"
    rounded = int(round(value))
    return f"-${abs(rounded):,}" if rounded < 0 else f"${rounded:,}"


def fmt_option_price(value: float | None, *, approximate: bool = False) -> str:
    """Options premiums and debits/credits are always displayed to two decimals."""
    if value is None:
        return "—"
    prefix = "≈" if approximate else ""
    return f"{prefix}${round(float(value), 2):.2f}"


def fmt_iv(value: float | None) -> str:
    if value is None or value <= 0:
        return "Unavailable"
    return f"{value * 100:.0f}%"


def fmt_oi(value: Any) -> str:
    amount = int(as_float(value, 0.0) or 0)
    return f"{amount:,}" if amount > 0 else "Unavailable"


def fmt_delta(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:+.2f}"



def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.0f}%"

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
        "message_hashes": {},
        "daily_report_date": "",
        "weekly_report_key": "",
        "guide_version": "",
        "routed_closed_trade_ids": [],
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
    if not isinstance(default.get("routed_closed_trade_ids"), list):
        default["routed_closed_trade_ids"] = []
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
        return round(direct, 2)
    raw = (row.get("cost_or_credit") or "").replace("credit", "").strip()
    return round(as_float(raw, 0.0) or 0.0, 2)


def exit_price(row: dict[str, str]) -> float | None:
    """Tracked closing premium/debit, normalized to an option-price cent."""
    stored = as_float(row.get("exit_price"))
    if stored is not None:
        return round(stored, 2)

    if row.get("outcome") not in {"WIN", "LOSS", "SCRATCH"}:
        return None

    entry = parse_entry_price(row)
    realized = as_float(row.get("realized_pl_dollars"))
    if realized is None:
        realized = as_float(row.get("current_pl_dollars"))
    if realized is None:
        pct = as_float(row.get("pct_gain_loss"))
        if pct is None:
            return None
        realized = entry * pct

    if row.get("play_type") == "SPREAD":
        return round(entry - (realized / 100), 2)
    return round(entry + (realized / 100), 2)


def entry_contract_value(row: dict[str, str]) -> float:
    return round(parse_entry_price(row) * 100)


def exit_contract_value(row: dict[str, str]) -> float | None:
    price = exit_price(row)
    return None if price is None else round(price * 100)

def result_is_reconstructed(row: dict[str, str]) -> bool:
    return row.get("result_price_source") == "RECONSTRUCTED"



def realized_pl_dollars(row: dict[str, str]) -> float:
    """One-contract result from cent-normalized entry and exit premiums."""
    entry = parse_entry_price(row)
    closing = exit_price(row)
    if closing is not None:
        if row.get("play_type") == "SPREAD":
            return round((entry - closing) * 100)
        return round((closing - entry) * 100)

    stored = as_float(row.get("realized_pl_dollars"))
    if stored is not None:
        return round(stored)

    current = as_float(row.get("current_pl_dollars"))
    if current is not None and row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}:
        return round(current)

    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    return round(entry * pct)

def result_amount_prefix(row: dict[str, str]) -> str:
    return "≈" if result_is_reconstructed(row) else ""


def result_price_details(row: dict[str, str]) -> tuple[float, float | None, float]:
    return parse_entry_price(row), exit_price(row), realized_pl_dollars(row)


def row_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("ticker", ""),
        row.get("play_type", ""),
        row.get("call_or_put", ""),
        row.get("strike", ""),
        row.get("expiration", ""),
    )


def trade_title(row: dict[str, str]) -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        return (
            f"{ticker} #{sequence} | {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)} "
            f"{kind} CREDIT | {expiration}"
        )

    strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
    return f"{ticker} #{sequence} | BUY {strike} {kind} | {expiration}"


def format_expiration(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (TypeError, ValueError):
        return value or "—"



def entry_alert_text(row: dict[str, str], include_link: str = "") -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry = parse_entry_price(row)
    breakeven = as_float(row.get("breakeven"))
    delta = as_float(row.get("delta_at_entry"))
    theta = as_float(row.get("theta_at_entry"))
    oi = row.get("open_interest_at_entry")
    iv = as_float(row.get("iv_at_entry"))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        stop = round(entry * SPREAD_STOP_MULTIPLE, 2)
        target = round(entry * (1 - SPREAD_TAKE_PROFIT_PCT), 2)
        stop_pl = round((entry - stop) * 100)
        target_pl = round((entry - target) * 100)
        price_line = (
            f"**Entry:** {fmt_option_price(entry)} CR ({fmt_money(entry * 100)})\n"
            f"**Target:** {fmt_option_price(target)} DB ({fmt_money(target_pl)})\n"
            f"**Stop:** {fmt_option_price(stop)} DB ({fmt_money(stop_pl)})"
        )
        risk_line = (
            f"**Max profit:** {fmt_money(as_float(row.get('max_profit')))}\n"
            f"**Max risk:** {fmt_money(as_float(row.get('max_risk')))}\n"
            f"**Break-even:** {fmt_option_price(breakeven)}"
        )
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        stop = round(entry * (1 - SINGLE_STOP_PCT), 2)
        target = round(entry * (1 + SINGLE_TAKE_PROFIT_PCT), 2)
        price_line = (
            f"**Entry:** {fmt_option_price(entry)} DB ({fmt_money(entry * 100)})\n"
            f"**Target:** {fmt_option_price(target)} CR ({fmt_money((target - entry) * 100)})\n"
            f"**Stop:** {fmt_option_price(stop)} CR ({fmt_money((stop - entry) * 100)})"
        )
        risk_line = (
            f"**Max risk:** {fmt_money(as_float(row.get('max_risk')))}\n"
            f"**Break-even:** {fmt_option_price(breakeven)}"
        )

    market_data = (
        f"**Delta:** {fmt_delta(delta)}\n"
        f"**IV:** {fmt_iv(iv)}\n"
        f"**OI:** {fmt_oi(oi)} *(open interest)*\n"
        f"**Volume:** {fmt_oi(row.get('option_volume_at_entry'))}\n"
        f"**Theta:** {'Unavailable' if theta is None else f'{theta:+.3f}/day'}"
    )
    lines = [
        f"## 🟦 {ticker} #{sequence} · ENTRY · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}",
        "### Entry Plan",
        price_line,
        "### Risk",
        risk_line,
        "### Market Data",
        market_data,
        "### Why This Qualified",
        (
            f"**Regime:** {row.get('market_regime') or 'CONTROLLED'}\n"
            f"**Score:** {row.get('setup_score') or '—'} *(ranking only; not a win probability)*\n"
            f"**Evidence:** {row.get('setup_reason') or 'Conservative directional filters passed'}"
        ),
    ]
    if include_link:
        lines.extend(["### Journal", f"[Open trade journal]({include_link})"])
    return "\n".join(lines)


def position_update_text(
    row: dict[str, str],
    evaluation: dict[str, Any],
    include_link: str = "",
) -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    signal = evaluation.get("signal") or row.get("last_signal") or "HOLD"
    entry = parse_entry_price(row)
    mark = as_float(evaluation.get("mark"), as_float(row.get("last_mark"), entry))
    if mark is None:
        mark = entry
    pl_dollars = as_float(evaluation.get("pl_dollars"), as_float(row.get("current_pl_dollars"), 0.0)) or 0.0
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("current_pl_pct"), 0.0)) or 0.0
    mfe = as_float(row.get("max_favorable_pct"), 0.0) or 0.0
    mae = as_float(row.get("max_adverse_pct"), 0.0) or 0.0

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        price_labels = (
            f"**Entry credit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})\n"
            f"**Current close debit:** {fmt_option_price(mark)} ({fmt_money(mark * 100)})"
        )
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        price_labels = (
            f"**Entry debit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})\n"
            f"**Current exit credit:** {fmt_option_price(mark)} ({fmt_money(mark * 100)})"
        )

    quote_note = evaluation.get("note") or ""
    state_label = "HOLD" if signal == "HOLD" else signal
    lines = [
        f"## 🟨 {ticker} #{sequence} · {state_label} · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}\n**Status:** {state_label}",
        "### Current Value",
        (
            f"{price_labels}\n"
            f"**Open P/L:** {fmt_money(pl_dollars)} ({fmt_pct(pl_pct)})"
        ),
        "### Excursion",
        f"**MFE:** {fmt_pct(mfe)}\n**MAE:** {fmt_pct(mae)}",
        "### Market Data",
        (
            f"**IV:** {fmt_iv(as_float(evaluation.get('iv'), as_float(row.get('iv_at_entry'))))}\n"
            f"**OI:** {fmt_oi(row.get('open_interest_at_entry'))} *(open interest)*\n"
            f"**Last checked:** {portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}"
        ),
    ]
    if quote_note:
        lines.extend(["### Quote Status", f"⚠️ {quote_note}"])
    if include_link:
        lines.extend(["### Journal", f"[Open trade journal]({include_link})"])
    return "\n".join(lines)


def close_alert_text(row: dict[str, str], evaluation: dict[str, Any], include_link: str = "") -> str:
    outcome = row.get("outcome", "CLOSED")
    icon = {"WIN": "🟩", "LOSS": "🟥", "SCRATCH": "⬜"}.get(outcome, "📕")
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry, closing, stored_pl = result_price_details(row)
    pl_dollars = round(as_float(evaluation.get("pl_dollars"), stored_pl) or 0.0)
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("pct_gain_loss"), 0.0)) or 0.0
    close_reason = evaluation.get("signal") or row.get("last_signal") or "CLOSED"
    approx = result_is_reconstructed(row)

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        entry_line = f"**Entry credit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})"
        exit_line = f"**Exit debit:** {fmt_option_price(closing, approximate=approx)} ({'≈' if approx else ''}{fmt_money(exit_contract_value(row))})"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        entry_line = f"**Entry debit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})"
        exit_line = f"**Exit credit:** {fmt_option_price(closing, approximate=approx)} ({'≈' if approx else ''}{fmt_money(exit_contract_value(row))})"

    closed_at = parse_iso(row.get("closed_at"))
    closed_text = portable_strftime(closed_at, "%m/%d/%y %-I:%M %p CT") if closed_at else "—"
    approx_prefix = "≈" if approx else ""
    lines = [
        f"## {icon} {ticker} #{sequence} · {outcome} · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}",
        "### Entry and Exit",
        f"{entry_line}\n{exit_line}",
        "### Result",
        (
            f"**Realized P/L:** {approx_prefix}{fmt_money(pl_dollars)}\n"
            f"**Return:** {fmt_pct(pl_pct)}\n"
            f"**Close reason:** {close_reason}\n"
            f"**MFE:** {fmt_pct(as_float(row.get('max_favorable_pct'), 0.0))}\n"
            f"**MAE:** {fmt_pct(as_float(row.get('max_adverse_pct'), 0.0))}"
        ),
        "### Timing",
        f"**Closed:** {closed_text}",
    ]
    if include_link:
        lines.extend(["### Journal", f"[Open completed trade journal]({include_link})"])
    return "\n".join(lines)


def qualified_trade_text(row: dict[str, str], include_link: str = "") -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry = parse_entry_price(row)
    pop = as_float(row.get("pop_estimate"))
    delta = as_float(row.get("delta_at_entry"))
    iv = as_float(row.get("iv_at_entry"))
    oi = row.get("open_interest_at_entry")
    width = as_float(row.get("bid_ask_width_at_entry"))
    volume = row.get("option_volume_at_entry")

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        price = f"{fmt_option_price(entry)} CR ({fmt_money(entry * 100)})"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"{play_type} LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        price = f"{fmt_option_price(entry)} DB ({fmt_money(entry * 100)})"

    lines = [
        f"## 🟪 {ticker} #{sequence} · QUALIFIED · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}",
        "### Entry",
        f"**Price:** {price}",
        "### Filter Data",
        (
            f"**Delta:** {fmt_delta(delta)}\n"
            f"**Delta proxy:** {fmt_pct(pop)} *(not a guaranteed win rate)*\n"
            f"**IV:** {fmt_iv(iv)}\n"
            f"**OI:** {fmt_oi(oi)} *(open interest)*\n"
            f"**Volume:** {fmt_oi(volume)}\n"
            f"**Bid/ask width:** {fmt_option_price(width)}"
        ),
        "### Why This Qualified",
        row.get("setup_reason") or "Conservative directional filters passed.",
    ]
    if include_link:
        lines.extend(["### Journal", f"[Open trade journal]({include_link})"])
    return "\n".join(lines)


def candidate_brief(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("call_or_put", "")).upper()
    play_type = str(candidate.get("play_type", "PLAY")).upper()
    expiration = format_expiration(str(candidate.get("expiration", "")))
    entry = as_float(candidate.get("entry_price"), 0.0) or 0.0
    score = as_float(candidate.get("score"), 0.0) or 0.0
    iv = as_float(candidate.get("iv"))
    oi = candidate.get("open_interest")
    if play_type == "SPREAD":
        setup = f"{kind} CREDIT {candidate.get('strike', '—')}"
        price = f"{fmt_option_price(entry)} CR"
    else:
        setup = f"{play_type} {kind} {candidate.get('strike', '—')}"
        price = f"{fmt_option_price(entry)} DB"
    return (
        f"• **{setup}** · EXP {expiration} · {price} · "
        f"IV {fmt_iv(iv)} · OI {fmt_oi(oi)} · score {score:.0f}"
    )

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


def get_daily_history(symbol: str, days: int = 90) -> list[dict[str, Any]]:
    end = now_ct().date()
    start = end - timedelta(days=days)
    data = tradier_get(
        "/markets/history",
        {
            "symbol": symbol,
            "interval": "daily",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )
    values = data.get("history", {}).get("day")
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def get_intraday_history(
    symbol: str,
    interval: str = "5min",
) -> list[dict[str, Any]]:
    """Return today's intraday bars when Tradier supplies time-and-sales data."""
    today = now_ct().date().isoformat()
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": f"{today} 08:30",
            "end": f"{today} 15:00",
            "session_filter": "open",
        },
    )
    values = data.get("series", {}).get("data")
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def simple_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def relative_strength_index(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [current - previous for previous, current in zip(values[-period - 1:-1], values[-period:])]
    gains = sum(max(change, 0) for change in changes) / period
    losses = sum(max(-change, 0) for change in changes) / period
    if losses == 0:
        return 100.0
    return 100 - (100 / (1 + gains / losses))


def directional_market_context(
    history: list[dict[str, Any]],
    spot_price: float,
    intraday: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    volumes = [value for day in history if (value := as_float(day.get("volume"))) is not None]
    sma20 = simple_moving_average(closes, 20)
    sma50 = simple_moving_average(closes, 50)
    rsi14 = relative_strength_index(closes)
    average_volume20 = simple_moving_average(volumes, 20)
    latest_volume = volumes[-1] if volumes else None
    volume_ratio = (
        latest_volume / average_volume20
        if latest_volume is not None and average_volume20 and average_volume20 > 0
        else None
    )
    intraday = intraday or []
    intraday_closes = [
        value
        for bar in intraday
        if (value := as_float(bar.get("close") or bar.get("price"))) is not None
    ]
    intraday_volumes = [
        as_float(bar.get("volume"), 0.0) or 0.0
        for bar in intraday
        if as_float(bar.get("close") or bar.get("price")) is not None
    ]
    intraday_open = intraday_closes[0] if intraday_closes else None
    intraday_change_pct = (
        ((spot_price / intraday_open) - 1) * 100
        if intraday_open and intraday_open > 0
        else None
    )
    intraday_vwap = None
    if intraday_closes and sum(intraday_volumes) > 0:
        intraday_vwap = sum(
            price * volume
            for price, volume in zip(intraday_closes, intraday_volumes)
        ) / sum(intraday_volumes)
    intraday_rsi = relative_strength_index(intraday_closes, 9)
    fast_average = simple_moving_average(intraday_closes, 5)
    slow_average = simple_moving_average(intraday_closes, 20)
    slope_pct = (
        ((intraday_closes[-1] / intraday_closes[-4]) - 1) * 100
        if len(intraday_closes) >= 4 and intraday_closes[-4] > 0
        else None
    )

    reasons: list[str] = []
    failures: list[str] = []
    regime = "NO TRADE"
    if sma20 is None or sma50 is None or rsi14 is None:
        failures.append("insufficient daily history")
    else:
        extension = (spot_price / sma20) - 1
        score = 0
        spot_vs_sma20 = (spot_price / sma20) - 1
        sma_trend_pct = (sma20 / sma50) - 1
        if spot_vs_sma20 >= 0.0025:
            score += 1
            reasons.append("price is above its 20-day average")
        elif spot_vs_sma20 <= -0.0025:
            score -= 1
            reasons.append("price is below its 20-day average")
        if sma_trend_pct >= 0.002:
            score += 1
            reasons.append("20-day trend is above the 50-day trend")
        elif sma_trend_pct <= -0.002:
            score -= 1
            reasons.append("20-day trend is below the 50-day trend")
        if rsi14 >= 55:
            score += 1
        elif rsi14 <= 45:
            score -= 1

        if intraday_change_pct is not None:
            if intraday_change_pct >= 0.35:
                score += 2
                reasons.append(f"intraday move is bullish ({intraday_change_pct:+.1f}%)")
            elif intraday_change_pct <= -0.35:
                score -= 2
                reasons.append(f"intraday move is bearish ({intraday_change_pct:+.1f}%)")
        if intraday_vwap:
            vwap_distance_pct = ((spot_price / intraday_vwap) - 1) * 100
            if vwap_distance_pct >= 0.15:
                score += 1
                reasons.append("price is holding above intraday VWAP")
            elif vwap_distance_pct <= -0.15:
                score -= 1
                reasons.append("price is holding below intraday VWAP")
        if fast_average is not None and slow_average is not None:
            momentum_gap_pct = ((fast_average / slow_average) - 1) * 100
            if momentum_gap_pct >= 0.10:
                score += 1
                reasons.append("5-bar momentum is above the 20-bar trend")
            elif momentum_gap_pct <= -0.10:
                score -= 1
                reasons.append("5-bar momentum is below the 20-bar trend")
        if intraday_rsi is not None:
            if intraday_rsi >= 60:
                score += 1
            elif intraday_rsi <= 40:
                score -= 1
        if slope_pct is not None:
            if slope_pct >= 0.35:
                score += 1
                reasons.append("recent 15-minute price slope is rising")
            elif slope_pct <= -0.35:
                score -= 1
                reasons.append("recent 15-minute price slope is falling")

        if score >= 2:
            regime = "BULLISH / CONTROLLED"
        elif score <= -2:
            regime = "BEARISH / CONTROLLED"
        elif intraday_closes:
            regime = "NEUTRAL / RANGE"
            reasons.append("combined daily and intraday evidence is balanced")
        else:
            failures.append(
                "intraday confirmation is unavailable and daily evidence is mixed"
            )
        if abs(extension) > MAX_EXTENSION_ABOVE_SMA20_PCT:
            reasons.append(
                f"price is extended {extension * 100:+.1f}% from the 20-day average; "
                "contract risk filters still apply"
            )
    return {
        "qualified": not failures,
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "intraday_change_pct": intraday_change_pct,
        "intraday_vwap": intraday_vwap,
        "intraday_rsi": intraday_rsi,
        "intraday_fast_average": fast_average,
        "intraday_slow_average": slow_average,
        "intraday_slope_pct": slope_pct,
        "evidence_score": score if sma20 is not None and sma50 is not None and rsi14 is not None else 0,
        "regime": regime,
        "reason": "; ".join(reasons) if reasons else "No controlled directional setup",
        "failures": failures,
    }


def rolling_average(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        output.append(running / period if index + 1 >= period else None)
    return output


def render_market_chart(history: list[dict[str, Any]], spot_price: float) -> None:
    """Render a dependency-free SVG chart that GitHub Pages and browsers can display."""
    points = [
        (str(day.get("date", "")), as_float(day.get("close")), as_float(day.get("volume")))
        for day in history
    ]
    points = [(day, close, volume) for day, close, volume in points if close is not None]
    if len(points) < 20:
        return
    dates = [point[0] for point in points]
    closes = [float(point[1]) for point in points]
    sma20 = rolling_average(closes, 20)
    sma50 = rolling_average(closes, 50)
    chart_width, chart_height = 1120, 560
    left, right, top, bottom = 72, 28, 56, 70
    plot_width = chart_width - left - right
    plot_height = chart_height - top - bottom
    visible_values = closes + [value for value in sma20 + sma50 if value is not None]
    low, high = min(visible_values), max(visible_values)
    padding = max((high - low) * 0.08, 0.10)
    low, high = low - padding, high + padding

    def xy(index: int, value: float) -> tuple[float, float]:
        x = left + (index / max(len(closes) - 1, 1)) * plot_width
        y = top + ((high - value) / max(high - low, 0.01)) * plot_height
        return x, y

    def polyline(values: list[float | None], color: str, width: int) -> str:
        segments: list[list[str]] = []
        current: list[str] = []
        for index, value in enumerate(values):
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            x, y = xy(index, value)
            current.append(f"{x:.1f},{y:.1f}")
        if current:
            segments.append(current)
        return "".join(
            f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
            for segment in segments
        )

    grid: list[str] = []
    for step in range(6):
        value = low + (high - low) * step / 5
        _, y = xy(0, value)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{chart_width-right}" y2="{y:.1f}" '
            f'stroke="#243244" stroke-width="1"/>'
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" fill="#9fb0c3" '
            f'font-size="13">${value:.2f}</text>'
        )
    context = directional_market_context(history, spot_price)
    support = min(closes[-20:])
    resistance = max(closes[-20:])
    display_name = "Ford (F)" if TICKER == "F" else TICKER
    title = html.escape(
        f"{display_name} market map • {dates[-1]} • {context['regime']} • RSI {context['rsi14']:.1f}"
        if context.get("rsi14") is not None
        else f"{display_name} market map • {dates[-1]}"
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{chart_width}" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}">
<rect width="100%" height="100%" fill="#0d1520"/>
<text x="{left}" y="30" fill="#f4f7fb" font-family="Arial,sans-serif" font-size="20" font-weight="700">{title}</text>
{"".join(grid)}
{polyline([float(value) for value in closes], "#f4f7fb", 3)}
{polyline(sma20, "#38bdf8", 2)}
{polyline(sma50, "#f59e0b", 2)}
<text x="{left}" y="{chart_height-34}" fill="#38bdf8" font-family="Arial,sans-serif" font-size="14">SMA20</text>
<text x="{left+72}" y="{chart_height-34}" fill="#f59e0b" font-family="Arial,sans-serif" font-size="14">SMA50</text>
<text x="{left+150}" y="{chart_height-34}" fill="#9fb0c3" font-family="Arial,sans-serif" font-size="14">20-day support ${support:.2f} • resistance ${resistance:.2f}</text>
<text x="{chart_width-right}" y="{chart_height-34}" text-anchor="end" fill="#9fb0c3" font-family="Arial,sans-serif" font-size="12">Decision aid, not financial advice</text>
</svg>"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    CHART_PATH.write_text(svg, encoding="utf-8")
    render_market_chart_png(history, spot_price, context, support, resistance, symbol=TICKER)


def render_market_chart_png(
    history: list[dict[str, Any]],
    spot_price: float,
    context: dict[str, Any],
    support: float,
    resistance: float,
    *,
    symbol: str = "F",
    output_path: Path | None = None,
) -> None:
    """Create a Discord-ready PNG screenshot without relying on a browser."""
    from PIL import Image, ImageDraw, ImageFont

    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    if len(closes) < 20:
        return
    sma20 = rolling_average(closes, 20)
    sma50 = rolling_average(closes, 50)
    width, height = 1200, 630
    left, right, top, bottom = 85, 35, 85, 95
    plot_width, plot_height = width - left - right, height - top - bottom
    values = closes + [value for value in sma20 + sma50 if value is not None]
    low, high = min(values), max(values)
    padding = max((high - low) * 0.08, 0.10)
    low, high = low - padding, high + padding
    image = Image.new("RGB", (width, height), "#0d1520")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)
    title_font = ImageFont.load_default(size=25)

    def xy(index: int, value: float) -> tuple[int, int]:
        x = left + int(index / max(len(closes) - 1, 1) * plot_width)
        y = top + int((high - value) / max(high - low, 0.01) * plot_height)
        return x, y

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#243244", width=1)
        draw.text((12, y - 9), f"${value:.2f}", fill="#9fb0c3", font=small)

    def draw_series(series: list[float | None], color: str, line_width: int) -> None:
        segment: list[tuple[int, int]] = []
        for index, value in enumerate(series):
            if value is None:
                if len(segment) > 1:
                    draw.line(segment, fill=color, width=line_width, joint="curve")
                segment = []
            else:
                segment.append(xy(index, value))
        if len(segment) > 1:
            draw.line(segment, fill=color, width=line_width, joint="curve")

    draw_series([float(value) for value in closes], "#f4f7fb", 4)
    draw_series(sma20, "#38bdf8", 3)
    draw_series(sma50, "#f59e0b", 3)
    rsi = context.get("rsi14")
    rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
    display_name = "Ford (F)" if symbol == "F" else symbol
    draw.text((left, 25), f"{display_name} Market Map | ${spot_price:.2f} | {context['regime']}", fill="#f4f7fb", font=title_font)
    draw.text((left, 55), f"RSI14 {rsi_text} | White: Price | Blue: SMA20 | Orange: SMA50", fill="#9fb0c3", font=small)
    draw.text((left, height - 66), f"20-day support ${support:.2f}  |  resistance ${resistance:.2f}", fill="#dbe7f3", font=font)
    draw.text((left, height - 36), "Decision aid only - not professional financial advice or a profit guarantee", fill="#9fb0c3", font=small)
    destination = output_path or CHART_SCREENSHOT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def trade_intraday_history(symbol: str) -> list[dict[str, Any]]:
    """Reuse one five-minute session history across same-ticker lifecycle cards."""
    symbol = symbol.strip().upper()
    cached = INTRADAY_SNAPSHOT_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached[0] < 60:
        return cached[1]
    bars = get_intraday_history(symbol, interval="5min")
    INTRADAY_SNAPSHOT_CACHE[symbol] = (now, bars)
    return bars


def render_trade_intraday_snapshot(
    row: dict[str, str],
    event: str,
    bars: list[dict[str, Any]],
) -> Path | None:
    """Render today's five-minute underlying chart for a journal entry or exit."""
    from PIL import Image, ImageDraw, ImageFont

    points: list[tuple[str, float]] = []
    for bar in bars:
        price = as_float(bar.get("close") or bar.get("price"))
        if price is None:
            continue
        label = str(bar.get("time") or bar.get("timestamp") or bar.get("date") or "")
        points.append((label[-8:-3] if len(label) >= 8 else label, price))
    if len(points) < 2:
        return None
    prices = [point[1] for point in points]
    reference = (
        as_float(row.get("entry_price"))
        if event == "entry"
        else as_float(row.get("exit_price") or row.get("last_mark"))
    )
    # The option premium is not comparable with the underlying chart. Use the
    # final underlying bar as the event marker and label the contract premium.
    marker_price = prices[-1]
    width, height = 1200, 630
    left, right, top, bottom = 85, 35, 90, 100
    plot_width, plot_height = width - left - right, height - top - bottom
    low, high = min(prices), max(prices)
    padding = max((high - low) * 0.10, 0.05)
    low, high = low - padding, high + padding
    image = Image.new("RGB", (width, height), "#0d1520")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=15)
    normal = ImageFont.load_default(size=18)
    title_font = ImageFont.load_default(size=25)

    def xy(index: int, value: float) -> tuple[int, int]:
        return (
            left + int(index / max(len(prices) - 1, 1) * plot_width),
            top + int((high - value) / max(high - low, 0.01) * plot_height),
        )

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#243244", width=1)
        draw.text((12, y - 9), f"${value:.2f}", fill="#9fb0c3", font=small)
    draw.line([xy(i, price) for i, price in enumerate(prices)], fill="#f4f7fb", width=4, joint="curve")
    mx, my = xy(len(prices) - 1, marker_price)
    color = "#22c55e" if event == "entry" else "#ef4444"
    draw.ellipse((mx - 8, my - 8, mx + 8, my + 8), fill=color)
    symbol = row.get("ticker") or "Ticker"
    event_label = event.upper()
    draw.text((left, 25), f"{symbol} 5-Minute Session | {event_label} | ${marker_price:.2f} underlying", fill="#f4f7fb", font=title_font)
    draw.text((left, 58), f"{row.get('trade_id')} | {row.get('play_type')} | contract premium {fmt_money(reference)}", fill="#9fb0c3", font=normal)
    draw.text((left, height - 66), f"Session {points[0][0] or 'open'} to {points[-1][0] or 'now'} | marker shows snapshot time", fill="#dbe7f3", font=normal)
    draw.text((left, height - 36), "Paper-trade context only - five-minute bars can omit fast moves and are not execution prices", fill="#9fb0c3", font=small)
    destination = TRADE_SNAPSHOT_DIR / f"{row.get('trade_id', 'trade')}-{event}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def build_trade_snapshot(row: dict[str, str], event: str) -> Path | None:
    try:
        return render_trade_intraday_snapshot(
            row,
            event,
            trade_intraday_history(row.get("ticker") or TICKER),
        )
    except (TradierError, requests.RequestException, ValueError, OSError) as exc:
        print(f"Could not render {event} snapshot for {row.get('trade_id')}: {exc}", file=sys.stderr)
        return None


def market_map_text(history: list[dict[str, Any]], spot_price: float) -> str:
    context = directional_market_context(history, spot_price)
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    support = min(closes[-20:]) if closes else spot_price
    resistance = max(closes[-20:]) if closes else spot_price
    rsi_text = f"{context['rsi14']:.1f}" if context.get("rsi14") is not None else "Unavailable"
    display_name = "Ford (F)" if TICKER == "F" else TICKER
    chart_line = f"[Open the current {TICKER} chart]({CHART_PUBLIC_URL})" if CHART_PUBLIC_URL else "Chart saved to the dashboard."
    return "\n".join([
        f"## 📈 {display_name} Market Map",
        "### Trend",
        (
            f"**Regime:** {context['regime']}\n"
            f"**{TICKER}:** ${spot_price:.2f} · **SMA20:** {fmt_money(context.get('sma20'))} · "
            f"**SMA50:** {fmt_money(context.get('sma50'))} · **RSI14:** {rsi_text}"
        ),
        "### Decision Levels",
        f"**20-day support:** ${support:.2f}\n**20-day resistance:** ${resistance:.2f}",
        "### Read",
        f"{context['reason']}. A level break is confirmation only after price and option liquidity agree.",
        "### Chart",
        chart_line,
        "Educational decision support only—not professional financial advice or a profit guarantee.",
    ])


def fetch_recent_ford_filings() -> list[dict[str, str]]:
    """Read Ford's official SEC submission feed; disabled until an identifiable UA is configured."""
    if not SEC_USER_AGENT:
        return []
    response = requests.get(
        f"https://data.sec.gov/submissions/CIK{FORD_CIK}.json",
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=20,
    )
    response.raise_for_status()
    recent = response.json().get("filings", {}).get("recent", {})
    filings: list[dict[str, str]] = []
    for form, accession, filed, document in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
    ):
        if form not in SEC_FORMS:
            continue
        accession_compact = str(accession).replace("-", "")
        filings.append({
            "id": str(accession),
            "form": str(form),
            "date": str(filed),
            "url": f"https://www.sec.gov/Archives/edgar/data/37996/{accession_compact}/{document}",
        })
        if len(filings) >= 8:
            break
    return filings


def sync_ford_events(discord: "DiscordTracker", state: dict[str, Any]) -> None:
    if not discord.ready:
        return
    filings = fetch_recent_ford_filings()
    if not filings:
        return
    seen = set(str(value) for value in state.get("seen_ford_filings", []))
    newest = [filing for filing in filings if filing["id"] not in seen]
    lines = [
        "## 🗓️ Ford Event Monitor",
        "### Official Sources",
        f"[Ford investor events]({FORD_IR_EVENTS_URL}) · [Ford SEC filings](https://www.sec.gov/edgar/browse/?CIK=37996)",
        "### Recent Market-Moving Filings",
    ]
    for filing in filings[:5]:
        marker = "🆕 " if filing in newest else ""
        lines.append(f"{marker}**{filing['date']} · {filing['form']}** · [Open filing]({filing['url']})")
    lines.extend([
        "### How the bot uses this",
        "Events raise caution and add context; they never override price confirmation, liquidity rules, or max-risk controls.",
    ])
    discord.upsert_channel_message("intelligence", state, "ford-event-monitor", "\n".join(lines))
    state["seen_ford_filings"] = [filing["id"] for filing in filings]


def ford_intelligence_text(
    rows: list[dict[str, str]],
    history: list[dict[str, Any]],
    spot_price: float,
    timestamp: datetime,
) -> str:
    context = directional_market_context(history, spot_price)
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    support = min(closes[-20:]) if closes else spot_price
    resistance = max(closes[-20:]) if closes else spot_price
    today_rows = [
        row for row in rows
        if (parsed := parse_iso(row.get("timestamp"))) and parsed.date() == timestamp.date()
    ]
    calls = sum(1 for row in today_rows if row.get("call_or_put", "").lower() == "call")
    puts = sum(1 for row in today_rows if row.get("call_or_put", "").lower() == "put")
    spreads = sum(1 for row in today_rows if row.get("play_type") == "SPREAD")
    directional = len(today_rows) - spreads
    reconstructed = sum(1 for row in today_rows if not row.get("setup_reason"))
    wins = sum(1 for row in today_rows if row.get("outcome") == "WIN")
    losses = sum(1 for row in today_rows if row.get("outcome") == "LOSS")
    open_count = sum(1 for row in today_rows if row.get("outcome") == "OPEN")
    rsi_text = f"{context['rsi14']:.1f}" if context.get("rsi14") is not None else "Unavailable"
    event_note = (
        "**Primary event:** Ford reported Q2 2026 earnings after the July 28 close. "
        "The July 29 session was therefore an earnings-reaction day with gap, volatility, "
        "and reversal risk—not a normal technical session."
        if timestamp.date() == date(2026, 7, 29)
        else (
            "Check the official Ford events and SEC links below before treating a move as purely technical. "
            "Company events can override normal indicator behavior."
        )
    )
    lines = [
        "## 🧭 Ford Intelligence Desk",
        "### What Moved Ford",
        event_note,
        "### Trend and Levels",
        (
            f"**Last price:** ${spot_price:.2f}\n"
            f"**Regime:** {context['regime']}\n"
            f"**SMA20:** {fmt_money(context.get('sma20'))} · "
            f"**SMA50:** {fmt_money(context.get('sma50'))} · **RSI14:** {rsi_text}\n"
            f"**20-day support:** ${support:.2f} · **20-day resistance:** ${resistance:.2f}"
        ),
        "### Today's Trade Map",
        (
            f"**Logged:** {len(today_rows)} · **Calls:** {calls} · **Puts:** {puts} · "
            f"**Spreads:** {spreads} · **Directional:** {directional}\n"
            f"**Closed:** {wins} wins / {losses} losses · **Still open:** {open_count}"
        ),
    ]
    if reconstructed:
        lines.extend([
            "### Important Data Limitation",
            (
                f"⚠️ **{reconstructed} trade(s) were imported or created before detailed rationale fields were active.** "
                "Their exact original trend, liquidity, and event justification was not recorded, so the bot will not "
                "invent one after the fact. Their structure can be explained, but their original decision evidence is incomplete."
            ),
        ])
    lines.extend([
        "### How to Read the Structures",
        (
            "**Long calls:** bullish direction; need upside continuation large enough to overcome premium and theta.\n"
            "**Long puts:** bearish/reversal direction; especially risky when fighting a strong earnings gap.\n"
            "**Call credit spreads:** neutral-to-bearish; profit if Ford remains below the short strike.\n"
            "**Put credit spreads:** neutral-to-bullish; profit if Ford remains above the short strike."
        ),
        "### Current Risk Read",
        (
            "An elevated RSI near a recent high means momentum is strong, but fresh calls can be late and puts can be early. "
            "The safer response is confirmation at support/resistance, controlled size, and liquid contracts—not guessing the reversal."
        ),
        "### Official Ford Sources",
        (
            f"[Ford investor events]({FORD_IR_EVENTS_URL}) · "
            "[Ford investor news](https://shareholder.ford.com/news/default.aspx) · "
            "[Ford SEC filings](https://www.sec.gov/edgar/browse/?CIK=37996) · "
            f"[Current chart]({CHART_PUBLIC_URL})"
        ),
        "Educational review only—not professional financial advice or a guarantee of profit.",
    ])
    return "\n".join(lines)


def publish_ford_intelligence(
    discord: "DiscordTracker",
    state: dict[str, Any],
    rows: list[dict[str, str]],
    history: list[dict[str, Any]],
    spot_price: float,
    timestamp: datetime,
) -> None:
    if not discord.ready or not history:
        return
    discord.upsert_channel_message(
        "intelligence",
        state,
        "ford-intelligence-desk",
        ford_intelligence_text(rows, history, spot_price, timestamp),
        search_token="Ford Intelligence Desk",
    )

# ---------------------------------------------------------------------------
# CSV state and migration
# ---------------------------------------------------------------------------


def blank_row() -> dict[str, str]:
    return {column: "" for column in LOG_HEADER}


def read_log() -> list[dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    if LOG_PATH.stat().st_size == 0:
        raise RuntimeError(
            f"Trade history {LOG_PATH} is empty; refusing to continue until it is recovered."
        )
    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows = [migrate_row(row) for row in raw_rows]
    assign_missing_trade_ids(rows)
    return rows


def write_log(rows: list[dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=STATE_DIR,
            prefix=f"{LOG_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=LOG_HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in LOG_HEADER})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, LOG_PATH)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def migrate_row(raw: dict[str, Any]) -> dict[str, str]:
    row = blank_row()
    for key, value in raw.items():
        if key in row and value is not None:
            row[key] = str(value)

    row["ticker"] = row.get("ticker") or TICKER
    row["outcome"] = (row.get("outcome") or "OPEN").upper()
    row["entry_price"] = round_or_blank(parse_entry_price(row), 2)
    row["discord_status"] = row.get("discord_status") or row["outcome"]
    row["last_signal"] = row.get("last_signal") or ("HOLD" if row["outcome"] == "OPEN" else row["outcome"])
    if row["outcome"] == "OPEN":
        row["last_mark"] = row.get("last_mark") or round_or_blank(parse_entry_price(row), 2)
        row["current_pl_dollars"] = row.get("current_pl_dollars") or "0"
        row["current_pl_pct"] = row.get("current_pl_pct") or "0"
        row["max_favorable_pct"] = row.get("max_favorable_pct") or "0"
        row["max_adverse_pct"] = row.get("max_adverse_pct") or "0"


    if row["outcome"] in {"WIN", "LOSS", "SCRATCH"}:
        had_exit_price = bool(row.get("exit_price"))
        inferred_exit = exit_price(row)
        if inferred_exit is not None and not row.get("exit_price"):
            row["exit_price"] = round_or_blank(inferred_exit, 2)
        if not row.get("result_price_source"):
            row["result_price_source"] = "TRACKED" if had_exit_price else "RECONSTRUCTED"
        row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 0)
        row["exit_contract_value"] = round_or_blank(exit_contract_value(row), 0)
        row["realized_pl_dollars"] = round_or_blank(realized_pl_dollars(row), 0)

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
        match = re.fullmatch(r"([A-Z0-9.-]+)-(\d{8})-(\d{3,})", trade_id)
        if match:
            prefix, day_key, sequence = match.group(1), match.group(2), int(match.group(3))
            next_sequence[f"{prefix}:{day_key}"] = max(
                next_sequence.get(f"{prefix}:{day_key}", 1), sequence + 1
            )

    for row in rows:
        if row.get("trade_id"):
            continue
        timestamp = parse_iso(row.get("timestamp")) or now_ct()
        day_key = timestamp.strftime("%Y%m%d")
        ticker = re.sub(r"[^A-Z0-9.-]", "", (row.get("ticker") or TICKER).upper()) or TICKER
        sequence_key = f"{ticker}:{day_key}"
        sequence = next_sequence.get(sequence_key, 1)
        candidate = f"{ticker}-{day_key}-{sequence:03d}"
        while candidate in used:
            sequence += 1
            candidate = f"{ticker}-{day_key}-{sequence:03d}"
        row["trade_id"] = candidate
        used.add(candidate)
        next_sequence[sequence_key] = sequence + 1


def next_trade_id(rows: list[dict[str, str]], timestamp: datetime) -> str:
    day_key = timestamp.strftime("%Y%m%d")
    highest = 0
    prefix = re.escape(TICKER)
    pattern = re.compile(rf"{prefix}-{day_key}-(\d+)$")
    for row in rows:
        match = pattern.match(row.get("trade_id", ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{TICKER}-{day_key}-{highest + 1:03d}"


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
        TICKER,
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
    regular: list[str] = []
    conservative: list[str] = []
    for expiration in expirations:
        expiry_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        days_out = (expiry_date - today).days
        if REGULAR_MIN_DTE <= days_out <= REGULAR_MAX_DTE:
            regular.append(expiration)
        elif MIN_DTE <= days_out <= MAX_DTE:
            conservative.append(expiration)
    return sorted(regular), sorted(conservative)


def filter_strikes(strikes: list[float], spot: float) -> list[float]:
    low = spot * (1 - STRIKE_BAND_PCT)
    high = spot * (1 + STRIKE_BAND_PCT)
    return sorted(strike for strike in strikes if low <= strike <= high)




def open_interest_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(option.get(key))
        if value is not None and value > 0:
            return int(value)
    greeks = option.get("greeks") or {}
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(greeks.get(key))
        if value is not None and value > 0:
            return int(value)
    return 0


def option_volume_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    return int(as_float(option.get("volume"), 0.0) or 0)


def option_has_liquidity(option: dict[str, Any]) -> bool:
    bid = as_float(option.get("bid"), 0.0) or 0.0
    ask = as_float(option.get("ask"), 0.0) or 0.0
    open_interest = open_interest_value(option)
    volume = option_volume_value(option)
    midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
    spread_pct = ((ask - bid) / midpoint) if midpoint > 0 else float("inf")
    return (
        bid > 0
        and ask >= bid
        and open_interest >= MIN_OPEN_INTEREST
        and volume >= MIN_OPTION_VOLUME
        and spread_pct <= MAX_BID_ASK_PCT
    )

def greek(option: dict[str, Any], key: str) -> float | None:
    return as_float((option.get("greeks") or {}).get(key))



def iv_value(option: dict[str, Any] | None) -> float | None:
    if not option:
        return None
    greeks = option.get("greeks") or {}
    for source in (greeks, option):
        for key in (
            "mid_iv",
            "smv_vol",
            "bid_iv",
            "ask_iv",
            "iv",
            "implied_volatility",
            "impliedVolatility",
        ):
            value = as_float(source.get(key))
            if value is not None and value > 0:
                return value
    return None

def scan_credit_spreads(
    chain: list[dict[str, Any]],
    kind: str,
    expiration: str,
    market_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
        max_risk = (width - credit) * 100
        if (
            credit < MIN_SPREAD_CREDIT
            or width <= 0
            or credit >= width
            or max_risk > MAX_RISK_PER_TRADE
        ):
            continue
        short_oi = open_interest_value(short_option)
        long_oi = open_interest_value(long_option)
        option_volume = min(option_volume_value(short_option), option_volume_value(long_option))
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
                "iv": round(iv_value(short_option), 4) if iv_value(short_option) is not None else "",
                "pop": round((1 - delta) * 100, 1),
                "max_profit": round(credit * 100, 2),
                "max_risk": round(max_risk, 2),
                "breakeven": round(short_strike - credit if kind == "put" else short_strike + credit, 2),
                "open_interest": min(short_oi, long_oi),
                "option_volume": option_volume,
                "bid_ask_width": round(combined_width, 2),
                "short_symbol": short_option.get("symbol") or option_symbol(TICKER, expiration, kind, short_strike),
                "long_symbol": long_option.get("symbol") or option_symbol(TICKER, expiration, kind, long_strike),
                "score": score,
                "setup_reason": (market_context or {}).get("reason", "Controlled regime filters passed"),
                "market_regime": (market_context or {}).get("regime", "CONTROLLED"),
            }
        )
    return candidates


def scan_single_legs(
    chain: list[dict[str, Any]],
    kind: str,
    expiration: str,
    play_type: str,
    market_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
        if ask > MAX_CONTRACT_ASK or ask * 100 > MAX_RISK_PER_TRADE:
            continue
        strike = float(option["strike"])
        open_interest = open_interest_value(option)
        option_volume = option_volume_value(option)
        spread_width = max(ask - bid, 0)
        spread_pct = spread_width / ((ask + bid) / 2)
        score = (
            40
            + delta * 30
            + math.log1p(open_interest) * 2
            + math.log1p(option_volume)
            - spread_pct * 50
            - (ask * 100 / max(MAX_RISK_PER_TRADE, 1)) * 5
        )
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
                "iv": round(iv_value(option), 4) if iv_value(option) is not None else "",
                "pop": round(delta * 100, 1),
                "max_profit": max_profit,
                "max_risk": round(ask * 100, 2),
                "breakeven": round(strike + ask if kind == "call" else strike - ask, 2),
                "open_interest": open_interest,
                "option_volume": option_volume,
                "bid_ask_width": round(spread_width, 2),
                "option_symbol": option.get("symbol") or option_symbol(TICKER, expiration, kind, strike),
                "score": score,
                "setup_reason": (market_context or {}).get("reason", "Bullish trend gate passed"),
                "market_regime": (market_context or {}).get("regime", "CONTROLLED"),
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
            "entry_price": round_or_blank(as_float(candidate["entry_price"]), 2),
            "delta_at_entry": str(candidate["delta"]),
            "theta_at_entry": str(candidate["theta"]),
            "iv_at_entry": "" if candidate.get("iv") in (None, "") else str(candidate["iv"]),
            "pop_estimate": str(candidate["pop"]),
            "max_profit": str(candidate["max_profit"]),
            "max_risk": str(candidate["max_risk"]),
            "breakeven": str(candidate["breakeven"]),
            "open_interest_at_entry": str(candidate["open_interest"]),
            "bid_ask_width_at_entry": str(candidate["bid_ask_width"]),
            "option_volume_at_entry": str(candidate.get("option_volume", "")),
            "setup_score": round_or_blank(as_float(candidate.get("score")), 1),
            "setup_reason": str(candidate.get("setup_reason", "")),
            "market_regime": str(candidate.get("market_regime", "")),
            "outcome": "OPEN",
            "last_mark": str(candidate["entry_price"]),
            "current_pl_dollars": "0",
            "current_pl_pct": "0",
            "max_favorable_pct": "0",
            "max_adverse_pct": "0",
            "last_signal": "HOLD",
            "last_evaluated_at": timestamp.isoformat(),
            "discord_status": "OPEN",
        }
    )
    return row

# ---------------------------------------------------------------------------
# Open-play evaluation
# ---------------------------------------------------------------------------



def refresh_open_entry_market_data(
    rows: list[dict[str, str]],
    quotes: dict[str, dict[str, Any]],
) -> int:
    """Fill legacy missing IV/OI from the latest live quote without overwriting valid entry data."""
    updated = 0
    for row in open_rows(rows):
        oi = int(as_float(row.get("open_interest_at_entry"), 0.0) or 0)
        iv = as_float(row.get("iv_at_entry"))
        replacement_oi = 0
        replacement_iv: float | None = None

        if row.get("play_type") == "SPREAD":
            short_quote = quotes.get(row.get("short_symbol", ""))
            long_quote = quotes.get(row.get("long_symbol", ""))
            short_oi = open_interest_value(short_quote)
            long_oi = open_interest_value(long_quote)
            if short_oi > 0 and long_oi > 0:
                replacement_oi = min(short_oi, long_oi)
            replacement_iv = iv_value(short_quote)
        else:
            quote = quotes.get(row.get("option_symbol", ""))
            replacement_oi = open_interest_value(quote)
            replacement_iv = iv_value(quote)

        if oi <= 0 and replacement_oi > 0:
            row["open_interest_at_entry"] = str(replacement_oi)
            updated += 1
        if (iv is None or iv <= 0) and replacement_iv is not None and replacement_iv > 0:
            row["iv_at_entry"] = round_or_blank(replacement_iv, 4)
            updated += 1
    return updated


def symbols_for_rows(rows: list[dict[str, str]]) -> list[str]:
    symbols: list[str] = []
    for row in rows:
        symbols.append(row.get("ticker", ""))
        if row.get("play_type") == "SPREAD":
            symbols.extend([row.get("short_symbol", ""), row.get("long_symbol", "")])
        else:
            symbols.append(row.get("option_symbol", ""))
    return list(dict.fromkeys(symbol for symbol in symbols if symbol))


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
    play_type = row.get("play_type")
    expiry_days = days_to_expiry(row["expiration"])
    expiring_soon = expiry_days <= (SPREAD_EXIT_DTE if play_type == "SPREAD" else 1)

    if play_type == "SPREAD":
        short_quote = quotes.get(row.get("short_symbol", ""))
        long_quote = quotes.get(row.get("long_symbol", ""))
        if not short_quote or not long_quote:
            return {
                "signal": "HOLD",
                "note": "Live leg quote unavailable; showing last tracked values.",
                "mark": as_float(row.get("last_mark"), entry),
                "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
                "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
            }
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
            return {
                "signal": "HOLD",
                "note": "Live option quote unavailable; showing last tracked values.",
                "mark": as_float(row.get("last_mark"), entry),
                "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
                "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
            }
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
        "mark": round(mark, 2),
        "pl_dollars": round(pnl * 100),
        "pl_pct": round(pnl_pct),
        **details,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result



def apply_evaluation_to_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> None:
    pnl_pct = as_float(evaluation.get("pl_pct"))
    row["last_evaluated_at"] = timestamp.isoformat()
    row["last_signal"] = evaluation.get("signal", "HOLD")
    row["last_mark"] = round_or_blank(as_float(evaluation.get("mark")), 2)
    row["current_pl_dollars"] = round_or_blank(as_float(evaluation.get("pl_dollars")), 0)
    row["current_pl_pct"] = round_or_blank(pnl_pct, 0)

    if pnl_pct is not None:
        current_mfe = as_float(row.get("max_favorable_pct"), 0.0) or 0.0
        current_mae = as_float(row.get("max_adverse_pct"), 0.0) or 0.0
        row["max_favorable_pct"] = round_or_blank(max(current_mfe, pnl_pct), 0)
        row["max_adverse_pct"] = round_or_blank(min(current_mae, pnl_pct), 0)


def close_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> str:
    signal = evaluation.get("signal")
    tracked_exit = as_float(evaluation.get("mark"))
    tracked_exit = None if tracked_exit is None else round(tracked_exit, 2)
    entry = parse_entry_price(row)

    if tracked_exit is None:
        realized = round(as_float(evaluation.get("pl_dollars"), 0.0) or 0.0)
    elif row.get("play_type") == "SPREAD":
        realized = round((entry - tracked_exit) * 100)
    else:
        realized = round((tracked_exit - entry) * 100)

    pnl_pct = (realized / (entry * 100) * 100) if entry else 0.0
    if signal == "TAKE PROFIT":
        outcome = "WIN"
    elif signal == "STOP OUT":
        outcome = "LOSS"
    else:
        # New lifecycle is intentionally binary: a closed paper trade either
        # made money or did not. Legacy SCRATCH rows remain readable.
        outcome = "WIN" if pnl_pct > 0 else "LOSS"

    row["outcome"] = outcome
    row["pct_gain_loss"] = round_or_blank(pnl_pct, 0)
    row["exit_price"] = round_or_blank(tracked_exit, 2)
    row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 0)
    row["exit_contract_value"] = round_or_blank(
        None if tracked_exit is None else tracked_exit * 100,
        0,
    )
    row["realized_pl_dollars"] = round_or_blank(realized, 0)
    row["result_price_source"] = "TRACKED"
    row["closed_at"] = timestamp.isoformat()
    row["discord_status"] = outcome
    return outcome


CARD_COLORS = {
    "entry": 0x3498DB,
    "qualified": 0x9B59B6,
    "hold": 0xF1C40F,
    "win": 0x2ECC71,
    "loss": 0xE74C3C,
    "scratch": 0x95A5A6,
    "scanner": 0x00A8E8,
    "performance": 0x5865F2,
    "error": 0xE74C3C,
    "status": 0x607D8B,
}



def card_color_for_text(content: str) -> int:
    title = next((line for line in content.splitlines() if line.strip()), content).upper()
    if "ERROR" in title or "FAILED" in title or "🚨" in title:
        return CARD_COLORS["error"]
    if "QUALIFIED" in title:
        return CARD_COLORS["qualified"]
    if "ENTRY" in title:
        return CARD_COLORS["entry"]
    if "· WIN" in title or "WINS SUMMARY" in title or "🏆" in title or "🟩" in title:
        return CARD_COLORS["win"]
    if "· LOSS" in title or "LOSSES SUMMARY" in title or "🟥" in title:
        return CARD_COLORS["loss"]
    if "SCRATCH" in title:
        return CARD_COLORS["scratch"]
    if "HOLD" in title or "POSITION" in title:
        return CARD_COLORS["hold"]
    if "SCAN" in title:
        return CARD_COLORS["scanner"]
    if "PERFORMANCE" in title or "STRATEGY" in title or "REPORT" in title or "RECAP" in title:
        return CARD_COLORS["performance"]
    return CARD_COLORS["status"]

def discord_card(content: str) -> dict[str, Any]:
    """Convert scanner markdown into a native Discord embed card."""
    raw_lines = [line.rstrip() for line in content.strip().splitlines()]
    title = "Tradysquids TradeBot"
    description_lines: list[str] = []
    fields: list[dict[str, Any]] = []
    current_name = ""
    current_value: list[str] = []

    def flush_field() -> None:
        nonlocal current_name, current_value
        if not current_name:
            return
        value = "\n".join(current_value).strip() or "—"
        fields.append({
            "name": current_name[:256],
            "value": value[:1024],
            "inline": False,
        })
        current_name = ""
        current_value = []

    for line in raw_lines:
        if line.startswith("## ") and title == "Tradysquids TradeBot":
            title = line[3:].strip()
            continue
        if line.startswith("# ") and title == "Tradysquids TradeBot":
            title = line[2:].strip()
            continue
        if line.startswith("### "):
            flush_field()
            current_name = line[4:].strip()
            continue
        if current_name:
            current_value.append(line)
        else:
            description_lines.append(line)
    flush_field()

    description = "\n".join(description_lines).strip()
    embed: dict[str, Any] = {
        "title": title[:256],
        "color": card_color_for_text(content),
        "footer": {"text": f"Tradysquids TradeBot · Card format {DISCORD_FORMAT_VERSION}"},
    }
    if description:
        embed["description"] = description[:4096]
    if fields:
        embed["fields"] = fields[:25]
    return embed


def message_search_text(message: dict[str, Any]) -> str:
    parts = [str(message.get("content") or "")]
    for embed in message.get("embeds") or []:
        parts.append(str(embed.get("title") or ""))
        parts.append(str(embed.get("description") or ""))
        for field in embed.get("fields") or []:
            parts.append(str(field.get("name") or ""))
            parts.append(str(field.get("value") or ""))
    return "\n".join(parts)


class DiscordError(RuntimeError):
    pass


def discord_route_is_missing(exc: Exception) -> bool:
    message = str(exc)
    return "HTTP 403" in message or "HTTP 404" in message or "Missing Access" in message


class DiscordTracker:
    API_BASE = "https://discord.com/api/v10"
    _discovery_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _discovery_lock = threading.Lock()
    _discovery_ttl_seconds = 300.0

    def __init__(self, token: str, guild_id: str):
        self.token = token
        self.guild_id = guild_id
        self.ready = False
        self.channels: dict[str, str] = {}
        self.tag_ids: dict[str, str] = {}
        self.forum_id = ""
        self.missing_channels: list[str] = []
        self.private_system_channels: set[str] = set()
        self._channel_message_cache: dict[str, list[dict[str, Any]]] = {}

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
                # Discord can impose a guild-wide cooldown longer than ten
                # seconds during chart/card bursts.  Sleeping for less than
                # the advertised window only burns every retry immediately.
                time.sleep(min(max(retry_after, 0.0) + 0.25, 65))
                continue
            if response.status_code >= 500 and attempt < 3:
                time.sleep(2**attempt)
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
        now = time.monotonic()
        with self._discovery_lock:
            cached = self._discovery_cache.get(self.guild_id)
        if cached and now - cached[0] < self._discovery_ttl_seconds:
            guild_channels = cached[1]
        else:
            guild_channels = self._request("GET", f"/guilds/{self.guild_id}/channels")
            with self._discovery_lock:
                self._discovery_cache[self.guild_id] = (now, guild_channels)
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

        channel_by_id = {str(channel.get("id")): channel for channel in guild_channels}

        def denies_everyone_view(channel: dict[str, Any] | None) -> bool:
            if not channel:
                return False
            for overwrite in channel.get("permission_overwrites") or []:
                if str(overwrite.get("id")) != self.guild_id or int(overwrite.get("type", -1)) != 0:
                    continue
                deny = int(overwrite.get("deny", 0))
                return bool(deny & 1024)  # VIEW_CHANNEL
            return False

        for key in SYSTEM_CHANNEL_KEYS:
            channel = by_name.get(CHANNEL_NAMES[key])
            parent = channel_by_id.get(str(channel.get("parent_id"))) if channel else None
            if denies_everyone_view(channel) or denies_everyone_view(parent):
                self.private_system_channels.add(key)

        for tag in forum.get("available_tags") or []:
            normalized = normalized_name(tag.get("name", ""))
            for key in TAG_KEYS:
                if normalized == key or normalized.endswith(f" {key}") or key in normalized:
                    self.tag_ids.setdefault(key, tag["id"])

        missing_tags = sorted(key for key in ("OPEN", "HOLDING", "WIN", "LOSS", "SCRATCH") if key not in self.tag_ids)
        if missing_tags:
            raise DiscordError(f"Missing required trade-journal forum tags: {', '.join(missing_tags)}")
        self.missing_channels = [
            CHANNEL_NAMES[key]
            for key in AUTOMATED_CHANNEL_KEYS
            if key not in self.channels
        ]
        self.ready = True

    def ensure_private_system_route(self, logical_name: str) -> None:
        if logical_name in SYSTEM_CHANNEL_KEYS and logical_name not in self.private_system_channels:
            raise DiscordError(
                f"Refusing to post system data to #{CHANNEL_NAMES[logical_name]} "
                "because @everyone can view the channel or its privacy could not be verified"
            )

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
        self.ensure_private_system_route(logical_name)
        payload: dict[str, Any] = {"allowed_mentions": {"parse": []}}
        if embed is None and content:
            embed = discord_card(content)
            content = ""
        if content:
            payload["content"] = content[:2000]
        if embed:
            payload["embeds"] = [embed]
        return self._request("POST", f"/channels/{channel_id}/messages", payload)

    def send_channel_file(
        self,
        logical_name: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id or not file_path.exists():
            return None
        self.ensure_private_system_route(logical_name)
        return self._send_file_to_channel(channel_id, file_path, content=content)

    def send_thread_file(
        self,
        thread_id: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        if not self.ready or not thread_id or not file_path.exists():
            return None
        return self._send_file_to_channel(thread_id, file_path, content=content)

    def _send_file_to_channel(
        self,
        channel_id: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        url = f"{self.API_BASE}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
        }
        payload = {
            "content": content[:2000],
            "allowed_mentions": {"parse": []},
        }
        for attempt in range(4):
            try:
                with file_path.open("rb") as handle:
                    response = SESSION.post(
                        url,
                        headers=headers,
                        data={"payload_json": json.dumps(payload)},
                        files={"files[0]": (file_path.name, handle, "image/png")},
                        timeout=30,
                    )
            except requests.RequestException as exc:
                if attempt == 3:
                    raise DiscordError(f"Discord chart upload failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 and attempt < 3:
                retry_after = as_float(response.json().get("retry_after"), 1.0) or 1.0
                time.sleep(min(retry_after + 0.25, 65))
                continue
            if response.status_code >= 500 and attempt < 3:
                time.sleep(2**attempt)
                continue
            if not response.ok:
                body = response.text[:700].replace(self.token, "[REDACTED]")
                raise DiscordError(f"Discord chart upload HTTP {response.status_code}: {body}")
            return response.json()
        raise DiscordError("Discord chart upload retries exhausted")

    def upsert_channel_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        state_key: str,
        content: str,
        search_token: str = "",
    ) -> str:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return ""
        self.ensure_private_system_route(logical_name)
        messages = state.setdefault("messages", {})
        hashes = state.setdefault("message_hashes", {})
        message_id = str(messages.get(state_key) or "")
        clipped_content = content[:6000]
        embed = discord_card(clipped_content)
        serialized = json.dumps(embed, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(
            f"{DISCORD_FORMAT_VERSION}:{serialized}".encode("utf-8")
        ).hexdigest()
        payload = {
            "content": "",
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        }
        if message_id and hashes.get(state_key) == content_hash:
            return message_id
        if message_id:
            try:
                self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
                hashes[state_key] = content_hash
                return message_id
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise

        if search_token:
            recent = self._request("GET", f"/channels/{channel_id}/messages?limit=100")
            if isinstance(recent, list):
                for message in recent:
                    author = message.get("author") or {}
                    if author.get("bot") and search_token in message_search_text(message):
                        message_id = str(message.get("id") or "")
                        if message_id:
                            self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
                            messages[state_key] = message_id
                            hashes[state_key] = content_hash
                            return message_id

        created = self._request("POST", f"/channels/{channel_id}/messages", payload)
        if isinstance(created, dict) and created.get("id"):
            message_id = str(created["id"])
            messages[state_key] = message_id
            hashes[state_key] = content_hash
        return message_id

    def upsert_trade_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        namespace: str,
        trade_id: str,
        content: str,
    ) -> str:
        if not trade_id:
            return ""
        return self.upsert_channel_message(
            logical_name,
            state,
            f"{namespace}:{logical_name}:{trade_id}",
            content,
            search_token=trade_id,
        )

    def upsert_trade_result(
        self,
        logical_name: str,
        state: dict[str, Any],
        trade_id: str,
        content: str,
    ) -> None:
        self.upsert_trade_message(logical_name, state, "result", trade_id, content)

    def delete_trade_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        namespace: str,
        trade_id: str,
    ) -> None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id or not trade_id:
            return
        messages = state.setdefault("messages", {})
        state_key = f"{namespace}:{logical_name}:{trade_id}"
        message_id = str(messages.get(state_key) or "")
        if message_id:
            try:
                self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        else:
            # Runtime state can be deleted or predate message tracking. Search
            # the channel itself so stale legacy cards do not become permanent.
            recent = self._channel_message_cache.get(channel_id)
            if recent is None:
                recent = []
                before = ""
                for _ in range(10):
                    suffix = f"&before={before}" if before else ""
                    page = self._request(
                        "GET", f"/channels/{channel_id}/messages?limit=100{suffix}"
                    )
                    if not isinstance(page, list) or not page:
                        break
                    recent.extend(page)
                    before = str(page[-1].get("id") or "")
                    if len(page) < 100 or not before:
                        break
                self._channel_message_cache[channel_id] = recent
            for message in list(recent):
                author = message.get("author") or {}
                if author.get("bot") and trade_id in message_search_text(message):
                    stale_id = str(message.get("id") or "")
                    if stale_id:
                        try:
                            self._request(
                                "DELETE", f"/channels/{channel_id}/messages/{stale_id}"
                            )
                        except DiscordError as exc:
                            if "HTTP 404" not in str(exc):
                                raise
                    recent.remove(message)
        messages.pop(state_key, None)
        state.setdefault("message_hashes", {}).pop(state_key, None)

    def create_trade_thread(self, row: dict[str, str], status: str = "OPEN") -> str:
        if not self.ready:
            return ""
        tag_id = self.tag_ids.get(status) or self.tag_ids.get("OPEN")
        payload = {
            "name": trade_title(row)[:100],
            "auto_archive_duration": 1440,
            "applied_tags": [tag_id] if tag_id else [],
            "message": {
                "content": "",
                "embeds": [discord_card(entry_alert_text(row))],
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
            row["last_discord_pl_pct"] = row.get("current_pl_pct") or "0"
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
            {"content": "", "embeds": [discord_card(entry_alert_text(row))], "allowed_mentions": {"parse": []}},
        )
        row["discord_format_version"] = DISCORD_FORMAT_VERSION

    def send_thread(self, thread_id: str, content: str) -> None:
        if not self.ready or not thread_id:
            return
        self._request(
            "POST",
            f"/channels/{thread_id}/messages",
            {"content": "", "embeds": [discord_card(content)], "allowed_mentions": {"parse": []}},
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



def migrate_recent_bot_messages_to_cards(
    discord: DiscordTracker,
    state: dict[str, Any],
    *,
    limit_per_channel: int = 50,
) -> int:
    """One-time conversion of recent TradeBot plain messages into embed cards."""
    if not discord.ready or state.get("card_migration_version") == DISCORD_FORMAT_VERSION:
        return 0

    converted = 0
    visited_channel_ids: set[str] = set()
    for logical_name in AUTOMATED_CHANNEL_KEYS:
        channel_id = discord.channels.get(logical_name)
        if not channel_id or channel_id in visited_channel_ids:
            continue
        visited_channel_ids.add(channel_id)
        recent = discord._request(
            "GET",
            f"/channels/{channel_id}/messages?limit={max(1, min(limit_per_channel, 100))}",
        )
        if not isinstance(recent, list):
            continue
        for message in recent:
            author = message.get("author") or {}
            content = str(message.get("content") or "").strip()
            if not author.get("bot") or not content or message.get("embeds"):
                continue
            message_id = str(message.get("id") or "")
            if not message_id:
                continue
            discord._request(
                "PATCH",
                f"/channels/{channel_id}/messages/{message_id}",
                {
                    "content": "",
                    "embeds": [discord_card(content)],
                    "allowed_mentions": {"parse": []},
                },
            )
            converted += 1

    state["card_migration_version"] = DISCORD_FORMAT_VERSION
    return converted


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
    iv_text = fmt_iv(iv)

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
            embed_field("Estimated POP", f"{as_float(row.get('pop_estimate'), 0):.0f}%"),
            embed_field("Theta", "—" if theta is None else f"{theta:+.3f}/day"),
            embed_field("IV", iv_text),
            embed_field("Entry OI", fmt_oi(row.get("open_interest_at_entry"))),
            embed_field("Entry volume", fmt_oi(row.get("option_volume_at_entry"))),
            embed_field("Bid/ask width", f"${as_float(row.get('bid_ask_width_at_entry'), 0):.2f}"),
            embed_field("Why it qualified", row.get("setup_reason"), False),
            embed_field(
                "Management",
                (
                    f"50% credit capture / 2× credit stop / close by {SPREAD_EXIT_DTE} DTE"
                    if play_type == "SPREAD"
                    else "+20% target / -15% stop"
                ),
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


def sync_existing_open_threads(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    *,
    refresh_existing: bool = True,
) -> int:
    if not DISCORD_SYNC_EXISTING_OPEN or not discord.ready:
        return 0
    created = 0
    for row in open_rows(rows):
        try:
            if row.get("discord_thread_id"):
                if (
                    refresh_existing
                    and row.get("discord_format_version") != DISCORD_FORMAT_VERSION
                ):
                    discord.refresh_trade_thread(row)
                continue
            thread_id = discord.create_trade_thread(row, "OPEN")
            if thread_id:
                created += 1
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
    status = "HOLDING"
    if evaluation.get("signal") == "TAKE PROFIT":
        status = "TARGET HIT"
    elif evaluation.get("signal") == "STOP OUT":
        status = "STOP WARNING"
    try:
        discord.send_thread(row["discord_thread_id"], content)
    except DiscordError as exc:
        if not discord_route_is_missing(exc):
            raise
        row["discord_thread_id"] = ""
        row["discord_status"] = ""
        row["discord_format_version"] = ""
        return
    try:
        discord.set_thread_status(row["discord_thread_id"], status)
    except DiscordError as exc:
        print(f"Could not update optional forum status for {row.get('trade_id')}: {exc}", file=sys.stderr)
    row["discord_status"] = status
    row["last_discord_signal"] = evaluation.get("signal", "HOLD")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 0)
    row["last_discord_update_at"] = timestamp.isoformat()


def stored_open_evaluation(row: dict[str, str]) -> dict[str, Any]:
    return {
        "signal": row.get("last_signal") or "HOLD",
        "mark": as_float(row.get("last_mark"), parse_entry_price(row)),
        "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
        "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        "note": "",
        "iv": as_float(row.get("iv_at_entry")),
    }

def sync_open_trade_cards(
    row: dict[str, str],
    discord: DiscordTracker,
    report_state: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
    *,
    include_entry: bool = False,
) -> None:
    if not discord.ready or row.get("outcome") != "OPEN":
        return
    trade_id = row.get("trade_id", "")
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    current = evaluation or stored_open_evaluation(row)
    if include_entry:
        discord.upsert_trade_message(
            "qualified",
            report_state,
            "qualified",
            trade_id,
            qualified_trade_text(row, link),
        )
        discord.upsert_trade_message(
            "entry",
            report_state,
            "entry",
            trade_id,
            entry_alert_text(row, link),
        )
    discord.upsert_trade_message(
        "updates",
        report_state,
        "position",
        trade_id,
        position_update_text(row, current, link),
    )
    if thread_id and row.get("discord_status") != "HOLDING":
        try:
            discord.set_thread_status(thread_id, "HOLDING")
            row["discord_status"] = "HOLDING"
        except DiscordError as exc:
            print(f"Could not update optional forum status for {trade_id}: {exc}", file=sys.stderr)


def sync_all_open_trade_cards(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> int:
    synced_open = 0
    for row in rows:
        trade_id = row.get("trade_id", "")
        if not trade_id:
            continue
        link = thread_link(row.get("discord_thread_id", ""))
        discord.upsert_trade_message(
            "qualified",
            report_state,
            "qualified",
            trade_id,
            qualified_trade_text(row, link),
        )
        discord.upsert_trade_message(
            "entry",
            report_state,
            "entry",
            trade_id,
            entry_alert_text(row, link),
        )
        if row.get("outcome") == "OPEN":
            sync_open_trade_cards(row, discord, report_state)
            synced_open += 1
    return synced_open

def mark_closed_result_routed(row: dict[str, str], report_state: dict[str, Any]) -> None:
    trade_id = row.get("trade_id", "")
    if not trade_id:
        return
    routed = report_state.setdefault("routed_closed_trade_ids", [])
    if trade_id not in routed:
        routed.append(trade_id)


def stored_close_evaluation(row: dict[str, str]) -> dict[str, Any]:
    pl_pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    return {
        "pl_pct": pl_pct,
        "pl_dollars": realized_pl_dollars(row),
        "mark": exit_price(row),
        "signal": row.get("last_signal") or "CLOSED",
    }


def sync_closed_result_channels(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> int:
    """Refresh exit alerts and outcome channels with complete entry/exit structures."""
    if not discord.ready:
        return 0
    updated = 0
    routed = set(report_state.get("routed_closed_trade_ids") or [])
    for row in sorted(closed_rows(rows), key=lambda item: item.get("closed_at") or item.get("timestamp") or ""):
        trade_id = row.get("trade_id", "")
        result_channel = {
            "WIN": "wins",
            "LOSS": "losses",
            "SCRATCH": "scratches",
            "EXPIRED": "expired",
        }.get(row.get("outcome", ""))
        if not trade_id or not result_channel:
            continue
        if trade_id in routed:
            # A completed destination card may predate held-card cleanup.  Do
            # not repost the result, but keep enforcing the channel lifecycle.
            discord.delete_trade_message(
                "updates", report_state, "position", trade_id
            )
            discord.delete_trade_message("exit", report_state, "exit", trade_id)
            continue
        link = thread_link(row.get("discord_thread_id", ""))
        content = close_alert_text(row, stored_close_evaluation(row), link)
        discord.upsert_trade_result(result_channel, report_state, trade_id, content)
        discord.delete_trade_message("updates", report_state, "position", trade_id)
        discord.delete_trade_message("exit", report_state, "exit", trade_id)
        mark_closed_result_routed(row, report_state)
        updated += 1
    return updated

def post_close(row: dict[str, str], evaluation: dict[str, Any], discord: DiscordTracker, report_state: dict[str, Any]) -> None:
    if not discord.ready:
        return
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    content = close_alert_text(row, evaluation, link)
    if thread_id:
        try:
            discord.send_thread(thread_id, close_alert_text(row, evaluation))
            snapshot = build_trade_snapshot(row, "exit")
            if snapshot:
                discord.send_thread_file(
                    thread_id,
                    snapshot,
                    content=(
                        f"📉 **EXIT SNAPSHOT · {row.get('trade_id')} · {row.get('outcome')}**\n"
                        f"5-minute underlying session · contract return "
                        f"{fmt_pct(as_float(evaluation.get('pl_pct')))}"
                    ),
                )
        except DiscordError as exc:
            if not discord_route_is_missing(exc):
                raise
            row["discord_thread_id"] = ""
            row["discord_status"] = ""
            link = ""
            content = close_alert_text(row, evaluation)
        else:
            try:
                discord.set_thread_status(thread_id, row["outcome"], archive=True)
            except DiscordError as exc:
                print(f"Could not update optional forum status for {row.get('trade_id')}: {exc}", file=sys.stderr)
    result_channel = {
        "WIN": "wins",
        "LOSS": "losses",
        "SCRATCH": "scratches",
        "EXPIRED": "expired",
    }.get(row["outcome"])
    if result_channel:
        discord.upsert_trade_result(result_channel, report_state, row.get("trade_id", ""), content)
        mark_closed_result_routed(row, report_state)
    discord.delete_trade_message("updates", report_state, "position", row.get("trade_id", ""))
    discord.delete_trade_message("exit", report_state, "exit", row.get("trade_id", ""))
    row["discord_status"] = row["outcome"]
    row["last_discord_signal"] = evaluation.get("signal", "CLOSE")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 0)
    row["last_discord_update_at"] = row.get("closed_at") or now_ct().isoformat()

def post_new_trade(
    row: dict[str, str],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> None:
    if not discord.ready:
        return
    if not row.get("discord_thread_id"):
        discord.create_trade_thread(row, "OPEN")
    sync_open_trade_cards(row, discord, report_state, include_entry=True)
    thread_id = row.get("discord_thread_id", "")
    snapshot = build_trade_snapshot(row, "entry")
    if thread_id and snapshot:
        discord.send_thread_file(
            thread_id,
            snapshot,
            content=(
                f"📸 **ENTRY SNAPSHOT · {row.get('trade_id')}**\n"
                f"5-minute underlying session · {row.get('play_type')} · "
                f"{row.get('strike')} · contract entry "
                f"{fmt_money(as_float(row.get('entry_price')))}"
            ),
        )

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
    win_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in wins)
        if value is not None
    ]
    loss_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in losses)
        if value is not None
    ]

    win_dollars = [realized_pl_dollars(row) for row in wins]
    loss_dollars = [realized_pl_dollars(row) for row in losses]
    scratch_dollars = [realized_pl_dollars(row) for row in scratches]
    all_dollars = win_dollars + loss_dollars + scratch_dollars

    gross_won = sum(value for value in win_dollars if value > 0)
    gross_lost = abs(sum(value for value in loss_dollars if value < 0))

    return {
        "wins": float(len(wins)),
        "losses": float(len(losses)),
        "scratches": float(len(scratches)),
        "closed": float(len(rows)),
        "win_rate": (len(wins) / len(decided) * 100) if decided else 0.0,
        "gross_won": gross_won,
        "gross_lost": gross_lost,
        "total_pnl": sum(all_dollars),
        "reconstructed": float(sum(result_is_reconstructed(row) for row in rows)),
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
    kind = row.get("call_or_put", "").upper()
    entry, closing, dollars = result_price_details(row)
    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    approx = result_is_reconstructed(row)
    prefix = "≈" if approx else ""

    if row.get("play_type") == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        setup = f"{kind} CREDIT {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)}"
        price_move = (
            f"{fmt_option_price(entry)} CR → "
            f"{fmt_option_price(closing, approximate=approx)} DB"
        )
    else:
        setup = f"LONG {kind} {fmt_strike(as_float(row.get('strike'), 0) or 0)}"
        price_move = (
            f"{fmt_option_price(entry)} DB → "
            f"{fmt_option_price(closing, approximate=approx)} CR"
        )

    return (
        f"• **{trade_id}** · {setup}\n"
        f"  {price_move} · **{outcome} {prefix}{fmt_money(dollars)} ({fmt_pct(pct)})**"
    )

def fmt_metric_money(metrics: dict[str, float], key: str) -> str:
    prefix = "≈" if metrics.get("reconstructed", 0) else ""
    return f"{prefix}{fmt_money(metrics[key])}"


def format_performance_stats(rows: list[dict[str, str]]) -> str:
    completed = closed_rows(rows)
    metrics = result_metrics(completed)
    open_count = len(open_rows(rows))
    return "\n".join([
        "## 📊 Performance Dashboard",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])} Wins** · 🔴 **{int(metrics['losses'])} Losses** · "
            f"➖ **{int(metrics['scratches'])} Scratches**"
        ),
        f"Win rate **{metrics['win_rate']:.0f}%** · Closed trades **{int(metrics['closed'])}**",
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%** · "
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%**"
        ),
        "### Current Exposure",
        f"⏸️ Open/HOLD positions **{open_count}** · Results use **1 contract per trade**",
        f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
    ])[:2000]


def format_strategy_breakdown(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        play_type = row.get("play_type", "PLAY").upper()
        kind = row.get("call_or_put", "").upper()
        label = f"{play_type} {kind}".strip()
        groups.setdefault(label, []).append(row)

    lines = [
        "## 🧠 Strategy Breakdown",
        "Strategies ranked by net result, then expectancy.",
    ]
    if not groups:
        lines.extend(["### Results", "No completed trades yet."])
    else:
        ranked: list[tuple[float, float, str, dict[str, float]]] = []
        for label, group in groups.items():
            metrics = result_metrics(group)
            ranked.append((metrics["total_pnl"], metrics["expectancy_pct"], label, metrics))
        medals = ["🥇", "🥈", "🥉"]
        for index, (_, _, label, metrics) in enumerate(
            sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True)[:8]
        ):
            badge = medals[index] if index < len(medals) else "▫️"
            lines.extend([
                f"### {badge} {label}",
                (
                    f"**Record:** {int(metrics['wins'])}W · {int(metrics['losses'])}L · "
                    f"{int(metrics['scratches'])}S\n"
                    f"**Win rate:** {metrics['win_rate']:.0f}%\n"
                    f"**Won / Lost / Net:** {fmt_metric_money(metrics, 'gross_won')} / "
                    f"{fmt_metric_money(metrics, 'gross_lost')} / "
                    f"{fmt_metric_money(metrics, 'total_pnl')}\n"
                    f"**Avg win / Avg loss:** {metrics['average_win_pct']:+.0f}% / "
                    f"{metrics['average_loss_pct']:+.0f}%\n"
                    f"**Expectancy:** {metrics['expectancy_pct']:+.0f}%"
                ),
            ])
    lines.extend(["### Updated", portable_strftime(now_ct(), "%m/%d/%y %-I:%M %p CT")])
    return "\n".join(lines)

def format_ticker_results(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        ticker = str(row.get("ticker") or "F").upper()
        groups.setdefault(ticker, []).append(row)
    lines = [
        "## Ticker Results",
        "Every completed tracked trade, grouped by underlying.",
    ]
    if not groups:
        lines.append("No completed trades yet.")
    else:
        ranked = sorted(
            groups.items(),
            key=lambda item: result_metrics(item[1])["total_pnl"],
            reverse=True,
        )
        for ticker, group in ranked:
            metrics = result_metrics(group)
            lines.append(
                f"**{ticker}** — {int(metrics['wins'])}W / {int(metrics['losses'])}L "
                f"/ {int(metrics['scratches'])}S · {metrics['win_rate']:.0f}% win rate · "
                f"Net {fmt_metric_money(metrics, 'total_pnl')}"
            )
    lines.append(f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**")
    return "\n".join(lines)[:2000]


def format_daily_recap(
    rows: list[dict[str, str]],
    report_date: date,
    *,
    market_open: bool,
) -> str:
    completed = rows_closed_on(rows, report_date)
    metrics = result_metrics(completed)
    status = "🟢 LIVE" if market_open else "✅ FINAL"
    lines = [
        f"## 📅 Daily Recap · {report_date.strftime('%m/%d/%y')} · {status}",
        "### Results",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Closed Trades",
    ]
    if completed:
        lines.extend(compact_result_line(row) for row in completed[-8:])
    else:
        lines.append("• No trades closed today.")
    carried = open_rows(rows)
    lines.extend([
        "### Positions Carried",
        f"⏸️ **{len(carried)} open/HOLD position(s)**",
        f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
    ])
    return "\n".join(lines)[:2000]

def format_weekly_report(
    rows: list[dict[str, str]], report_date: date, *, final: bool = False
) -> str:
    monday = report_date - timedelta(days=report_date.weekday())
    completed = rows_closed_between(rows, monday, report_date)
    metrics = result_metrics(completed)
    lines = [
        f"## 📆 Weekly Report · {monday.strftime('%m/%d')}–{report_date.strftime('%m/%d/%y')}",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%** · "
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%**"
        ),
    ]
    if completed:
        best = max(completed, key=lambda row: as_float(row.get("pct_gain_loss"), -math.inf) or -math.inf)
        worst = min(completed, key=lambda row: as_float(row.get("pct_gain_loss"), math.inf) or math.inf)
        lines.extend([
            "### Best / Worst",
            f"Best: {compact_result_line(best)[2:]}",
            f"Worst: {compact_result_line(worst)[2:]}",
        ])
    else:
        lines.append("No trades closed this week.")
    lines.append(f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**")
    lines.insert(1, f"**Status:** {'FINAL' if final else 'LIVE'}")
    return "\n".join(lines)[:2000]

def static_server_pages() -> dict[str, str]:
    """Manual channels are intentionally excluded from automation."""
    return {}

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
        "### Current State",
        summary,
        "### Workflow",
        (
            f"**Open trades:** {len(open_rows(rows))}\n"
            f"**Trigger:** {event_name}\n"
            f"**Run:** #{run_number}\n"
            f"**Last check:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M:%S %p CT')}"
        ),
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



def format_result_channel_summary(rows: list[dict[str, str]], outcome: str) -> str:
    selected = [row for row in closed_rows(rows) if row.get("outcome") == outcome]
    metrics = result_metrics(selected)
    if outcome == "WIN":
        title = "## 🟩 Wins Summary"
        total_label = "Total won"
        total_value = fmt_metric_money(metrics, "gross_won")
        average = f"{metrics['average_win_pct']:+.0f}%"
    elif outcome == "LOSS":
        title = "## 🟥 Losses Summary"
        total_label = "Total lost"
        total_value = fmt_metric_money(metrics, "gross_lost")
        average = f"{metrics['average_loss_pct']:+.0f}%"
    else:
        title = "## ⬜ Scratches Summary"
        total_label = "Net"
        total_value = fmt_metric_money(metrics, "total_pnl")
        average = f"{metrics['average_pct']:+.0f}%"
    return "\n".join([
        title,
        "### Record",
        f"**Trades:** {len(selected)}\n**Average result:** {average}",
        "### Money",
        f"**{total_label}:** {total_value}",
        "### Updated",
        portable_strftime(now_ct(), "%m/%d/%y %-I:%M %p CT"),
    ])

def format_channel_audit(discord: DiscordTracker, timestamp: datetime) -> str:
    connected = len(AUTOMATED_CHANNEL_KEYS) - len(discord.missing_channels)
    private_systems = sorted(
        CHANNEL_NAMES[key] for key in SYSTEM_CHANNEL_KEYS
        if key in discord.private_system_channels
    )
    privacy_issues = sorted(
        CHANNEL_NAMES[key] for key in SYSTEM_CHANNEL_KEYS
        if key in discord.channels and key not in discord.private_system_channels
    )
    lines = [
        "## 🔌 Discord Routing Audit",
        "### Connections",
        (
            f"**Automated channels:** {connected}/{len(AUTOMATED_CHANNEL_KEYS)} connected\n"
            f"**Trade journal forum:** Connected\n"
            f"**Required tags:** Connected\n"
            f"**Card format:** Version {DISCORD_FORMAT_VERSION}\n"
            f"**Private system channels:** {len(private_systems)}/{len(SYSTEM_CHANNEL_KEYS)} verified"
        ),
        "### Result",
    ]
    if privacy_issues:
        lines.append(
            "❌ Unsafe system visibility: "
            + ", ".join(f"#{name}" for name in privacy_issues)
            + ". Technical posts to these channels are blocked."
        )
    elif discord.missing_channels:
        lines.append("❌ Missing: " + ", ".join(f"#{name}" for name in discord.missing_channels))
    else:
        lines.append("✅ Trading content is public-facing; diagnostics remain in the private SYSTEM category.")
    lines.extend([
        "### Manual Channels",
        "Welcome, rules, risk management, server guide, and admin notes are not modified.",
        "### Checked",
        portable_strftime(timestamp, "%m/%d/%y %-I:%M %p CT"),
    ])
    return "\n".join(lines)

def publish_channel_audit(
    discord: DiscordTracker,
    state: dict[str, Any],
    timestamp: datetime,
) -> None:
    if not discord.ready:
        return
    content = format_channel_audit(discord, timestamp)
    discord.upsert_channel_message(
        "status",
        state,
        "channel-audit",
        content,
        search_token="Discord Routing Audit",
    )
    if discord.missing_channels:
        discord.upsert_channel_message(
            "errors",
            state,
            "missing-discord-channels",
            "🚨 **Discord routing audit failed**\nMissing: "
            + ", ".join(f"#{name}" for name in discord.missing_channels),
            search_token="Discord routing audit failed",
        )



def format_qualified_scan(
    qualified: list[dict[str, Any]],
    eligible: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    timestamp: datetime,
) -> str:
    lines = [
        f"## ✅ Qualified {TICKER} Option Setups",
        "### Filter Results",
        (
            f"**Passed all filters:** {len(qualified)}\n"
            f"**New eligible:** {len(eligible)}\n"
            f"**Opened:** {len(selected)}"
        ),
        "### Highest-Ranked Setups",
    ]
    if qualified:
        ranked = sorted(qualified, key=lambda candidate: candidate.get("score", 0), reverse=True)
        lines.extend(candidate_brief(candidate) for candidate in ranked[:8])
        if len(ranked) > 8:
            lines.append(f"…and **{len(ranked) - 8}** additional qualified setup(s).")
    else:
        lines.append("No setup passed every filter on this run.")
    lines.extend(["### Scan Time", portable_strftime(timestamp, "%m/%d/%y %-I:%M %p CT")])
    return "\n".join(lines)


def format_scanner_feed(
    stats: dict[str, Any],
    *,
    spot_price: float,
    eligible_count: int,
    selected_count: int,
    closed_count: int,
    hold_count: int,
    open_count: int,
    timestamp: datetime,
) -> str:
    expirations = stats.get("expirations") or []
    expiration_text = "\n".join(
        f"• **{item['bucket']}:** {format_expiration(item['expiration'])}"
        for item in expirations
    ) or "None available"
    by_strategy = stats.get("candidate_counts") or {}
    context = stats.get("market_context") or {}
    failures = context.get("failures") or []
    trend_text = (
        f"**Regime:** {context.get('regime', 'Unavailable')}\n"
        f"**SMA20 / SMA50:** {fmt_option_price(as_float(context.get('sma20')))} / "
        f"{fmt_option_price(as_float(context.get('sma50')))}\n"
        f"**RSI(14):** {round_or_blank(as_float(context.get('rsi14')), 1) or '—'}\n"
        f"**Gate:** {'Passed' if context.get('qualified') else 'Blocked'}"
    )
    if failures:
        trend_text += "\n**Blocked by:** " + "; ".join(failures)
    strategy_text = "\n".join(
        f"• **{label}:** {count}" for label, count in by_strategy.items() if count
    ) or "None"
    return "\n".join([
        f"## 📡 {TICKER} Options Scanner",
        "### Market",
        (
            f"**Time:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M %p CT')}\n"
            f"**{TICKER} spot:** {fmt_option_price(spot_price)}"
        ),
        "### Expirations",
        expiration_text,
        "### Market Regime Gate",
        trend_text,
        "### Contracts",
        (
            f"**Received:** {stats.get('raw_contracts', 0)}\n"
            f"**Inside strike band:** {stats.get('band_contracts', 0)}\n"
            f"**Calls / Puts:** {stats.get('calls', 0)} / {stats.get('puts', 0)}"
        ),
        "### Filter Results",
        (
            f"**Passed:** {stats.get('qualified_candidates', 0)}\n"
            f"**New eligible:** {eligible_count}\n"
            f"**Opened:** {selected_count}"
        ),
        "### Qualified Mix",
        strategy_text,
        "### Lifecycle",
        (
            f"**HOLD:** {hold_count}\n"
            f"**Closed this run:** {closed_count}\n"
            f"**Open total:** {open_count}"
        ),
    ])


def format_closed_scanner_feed(rows: list[dict[str, str]], timestamp: datetime) -> str:
    return "\n".join([
        f"## 📡 {TICKER} Options Scanner",
        "### Market",
        (
            f"**Status:** Closed\n"
            f"**Time:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M %p CT')}"
        ),
        "### Maintenance Sync",
        (
            "No option-chain scan was performed.\n"
            f"**Open/HOLD positions:** {len(open_rows(rows))}"
        ),
    ])

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
    discord.upsert_channel_message(
        "ticker_results",
        state,
        "ticker-results",
        format_ticker_results(rows),
    )
    discord.upsert_channel_message(
        "wins",
        state,
        "wins-summary",
        format_result_channel_summary(rows, "WIN"),
    )
    discord.upsert_channel_message(
        "losses",
        state,
        "losses-summary",
        format_result_channel_summary(rows, "LOSS"),
    )
    discord.upsert_channel_message(
        "scratches",
        state,
        "scratches-summary",
        format_result_channel_summary(rows, "SCRATCH"),
    )


def sync_reports(
    discord: DiscordTracker,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_open: bool,
) -> None:
    if not discord.ready:
        return

    today = timestamp.date()
    historical_dates = {
        parsed.date()
        for row in closed_rows(rows)
        if (parsed := parse_iso(row.get("closed_at"))) is not None
    }
    daily_dates = [today]
    for report_date in daily_dates:
        date_key = report_date.isoformat()
        daily = format_daily_recap(
            rows,
            report_date,
            market_open=market_open and report_date == today,
        )
        discord.upsert_channel_message(
            "daily_recap",
            state,
            f"daily-recap:{date_key}",
            daily,
            search_token=f"Daily Recap · {report_date.strftime('%m/%d/%y')}",
        )

    week_starts = {
        report_date - timedelta(days=report_date.weekday())
        for report_date in daily_dates
    }
    for monday in sorted(week_starts)[-12:]:
        current_week = monday <= today <= monday + timedelta(days=6)
        friday = monday + timedelta(days=4)
        report_end = min(today, friday) if current_week else friday
        iso_year, iso_week, _ = monday.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly = format_weekly_report(
            rows, report_end, final=(not current_week or today >= friday)
        )
        discord.upsert_channel_message(
            "weekly_report",
            state,
            f"weekly-report:{week_key}",
            weekly,
            search_token=f"Weekly Report · {monday.strftime('%m/%d')}",
        )

    state["daily_report_date"] = today.isoformat()
    iso_year, iso_week, _ = today.isocalendar()
    state["weekly_report_key"] = f"{iso_year}-W{iso_week:02d}"


# ---------------------------------------------------------------------------
# Main orchestration
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
                f"<span class='pl'>{fmt_money(realized_pl_dollars(row))} "
                f"({fmt_pct(as_float(row.get('pct_gain_loss')))})</span></div></div>"
                f"<div class='plsub'>"
                f"Entry ${parse_entry_price(row):.2f} ({fmt_money(entry_contract_value(row))}) · "
                f"Exit {'≈' if result_is_reconstructed(row) else ''}${(exit_price(row) or 0):.2f} "
                f"({'≈' if result_is_reconstructed(row) else ''}{fmt_money(exit_contract_value(row))}) · "
                f"Opened {esc((row.get('timestamp') or '')[:16].replace('T',' '))} · "
                f"Closed {esc((row.get('closed_at') or '')[:16].replace('T',' '))} · "
                f"MFE {fmt_pct(as_float(row.get('max_favorable_pct')))} · MAE {fmt_pct(as_float(row.get('max_adverse_pct')))}</div>"
                f"{legs}</div>"
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


def scan_candidates(
    spot_price: float,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    expirations = get_expirations(TICKER)
    near_expirations, swing_expirations = pick_expirations(expirations, now_ct().date())
    try:
        intraday_history = get_intraday_history(TICKER)
    except (TradierError, requests.RequestException):
        intraday_history = []
    market_context = directional_market_context(
        get_daily_history(TICKER),
        spot_price,
        intraday_history,
    )
    candidate_expirations: list[tuple[str, str]] = []
    if near_expirations:
        candidate_expirations.append((near_expirations[0], "REGULAR"))
    if swing_expirations:
        candidate_expirations.append((swing_expirations[0], "SWING"))

    stats: dict[str, Any] = {
        "expirations": [],
        "raw_contracts": 0,
        "band_contracts": 0,
        "calls": 0,
        "puts": 0,
        "qualified_candidates": 0,
        "candidate_counts": {},
        "market_context": market_context,
    }
    candidates: list[dict[str, Any]] = []
    quote_map: dict[str, dict[str, Any]] = {}

    if not market_context["qualified"]:
        return candidates, quote_map, stats

    def add_candidates(label: str, found: list[dict[str, Any]]) -> None:
        candidates.extend(found)
        stats["candidate_counts"][label] = stats["candidate_counts"].get(label, 0) + len(found)

    for expiration, bucket in candidate_expirations:
        stats["expirations"].append({"expiration": expiration, "bucket": bucket})
        allowed_strikes = set(filter_strikes(get_strikes(TICKER, expiration), spot_price))
        raw_chain = get_chain(TICKER, expiration)
        stats["raw_contracts"] += len(raw_chain)
        chain = [
            option for option in raw_chain
            if float(option.get("strike", -1)) in allowed_strikes
        ]
        stats["band_contracts"] += len(chain)
        for option in chain:
            if option.get("symbol"):
                quote_map[option["symbol"]] = option
        calls = [option for option in chain if option.get("option_type") == "call"]
        puts = [option for option in chain if option.get("option_type") == "put"]
        stats["calls"] += len(calls)
        stats["puts"] += len(puts)
        regime = market_context["regime"]
        if regime == "BULLISH / CONTROLLED":
            add_candidates(
                f"{bucket} long calls",
                scan_single_legs(calls, "call", expiration, bucket, market_context),
            )
            if bucket == "SWING":
                add_candidates("Bull put spreads", scan_credit_spreads(puts, "put", expiration, market_context))
        elif regime == "BEARISH / CONTROLLED":
            add_candidates(
                f"{bucket} long puts",
                scan_single_legs(puts, "put", expiration, bucket, market_context),
            )
            if bucket == "SWING":
                add_candidates("Bear call spreads", scan_credit_spreads(calls, "call", expiration, market_context))
        elif regime == "NEUTRAL / RANGE" and bucket == "SWING":
            add_candidates("Call credit spreads", scan_credit_spreads(calls, "call", expiration, market_context))
            add_candidates("Put credit spreads", scan_credit_spreads(puts, "put", expiration, market_context))
    stats["qualified_candidates"] = len(candidates)
    return candidates, quote_map, stats

def report_error(discord: DiscordTracker | None, message: str) -> None:
    safe_message = message
    for secret in (TRADIER_TOKEN, DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL):
        if secret:
            safe_message = safe_message.replace(secret, "[REDACTED]")
    print(safe_message, file=sys.stderr)
    if discord and discord.ready:
        safe_discord_call("error alert", lambda: discord.send_channel("errors", content=f"🚨 **{TICKER} scanner error**\n```{safe_message[:1500]}```"))


def intelligence_only_main() -> int:
    """Run the low-frequency Ford briefing without scanning option chains."""
    timestamp = now_ct()
    rows = read_log()
    try:
        discord = initialize_discord()
    except DiscordError as exc:
        report_error(None, f"TradeBot setup failed: {exc}")
        return 1
    report_state = read_report_state()
    try:
        spot = get_quote(TICKER)
        spot_price = as_float((spot or {}).get("last"))
        history = get_daily_history(TICKER, days=120)
        if spot_price is None or not history:
            raise TradierError("Ford quote or daily history was unavailable for the intelligence briefing")
        render_market_chart(history, spot_price)
        publish_ford_intelligence(
            discord,
            report_state,
            rows,
            history,
            spot_price,
            timestamp,
        )
        sync_ford_events(discord, report_state)
        before_open = (
            timestamp.hour < MARKET_OPEN[0]
            or (timestamp.hour == MARKET_OPEN[0] and timestamp.minute < MARKET_OPEN[1])
        )
        session_label = "premarket" if before_open else "after-market"
        if (
            session_label == "premarket"
            and report_state.get("chart_snapshot_date") != timestamp.date().isoformat()
        ):
            upload = discord.send_channel_file(
                "charts",
                CHART_SCREENSHOT_PATH,
                content=(
                    f"📊 **PREMARKET FORD CHART · {timestamp.date().isoformat()}**\n"
                    f"Last price ${spot_price:.2f} · indicators, support, and resistance are marked."
                ),
            )
            if upload:
                report_state["chart_snapshot_date"] = timestamp.date().isoformat()
        write_report_state(report_state)
        print(f"Ford {session_label} intelligence briefing complete.")
        return 0
    except (TradierError, DiscordError, requests.RequestException, ValueError, KeyError) as exc:
        report_error(discord, f"Ford intelligence briefing failed: {type(exc).__name__}: {exc}")
        write_report_state(report_state)
        return 1


def main(*, publish_shared: bool = True) -> int:
    if "--intelligence-only" in sys.argv[1:]:
        return intelligence_only_main()
    timestamp = now_ct()
    rows = read_log()
    write_log(rows)  # immediately migrate old CSV headers/IDs safely

    discord: DiscordTracker | None = None
    try:
        discord = initialize_discord()
    except DiscordError as exc:
        report_error(None, f"TradeBot setup failed: {exc}")
        return 1

    report_state = read_report_state()
    migrated_cards = 0
    if publish_shared:
        if DISCORD_MIGRATE_LEGACY_MESSAGES:
            try:
                migrated_cards = migrate_recent_bot_messages_to_cards(discord, report_state)
            except DiscordError as exc:
                print(f"Discord card migration failed: {exc}", file=sys.stderr)
        if migrated_cards:
            print(f"Discord card migration: converted {migrated_cards} recent message(s).")
        safe_discord_call(
            "channel audit",
            lambda: publish_channel_audit(discord, report_state, timestamp),
        )
        safe_discord_call(
            "server pages",
            lambda: ensure_static_server_pages(discord, report_state),
        )
        safe_discord_call(
            "performance pages",
            lambda: update_performance_pages(discord, report_state, rows),
        )

    closed_results_backfilled = 0
    if publish_shared:
        try:
            closed_results_backfilled = sync_closed_result_channels(rows, discord, report_state)
        except DiscordError as exc:
            print(f"Discord closed-result backfill failed: {exc}", file=sys.stderr)
    if closed_results_backfilled:
        print(f"Discord result backfill: posted {closed_results_backfilled} closed result(s).")

    backfilled = (
        sync_existing_open_threads(rows, discord, refresh_existing=False)
        if publish_shared
        else 0
    )
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
        safe_discord_call(
            "report sync",
            lambda: sync_reports(
                discord,
                report_state,
                rows,
                timestamp,
                market_open=False,
            ),
        )
        safe_discord_call(
            "closed scanner feed",
            lambda: discord.upsert_channel_message(
                "scanner_feed",
                report_state,
                f"scanner-closed:{timestamp.date().isoformat()}",
                format_closed_scanner_feed(rows, timestamp),
                search_token="Market closed. No option-chain scan was performed.",
            ),
        )
        safe_discord_call(
            "workflow log",
            lambda: post_workflow_log(
                discord,
                timestamp=timestamp,
                result=f"OK · market closed · {len(open_rows(rows))} open",
            ),
        )
        render_dashboard(None, rows, f"Market closed at {portable_strftime(timestamp, '%-I:%M %p %Z')}; maintenance sync only.")
        write_log(rows)
        write_report_state(report_state)
        print(f"Market closed ({timestamp.isoformat()}); maintenance sync complete.")
        return 0

    try:
        spot = get_quote(TICKER)
        if not spot or as_float(spot.get("last")) is None:
            raise TradierError(f"{TICKER} spot quote was unavailable")
        spot_price = float(spot["last"])
        history = get_daily_history(TICKER, days=120)
        if history:
            render_market_chart(history, spot_price)
            safe_discord_call(
                f"{TICKER} market map",
                lambda: discord.upsert_channel_message(
                    "charts",
                    report_state,
                    f"{TICKER.lower()}-market-map",
                    market_map_text(history, spot_price),
                    search_token=f"{TICKER} Market Map",
                ),
            )
            chart_date_key = f"chart_snapshot_date:{TICKER}"
            if report_state.get(chart_date_key) != timestamp.date().isoformat():
                upload = discord.send_channel_file(
                    "charts",
                    CHART_SCREENSHOT_PATH,
                    content=(
                        f"📊 **DAILY {TICKER} CHART · {timestamp.date().isoformat()}**\n"
                        f"Spot ${spot_price:.2f} · indicators, support, and resistance are marked."
                    ),
                )
                if upload:
                    report_state[chart_date_key] = timestamp.date().isoformat()

        # Reprice every existing open play in one or more batched quote calls.
        currently_open = open_rows(rows) if publish_shared else []
        open_quote_map = get_quotes(symbols_for_rows(currently_open), include_greeks=True)
        refreshed_market_fields = refresh_open_entry_market_data(currently_open, open_quote_map)
        if refreshed_market_fields:
            print(f"Refreshed {refreshed_market_fields} missing IV/OI field(s) on open trades.")
        closed_count = 0
        material_updates = 0
        hold_count = 0
        for row in list(currently_open):
            evaluation = evaluate_open_row(row, open_quote_map, timestamp)
            if evaluation.get("pl_pct") is None:
                hold_count += 1
                safe_discord_call(
                    "position board quote warning",
                    lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
                )
                continue
            signal = evaluation.get("signal")
            if signal in {"STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE"}:
                close_row(row, evaluation, timestamp)
                safe_discord_call("close routing", lambda r=row, e=evaluation: post_close(r, e, discord, report_state))
                closed_count += 1
            else:
                hold_count += 1
                before = row.get("last_discord_update_at")
                safe_discord_call("journal position update", lambda r=row, e=evaluation: post_material_update(r, e, discord, timestamp))
                safe_discord_call(
                    "position board sync",
                    lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
                )
                if row.get("last_discord_update_at") != before:
                    material_updates += 1

        # Scan for new candidates and choose the highest-quality unique set.
        candidates, candidate_quote_map, scan_stats = scan_candidates(spot_price)
        eligible = [candidate for candidate in candidates if not recently_tracked(rows, candidate, timestamp)]
        eligible.sort(key=lambda candidate: candidate.get("score", 0), reverse=True)
        selected = eligible

        new_rows: list[dict[str, str]] = []
        for candidate in selected:
            row = candidate_to_row(candidate, rows, timestamp)
            rows.append(row)
            new_rows.append(row)
            safe_discord_call("new trade post", lambda r=row: post_new_trade(r, discord, report_state))

        # Give newly opened rows their initial zero-P&L values and preserve all state.
        all_quotes = {**open_quote_map, **candidate_quote_map}
        for row in new_rows:
            evaluation = evaluate_open_row(row, all_quotes, timestamp)
            if evaluation.get("pl_pct") is None:
                row["current_pl_pct"] = "0"
                row["current_pl_dollars"] = "0"
                evaluation = stored_open_evaluation(row)
            hold_count += 1
            safe_discord_call(
                "new position board sync",
                lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
            )

        write_log(rows)
        summary = (
            f"Spot ${spot_price:.2f} · {scan_stats.get('raw_contracts', 0)} contracts scanned · "
            f"{scan_stats.get('qualified_candidates', 0)} passed filters · {len(new_rows)} opened · "
            f"{closed_count} closed · {hold_count} HOLD · {len(open_rows(rows))} open total."
        )
        render_dashboard(spot, rows, summary)
        if publish_shared:
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
                "report sync",
                lambda: sync_reports(
                    discord,
                    report_state,
                    rows,
                    timestamp,
                    market_open=True,
                ),
            )
        run_number = os.environ.get("GITHUB_RUN_NUMBER", timestamp.strftime("%Y%m%d%H%M"))
        safe_discord_call(
            "qualified scan feed",
            lambda: discord.upsert_channel_message(
                "qualified",
                report_state,
                f"qualified-scan:{TICKER}:{run_number}",
                format_qualified_scan(candidates, eligible, selected, timestamp),
                search_token=f"Qualified {TICKER} Option Setups",
            ),
        )
        safe_discord_call(
            "scanner feed",
            lambda: discord.upsert_channel_message(
                "scanner_feed",
                report_state,
                f"scanner-run:{TICKER}:{run_number}",
                format_scanner_feed(
                    scan_stats,
                    spot_price=spot_price,
                    eligible_count=len(eligible),
                    selected_count=len(new_rows),
                    closed_count=closed_count,
                    hold_count=hold_count,
                    open_count=len(open_rows(rows)),
                    timestamp=timestamp,
                ),
                search_token=f"{TICKER} Options Scanner",
            ),
        )
        if publish_shared:
            safe_discord_call(
                "workflow log",
                lambda: post_workflow_log(
                    discord,
                    timestamp=timestamp,
                    result=f"OK · {summary}",
                ),
            )

        if not discord.ready and (new_rows or closed_count):
            notify_webhook([summary], title=f"{TICKER} options scan")

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
