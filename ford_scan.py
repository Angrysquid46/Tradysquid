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
import hashlib
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
DISCORD_FORMAT_VERSION = "8"

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

AUTOMATED_CHANNEL_KEYS = [
    "scanner_feed",
    "qualified",
    "entry",
    "updates",
    "exit",
    "wins",
    "losses",
    "scratches",
    "daily_recap",
    "weekly_report",
    "performance_stats",
    "strategy_breakdown",
    "status",
    "errors",
    "workflow_log",
]

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
    if value is None:
        return "—"
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


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
        return direct
    raw = (row.get("cost_or_credit") or "").replace("credit", "").strip()
    return as_float(raw, 0.0) or 0.0


def exit_price(row: dict[str, str]) -> float | None:
    """Tracked closing premium/debit. Reconstructs old rows only when necessary."""
    stored = as_float(row.get("exit_price"))
    if stored is not None:
        return stored

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
        return round(entry - (realized / 100), 4)
    return round(entry + (realized / 100), 4)


def entry_contract_value(row: dict[str, str]) -> float:
    return round(parse_entry_price(row) * 100, 2)


def exit_contract_value(row: dict[str, str]) -> float | None:
    price = exit_price(row)
    return None if price is None else round(price * 100, 2)


def result_is_reconstructed(row: dict[str, str]) -> bool:
    return row.get("result_price_source") == "RECONSTRUCTED"


def realized_pl_dollars(row: dict[str, str]) -> float:
    """One-contract result calculated from the stored entry and exit premiums."""
    stored = as_float(row.get("realized_pl_dollars"))
    if stored is not None:
        return stored

    entry = parse_entry_price(row)
    closing = exit_price(row)
    if closing is not None:
        if row.get("play_type") == "SPREAD":
            return round((entry - closing) * 100, 2)
        return round((closing - entry) * 100, 2)

    current = as_float(row.get("current_pl_dollars"))
    if current is not None and row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}:
        return current

    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    return round(entry * pct, 2)


def result_amount_prefix(row: dict[str, str]) -> str:
    return "≈" if result_is_reconstructed(row) else ""


def result_price_details(row: dict[str, str]) -> tuple[float, float | None, float]:
    return parse_entry_price(row), exit_price(row), realized_pl_dollars(row)


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
    expiration = format_expiration(row.get("expiration", ""))
    entry = parse_entry_price(row)
    breakeven = as_float(row.get("breakeven"))
    delta = as_float(row.get("delta_at_entry"))
    oi = int(as_float(row.get("open_interest_at_entry"), 0.0) or 0)
    iv = as_float(row.get("iv_at_entry"))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 F {fmt_strike(sell_strike)} {kind} / "
            f"🟢 BUY 1 F {fmt_strike(buy_strike)} {kind}"
        )
        stop = entry * SPREAD_STOP_MULTIPLE
        target = entry * (1 - SPREAD_TAKE_PROFIT_PCT)
        stop_pl = (entry - stop) * 100
        target_pl = (entry - target) * 100
        price_line = (
            f"ENTRY **${entry:.2f} CR** ({fmt_money(entry * 100)}) · "
            f"STOP **${stop:.2f} DB** ({fmt_money(stop_pl)}) · "
            f"TP **${target:.2f} DB** ({fmt_money(target_pl)})"
        )
        risk_line = (
            f"MAX PROFIT **{fmt_money(as_float(row.get('max_profit')))}** · "
            f"MAX RISK **{fmt_money(as_float(row.get('max_risk')))}** · "
            f"BE **${breakeven:.2f}**" if breakeven is not None else
            f"MAX PROFIT **{fmt_money(as_float(row.get('max_profit')))}** · "
            f"MAX RISK **{fmt_money(as_float(row.get('max_risk')))}**"
        )
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"🟢 BUY 1 F {strike} {kind}"
        stop = entry * (1 - SINGLE_STOP_PCT)
        target = entry * (1 + SINGLE_TAKE_PROFIT_PCT)
        price_line = (
            f"ENTRY **${entry:.2f} DB** ({fmt_money(entry * 100)}) · "
            f"STOP **${stop:.2f} CR** ({fmt_money((stop - entry) * 100)}) · "
            f"TP **${target:.2f} CR** ({fmt_money((target - entry) * 100)})"
        )
        risk_line = (
            f"MAX RISK **{fmt_money(as_float(row.get('max_risk')))}** · "
            f"BE **${breakeven:.2f}**" if breakeven is not None else
            f"MAX RISK **{fmt_money(as_float(row.get('max_risk')))}**"
        )

    iv_text = "—" if iv is None else f"{iv * 100:.1f}%"
    delta_text = "—" if delta is None else f"{delta:+.2f}"
    lines = [
        f"🟢 **F #{sequence} · ENTRY · {strategy}**",
        f"{setup} · EXP **{expiration}**",
        price_line,
        risk_line,
        f"Δ **{delta_text}** · IV **{iv_text}** · OI **{oi:,}**",
    ]
    if include_link:
        lines.append(f"[Open trade journal]({include_link})")
    return "\n".join(lines)[:2000]

def position_update_text(
    row: dict[str, str],
    evaluation: dict[str, Any],
    include_link: str = "",
) -> str:
    trade_id = row.get("trade_id") or "F-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    signal = evaluation.get("signal") or row.get("last_signal") or "HOLD"
    entry = parse_entry_price(row)
    mark = as_float(evaluation.get("mark"), as_float(row.get("last_mark")))
    pl_dollars = as_float(evaluation.get("pl_dollars"), as_float(row.get("current_pl_dollars")))
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("current_pl_pct")))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"SELL 1 F {fmt_strike(sell_strike)} {kind} / "
            f"BUY 1 F {fmt_strike(buy_strike)} {kind}"
        )
        entry_label = f"${entry:.2f} CR"
        mark_label = "—" if mark is None else f"${mark:.2f} DB"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"BUY 1 F {strike} {kind}"
        entry_label = f"${entry:.2f} DB"
        mark_label = "—" if mark is None else f"${mark:.2f} CR"

    quote_note = evaluation.get("note") or ""
    state_label = "HOLD" if signal == "HOLD" else signal
    lines = [
        f"⏸️ **F #{sequence} · {state_label} · {strategy}**",
        f"{setup} · EXP **{expiration}**",
        f"ENTRY **{entry_label}** · CURRENT **{mark_label}**",
        f"P/L **{fmt_money(pl_dollars)}** ({fmt_pct(pl_pct)})",
        (
            f"MFE **{fmt_pct(as_float(row.get('max_favorable_pct')))}** · "
            f"MAE **{fmt_pct(as_float(row.get('max_adverse_pct')))}**"
        ),
        f"Last checked **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**",
    ]
    if quote_note:
        lines.append(f"⚠️ {quote_note}")
    if include_link:
        lines.append(f"[Open trade journal]({include_link})")
    return "\n".join(lines)[:2000]

def close_alert_text(row: dict[str, str], evaluation: dict[str, Any], include_link: str = "") -> str:
    outcome = row.get("outcome", "CLOSED")
    icon = {"WIN": "🏆", "LOSS": "🔴", "SCRATCH": "➖"}.get(outcome, "📕")
    trade_id = row.get("trade_id") or "F-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry, closing, stored_pl = result_price_details(row)
    pl_dollars = as_float(evaluation.get("pl_dollars"), stored_pl)
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("pct_gain_loss"), 0.0))
    close_reason = evaluation.get("signal") or row.get("last_signal") or "CLOSED"
    approx = result_amount_prefix(row)

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 F {fmt_strike(sell_strike)} {kind} / "
            f"🟢 BUY 1 F {fmt_strike(buy_strike)} {kind}"
        )
        entry_label = f"${entry:.4f}".rstrip("0").rstrip(".") + " CR"
        exit_label = "—" if closing is None else f"{approx}${closing:.4f}".rstrip("0").rstrip(".") + " DB"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"LONG {kind}"
        setup = f"🟢 BUY 1 F {strike} {kind}"
        entry_label = f"${entry:.4f}".rstrip("0").rstrip(".") + " DB"
        exit_label = "—" if closing is None else f"{approx}${closing:.4f}".rstrip("0").rstrip(".") + " CR"

    entry_value = entry_contract_value(row)
    exit_value = exit_contract_value(row)
    exit_value_text = "—" if exit_value is None else f"{approx}{fmt_money(exit_value)}"
    pnl_text = f"{approx}{fmt_money(pl_dollars)}"
    closed_at = parse_iso(row.get("closed_at"))
    closed_text = closed_at.strftime("%m/%d/%y %-I:%M %p CT") if closed_at else "—"

    lines = [
        f"{icon} **F #{sequence} · {outcome} · {strategy}**",
        f"{setup} · EXP **{expiration}**",
        f"ENTRY **{entry_label}** ({fmt_money(entry_value)}) · EXIT **{exit_label}** ({exit_value_text})",
        f"P/L **{pnl_text}** ({fmt_pct(pl_pct)}) · CLOSE **{close_reason}**",
        f"Closed **{closed_text}**",
    ]
    if include_link:
        lines.append(f"[Open completed trade journal]({include_link})")
    return "\n".join(lines)[:2000]

def qualified_trade_text(row: dict[str, str], include_link: str = "") -> str:
    trade_id = row.get("trade_id") or "F-UNKNOWN"
    sequence = trade_id.rsplit("-", 1)[-1]
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry = parse_entry_price(row)
    pop = as_float(row.get("pop_estimate"))
    oi = int(as_float(row.get("open_interest_at_entry"), 0.0) or 0)
    width = as_float(row.get("bid_ask_width_at_entry"))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{kind} CREDIT SPREAD"
        setup = (
            f"SELL 1 F {fmt_strike(sell_strike)} {kind} / "
            f"BUY 1 F {fmt_strike(buy_strike)} {kind}"
        )
        price = f"${entry:.2f} CR ({fmt_money(entry * 100)})"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"{play_type} LONG {kind}"
        setup = f"BUY 1 F {strike} {kind}"
        price = f"${entry:.2f} DB ({fmt_money(entry * 100)})"

    lines = [
        f"✅ **F #{sequence} · QUALIFIED · {strategy}**",
        f"{setup} · EXP **{expiration}**",
        f"ENTRY **{price}**",
        (
            f"POP/DELTA EST **{fmt_pct(pop)}** · OI **{oi:,}** · "
            f"BID/ASK WIDTH **{fmt_money(width)}**"
        ),
    ]
    if include_link:
        lines.append(f"[Open trade journal]({include_link})")
    return "\n".join(lines)[:2000]


def candidate_brief(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("call_or_put", "")).upper()
    play_type = str(candidate.get("play_type", "PLAY")).upper()
    expiration = format_expiration(str(candidate.get("expiration", "")))
    entry = as_float(candidate.get("entry_price"), 0.0) or 0.0
    score = as_float(candidate.get("score"), 0.0) or 0.0
    if play_type == "SPREAD":
        setup = f"{kind} CREDIT {candidate.get('strike', '—')}"
        price = f"${entry:.2f} CR"
    else:
        setup = f"{play_type} {kind} {candidate.get('strike', '—')}"
        price = f"${entry:.2f} DB"
    return f"• **{setup}** · EXP {expiration} · {price} · score {score:.1f}"


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

    if row["outcome"] in {"WIN", "LOSS", "SCRATCH"}:
        had_exit_price = bool(row.get("exit_price"))
        inferred_exit = exit_price(row)
        if inferred_exit is not None and not row.get("exit_price"):
            row["exit_price"] = round_or_blank(inferred_exit, 4)
        if not row.get("result_price_source"):
            row["result_price_source"] = "TRACKED" if had_exit_price else "RECONSTRUCTED"
        row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 2)
        row["exit_contract_value"] = round_or_blank(exit_contract_value(row), 2)
        if not row.get("realized_pl_dollars"):
            row["realized_pl_dollars"] = round_or_blank(realized_pl_dollars(row), 2)

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
    tracked_exit = as_float(evaluation.get("mark"))
    row["exit_price"] = round_or_blank(tracked_exit, 4)
    row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 2)
    row["exit_contract_value"] = round_or_blank(
        None if tracked_exit is None else tracked_exit * 100,
        2,
    )
    row["realized_pl_dollars"] = round_or_blank(as_float(evaluation.get("pl_dollars"), 0.0), 2)
    row["result_price_source"] = "TRACKED"
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
        self.missing_channels: list[str] = []

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

        missing_tags = sorted(key for key in ("OPEN", "HOLDING", "WIN", "LOSS", "SCRATCH") if key not in self.tag_ids)
        if missing_tags:
            raise DiscordError(f"Missing required trade-journal forum tags: {', '.join(missing_tags)}")
        self.missing_channels = [
            CHANNEL_NAMES[key]
            for key in AUTOMATED_CHANNEL_KEYS
            if key not in self.channels
        ]
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
        search_token: str = "",
    ) -> str:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return ""
        messages = state.setdefault("messages", {})
        hashes = state.setdefault("message_hashes", {})
        message_id = str(messages.get(state_key) or "")
        clipped_content = content[:2000]
        content_hash = hashlib.sha256(clipped_content.encode("utf-8")).hexdigest()
        payload = {
            "content": clipped_content,
            "embeds": [],
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
                    if author.get("bot") and search_token in (message.get("content") or ""):
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

def stored_open_evaluation(row: dict[str, str]) -> dict[str, Any]:
    return {
        "signal": "HOLD",
        "mark": as_float(row.get("last_mark")),
        "pl_dollars": as_float(row.get("current_pl_dollars")),
        "pl_pct": as_float(row.get("current_pl_pct")),
        "note": "",
    }


def sync_open_trade_cards(
    row: dict[str, str],
    discord: DiscordTracker,
    report_state: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
) -> None:
    if not discord.ready or row.get("outcome") != "OPEN":
        return
    trade_id = row.get("trade_id", "")
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    current = evaluation or stored_open_evaluation(row)
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
        discord.set_thread_status(thread_id, "HOLDING")
        row["discord_status"] = "HOLDING"


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
    for row in sorted(closed_rows(rows), key=lambda item: item.get("closed_at") or item.get("timestamp") or ""):
        trade_id = row.get("trade_id", "")
        result_channel = {"WIN": "wins", "LOSS": "losses", "SCRATCH": "scratches"}.get(row.get("outcome", ""))
        if not trade_id or not result_channel:
            continue
        link = thread_link(row.get("discord_thread_id", ""))
        content = close_alert_text(row, stored_close_evaluation(row), link)
        discord.upsert_trade_message("exit", report_state, "exit", trade_id, content)
        discord.upsert_trade_result(result_channel, report_state, trade_id, content)
        discord.delete_trade_message("updates", report_state, "position", trade_id)
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
        discord.send_thread(thread_id, close_alert_text(row, evaluation))
        discord.set_thread_status(thread_id, row["outcome"], archive=True)
    discord.upsert_trade_message("exit", report_state, "exit", row.get("trade_id", ""), content)
    result_channel = {"WIN": "wins", "LOSS": "losses", "SCRATCH": "scratches"}.get(row["outcome"])
    if result_channel:
        discord.upsert_trade_result(result_channel, report_state, row.get("trade_id", ""), content)
        mark_closed_result_routed(row, report_state)
    discord.delete_trade_message("updates", report_state, "position", row.get("trade_id", ""))
    row["discord_status"] = row["outcome"]
    row["last_discord_signal"] = evaluation.get("signal", "CLOSE")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 1)
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
    sync_open_trade_cards(row, discord, report_state)

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
    approx = result_amount_prefix(row)

    if row.get("play_type") == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        setup = f"{kind} CREDIT {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)}"
        price_move = (
            f"${entry:.4f}".rstrip("0").rstrip(".") + " CR → " +
            ("—" if closing is None else f"{approx}${closing:.4f}".rstrip("0").rstrip(".") + " DB")
        )
    else:
        setup = f"LONG {kind} {fmt_strike(as_float(row.get('strike'), 0) or 0)}"
        price_move = (
            f"${entry:.4f}".rstrip("0").rstrip(".") + " DB → " +
            ("—" if closing is None else f"{approx}${closing:.4f}".rstrip("0").rstrip(".") + " CR")
        )

    return (
        f"• **{trade_id}** {setup} · {price_move} · "
        f"{outcome} · {approx}{fmt_money(dollars)} ({pct:+.1f}%)"
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
        f"Win rate **{metrics['win_rate']:.1f}%** · Closed trades **{int(metrics['closed'])}**",
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Avg win **{metrics['average_win_pct']:+.1f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.1f}%** · "
            f"Expectancy **{metrics['expectancy_pct']:+.1f}%**"
        ),
        "### Current Exposure",
        f"⏸️ Open/HOLD positions **{open_count}** · Results use **1 contract per trade**",
        f"Updated **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**",
    ])[:2000]

def format_strategy_breakdown(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        play_type = row.get("play_type", "PLAY").upper()
        kind = row.get("call_or_put", "").upper()
        label = f"{play_type} {kind}".strip()
        groups.setdefault(label, []).append(row)

    lines = ["## 🧠 Strategy Breakdown", "Ranked by net result, then expectancy."]
    if not groups:
        lines.append("No completed trades yet.")
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
                    f"Record **{int(metrics['wins'])}W-{int(metrics['losses'])}L-"
                    f"{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.1f}%**"
                ),
                (
                    f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
                    f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
                    f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
                ),
                (
                    f"Avg win **{metrics['average_win_pct']:+.1f}%** · "
                    f"Avg loss **{metrics['average_loss_pct']:+.1f}%** · "
                    f"Expectancy **{metrics['expectancy_pct']:+.1f}%**"
                ),
            ])
    lines.append(f"Updated **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**")
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
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.1f}%**"
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
        f"Updated **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**",
    ])
    return "\n".join(lines)[:2000]

def format_weekly_report(rows: list[dict[str, str]], report_date: date) -> str:
    monday = report_date - timedelta(days=report_date.weekday())
    completed = rows_closed_between(rows, monday, report_date)
    metrics = result_metrics(completed)
    lines = [
        f"## 📆 Weekly Report · {monday.strftime('%m/%d')}–{report_date.strftime('%m/%d/%y')}",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.1f}%**"
        ),
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Expectancy **{metrics['expectancy_pct']:+.1f}%** · "
            f"Avg win **{metrics['average_win_pct']:+.1f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.1f}%**"
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
    lines.append(f"Updated **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**")
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


def format_result_channel_summary(rows: list[dict[str, str]], outcome: str) -> str:
    selected = [row for row in closed_rows(rows) if row.get("outcome") == outcome]
    metrics = result_metrics(selected)
    if outcome == "WIN":
        title = "## 🏆 Wins"
        total_line = f"Total won **{fmt_metric_money(metrics, 'gross_won')}**"
        avg_line = f"Average win **{metrics['average_win_pct']:+.1f}%**"
    elif outcome == "LOSS":
        title = "## 🔴 Losses"
        total_line = f"Total lost **{fmt_metric_money(metrics, 'gross_lost')}**"
        avg_line = f"Average loss **{metrics['average_loss_pct']:+.1f}%**"
    else:
        title = "## ➖ Scratches"
        total_line = f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        avg_line = f"Average result **{metrics['average_pct']:+.1f}%**"
    return "\n".join([
        title,
        f"Trades **{len(selected)}** · {total_line}",
        avg_line,
        f"Updated **{now_ct().strftime('%m/%d/%y %-I:%M %p CT')}**",
    ])

def format_channel_audit(discord: DiscordTracker, timestamp: datetime) -> str:
    connected = len(AUTOMATED_CHANNEL_KEYS) - len(discord.missing_channels)
    lines = [
        "## 🔌 Discord Routing Audit",
        f"Automated channels **{connected}/{len(AUTOMATED_CHANNEL_KEYS)} connected**",
        "Trade journal forum **connected** · Required tags **connected**",
    ]
    if discord.missing_channels:
        lines.append("❌ Missing: " + ", ".join(f"#{name}" for name in discord.missing_channels))
    else:
        lines.append("✅ Scanner, trade lifecycle, results, reports, performance, and system routing verified.")
    lines.append("Manual channels are intentionally not modified by TradeBot.")
    lines.append(f"Checked **{timestamp.strftime('%m/%d/%y %-I:%M %p CT')}**")
    return "\n".join(lines)[:2000]


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
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    lines = [
        f"## ✅ Qualified Scan · Run #{run_number}",
        (
            f"Passed all filters **{len(qualified)}** · "
            f"New eligible **{len(eligible)}** · Opened **{len(selected)}**"
        ),
    ]
    if qualified:
        lines.append("### Highest-Ranked Setups")
        ranked = sorted(qualified, key=lambda candidate: candidate.get("score", 0), reverse=True)
        lines.extend(candidate_brief(candidate) for candidate in ranked[:8])
        if len(ranked) > 8:
            lines.append(f"…and **{len(ranked) - 8}** additional qualified setup(s).")
    else:
        lines.append("No setup passed every filter on this run.")
    lines.append(f"Scanned **{timestamp.strftime('%m/%d/%y %-I:%M %p CT')}**")
    return "\n".join(lines)[:2000]

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
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    expirations = stats.get("expirations") or []
    expiration_text = ", ".join(
        f"{item['bucket']} {format_expiration(item['expiration'])}"
        for item in expirations
    ) or "none available"
    by_strategy = stats.get("candidate_counts") or {}
    strategy_text = " · ".join(
        f"{label} **{count}**" for label, count in by_strategy.items() if count
    ) or "none"
    return "\n".join([
        f"## 📡 Ford Scan · Run #{run_number}",
        f"**{timestamp.strftime('%m/%d/%y %-I:%M %p CT')}** · Trigger **{event_name}** · Spot **${spot_price:.2f}**",
        f"Expirations: **{expiration_text}**",
        (
            f"Contracts received **{stats.get('raw_contracts', 0)}** · "
            f"Inside strike band **{stats.get('band_contracts', 0)}** · "
            f"Calls **{stats.get('calls', 0)}** · Puts **{stats.get('puts', 0)}**"
        ),
        f"Passed filters **{stats.get('qualified_candidates', 0)}** · New eligible **{eligible_count}** · Opened **{selected_count}**",
        f"Qualified mix: {strategy_text}",
        f"Lifecycle: HOLD **{hold_count}** · Closed this run **{closed_count}** · Open total **{open_count}**",
    ])[:2000]


def format_closed_scanner_feed(rows: list[dict[str, str]], timestamp: datetime) -> str:
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    return "\n".join([
        f"## 📡 Ford Scan · Run #{run_number}",
        f"**{timestamp.strftime('%m/%d/%y %-I:%M %p CT')}** · Trigger **{event_name}**",
        "⚫ Market closed. No option-chain scan was performed.",
        f"Maintenance sync completed · Open/HOLD positions **{len(open_rows(rows))}**",
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
    daily_dates = sorted(historical_dates | {today})[-30:]
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
        report_end = today if current_week else monday + timedelta(days=4)
        iso_year, iso_week, _ = monday.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly = format_weekly_report(rows, report_end)
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
                f"Entry ${parse_entry_price(row):.4f} ({fmt_money(entry_contract_value(row))}) · "
                f"Exit {'≈' if result_is_reconstructed(row) else ''}${(exit_price(row) or 0):.4f} "
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
    candidate_expirations: list[tuple[str, str]] = []
    if near_expirations:
        candidate_expirations.append((near_expirations[0], "NEAR"))
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
    }
    candidates: list[dict[str, Any]] = []
    quote_map: dict[str, dict[str, Any]] = {}

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
        if bucket == "NEAR":
            add_candidates("Call spreads", scan_credit_spreads(calls, "call", expiration))
            add_candidates("Put spreads", scan_credit_spreads(puts, "put", expiration))
            add_candidates("Regular calls", scan_single_legs(calls, "call", expiration, "REGULAR"))
            add_candidates("Regular puts", scan_single_legs(puts, "put", expiration, "REGULAR"))
        else:
            add_candidates("Swing calls", scan_single_legs(calls, "call", expiration, "SWING"))
            add_candidates("Swing puts", scan_single_legs(puts, "put", expiration, "SWING"))
    stats["qualified_candidates"] = len(candidates)
    return candidates, quote_map, stats

def report_error(discord: DiscordTracker | None, message: str) -> None:
    safe_message = message
    for secret in (TRADIER_TOKEN, DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL):
        if secret:
            safe_message = safe_message.replace(secret, "[REDACTED]")
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
    try:
        closed_results_backfilled = sync_closed_result_channels(rows, discord, report_state)
    except DiscordError as exc:
        print(f"Discord closed-result backfill failed: {exc}", file=sys.stderr)
    if closed_results_backfilled:
        print(f"Discord result backfill: posted {closed_results_backfilled} closed result(s).")

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

    safe_discord_call(
        "open trade channel sync",
        lambda: sync_all_open_trade_cards(rows, discord, report_state),
    )

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
        selected = eligible[:MAX_NEW_PLAYS_PER_SCAN]

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
                row["current_pl_pct"] = "0.0"
                row["current_pl_dollars"] = "0.0"
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
                f"qualified-scan:{run_number}",
                format_qualified_scan(candidates, eligible, selected, timestamp),
                search_token=f"Qualified Scan · Run #{run_number}",
            ),
        )
        safe_discord_call(
            "scanner feed",
            lambda: discord.upsert_channel_message(
                "scanner_feed",
                report_state,
                f"scanner-run:{run_number}",
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
                search_token=f"Ford Scan · Run #{run_number}",
            ),
        )
        safe_discord_call(
            "workflow log",
            lambda: post_workflow_log(
                discord,
                timestamp=timestamp,
                result=f"OK · {summary}",
            ),
        )

        if not discord.ready and (new_rows or closed_count):
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
