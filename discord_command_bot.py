"""HTTP Discord slash-command and provider-signal gateway.

Run locally and expose only the /interactions endpoint through ngrok.
Discord request signatures are verified before any command is processed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

import requests
from flask import Flask, Response, abort, jsonify, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

import spy_scanner
import dynamic_universe
import local_information_engine as info_engine
import ticker_registry

HOST = os.environ.get("COMMAND_BOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMMAND_BOT_PORT", "8080"))
LOCK_PORT = int(os.environ.get("COMMAND_BOT_LOCK_PORT", "8081"))
PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "").strip()
ALLOWED_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID", "").strip()
OWNER_ONLY_COMMANDS = {
    "reset-trading-data",
    "clear-chat-history",
    "ticker-pause",
    "ticker-resume",
    "ticker-remove",
    "scan-now",
}
TRADINGVIEW_WEBHOOK_SECRET = os.environ.get("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
ROBINHOOD_SCAN_WEBHOOK_SECRET = os.environ.get("ROBINHOOD_SCAN_WEBHOOK_SECRET", "").strip()
ROBINHOOD_SCAN_PRESETS = {
    "HIGH_OPTIONS_VOLUME_IV",
    "DAILY_GAINERS",
    "DAILY_LOSERS",
}

APP = Flask(__name__)
CHART_LOCK = threading.Lock()

LEARNING_ANSWERS = [
    (("call option", "what is a call", "what's a call", "whats a call"),
     "**Call option:** The buyer receives the right, but not the obligation, to buy 100 shares at the strike before expiration. Call buyers generally want the stock to rise. Maximum loss is normally the premium paid, but time decay and volatility can still cause a loss."),
    (("put option", "what is a put", "what's a put", "whats a put"),
     "**Put option:** The buyer receives the right, but not the obligation, to sell 100 shares at the strike before expiration. Put buyers generally want the stock to fall. Maximum loss is normally the premium paid."),
    (("strike price", "what is a strike", "what's a strike"),
     "**Strike price:** The fixed stock price at which an option can be exercised. It helps determine whether the option is in, at, or out of the money."),
    (("premium", "option price", "option cost"),
     "**Premium:** The quoted option price per share. One standard contract represents 100 shares, so a $0.42 premium normally costs $42 per contract, plus fees."),
    (("expiration", "dte", "days to expiration"),
     "**Expiration and DTE:** Expiration is the contract's final date; DTE means days to expiration. Less time usually means faster decay and more expiration, exercise, assignment, and pin-risk urgency."),
    (("in the money", "out of the money", "at the money", "itm", "otm", "atm"),
     "**Moneyness:** A call is in the money above its strike; a put is in the money below its strike. At-the-money is near the stock price. Out-of-the-money options have no intrinsic value."),
    (("breakeven", "break even"),
     "**Expiration breakeven:** For a long call it is strike plus premium; for a long put it is strike minus premium. Before expiration, remaining time and volatility also affect value."),
    (("bid ask", "bid/ask", "spread"),
     "**Bid/ask spread:** The bid is what buyers offer and the ask is what sellers request. A wide gap can mean weak liquidity and more slippage. A limit order controls price better than a market order."),
    (("open interest", "volume"),
     "**Volume and open interest:** Volume is contracts traded today. Open interest is contracts still open. Neither guarantees a good fill, but low values often signal weak liquidity."),
    (("delta",),
     "**Delta:** An estimate of how much an option may change for a $1 stock move, all else equal. It is sometimes used as a rough probability proxy, but it is not a guarantee."),
    (("theta", "time decay"),
     "**Theta:** An estimate of daily option value lost from passing time, all else equal. Decay often accelerates near expiration."),
    (("implied volatility", " iv ", "volatility"),
     "**Implied volatility (IV):** The market's priced expectation of movement. Higher IV usually raises premiums. An IV drop can hurt a long option even when direction is correct."),
    (("credit spread", "call spread", "put spread"),
     "**Credit spread:** A defined-risk position that sells one option and buys another for protection. Maximum loss still exists, and the short leg can face early assignment and expiration risk."),
    (("assignment", "assigned"),
     "**Assignment:** An option seller must fulfill the contract, potentially creating a 100-share position per contract. American-style equity options can be assigned early."),
    (("exercise",),
     "**Exercise:** An option buyer uses the right to buy or sell 100 shares at the strike. Exercise can require substantial capital and differs from selling the option to close."),
    (("limit order", "market order"),
     "**Order types:** A market order prioritizes execution, not price. A limit order controls the worst acceptable price but may not fill."),
    (("support", "resistance"),
     "**Support and resistance:** Areas where price previously found buying or selling pressure. They are context zones, not guaranteed barriers or entry prices."),
    (("rsi",),
     "**RSI:** A 0-100 momentum indicator. High or low readings can show strong or stretched momentum, but do not independently predict a reversal."),
    (("atr", "average true range"),
     "**ATR:** Average True Range estimates recent movement size. It describes volatility, not direction or probability of profit."),
    (("paper trade", "paper trading"),
     "**Paper trading:** Practicing with simulated orders. It tests a process without risking cash, although simulated fills may be better than real fills."),
    (("risk reward", "risk/reward", "position size"),
     "**Risk and sizing:** Define maximum possible loss before entry and consider total exposure. Low dollar risk is not the same as high probability. Never trade money needed for necessities."),
]


def acquire_instance_lock() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        listener.bind((HOST, LOCK_PORT))
        listener.listen(1)
    except OSError as exc:
        listener.close()
        raise RuntimeError("The Discord command service is already running.") from exc
    return listener


def command_user_id(interaction: dict[str, Any]) -> str:
    member = interaction.get("member") or {}
    user = member.get("user") or interaction.get("user") or {}
    return str(user.get("id") or "")


def verify_discord_request() -> None:
    if not PUBLIC_KEY:
        abort(503, "DISCORD_PUBLIC_KEY is not configured")
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    if not signature or not timestamp:
        abort(401, "missing Discord signature")
    try:
        VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
            timestamp.encode("utf-8") + request.get_data(),
            bytes.fromhex(signature),
        )
    except (BadSignatureError, ValueError):
        abort(401, "invalid Discord signature")


def option_value(interaction: dict[str, Any], name: str, default: Any = None) -> Any:
    for option in interaction.get("data", {}).get("options") or []:
        if option.get("name") == name:
            return option.get("value", default)
    return default


def patch_original(
    application_id: str,
    token: str,
    *,
    content: str,
    file_path: Path | None = None,
) -> None:
    url = (
        f"https://discord.com/api/v10/webhooks/{application_id}/{token}"
        "/messages/@original"
    )
    payload = {"content": content[:2000], "allowed_mentions": {"parse": []}}
    if file_path and file_path.exists():
        payload["attachments"] = [{"id": 0, "filename": file_path.name}]
        with file_path.open("rb") as handle:
            response = requests.patch(
                url,
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (file_path.name, handle, "image/png")},
                timeout=30,
            )
    else:
        response = requests.patch(url, json=payload, timeout=20)
    response.raise_for_status()


def command_ticker(value: str | None) -> str:
    active = dynamic_universe.initialize()
    ticker = dynamic_universe.normalize_symbol(
        value or (active[0] if active else "SPY")
    )
    if ticker not in active:
        raise ValueError(f"{ticker} is not active in the scanner universe.")
    return ticker


def interaction_ticker(interaction: dict[str, Any]) -> str:
    """Use the requested ticker or the highest-ranked active universe symbol."""
    explicit = str(option_value(interaction, "ticker", "") or "").strip()
    if explicit:
        return command_ticker(explicit)
    return command_ticker(None)


def live_market_data(ticker: str, days: int = 120) -> tuple[float, list[dict[str, Any]]]:
    quote = spy_scanner.get_quote(ticker)
    spot = spy_scanner.as_float((quote or {}).get("last"))
    history = spy_scanner.get_daily_history(ticker, days=max(60, days))
    if spot is None or not history:
        raise spy_scanner.TradierError(f"{ticker} quote or price history is unavailable")
    return spot, history


def chart_reply(ticker: str, days: int) -> tuple[str, Path]:
    with CHART_LOCK:
        spot, history = live_market_data(ticker, days)
        context = spy_scanner.directional_market_context(history, spot)
        closes = [
            value for day in history[-days:]
            if (value := spy_scanner.as_float(day.get("close"))) is not None
        ]
        chart_path = (
            info_engine.TICKER_CHART_DIR
            / f"{ticker.lower()}-command-chart.png"
        )
        spy_scanner.render_market_chart_png(
            history[-days:],
            spot,
            context,
            min(closes[-20:]) if closes else spot,
            max(closes[-20:]) if closes else spot,
            symbol=ticker,
            output_path=chart_path,
        )
        rsi = context.get("rsi14")
        rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
        content = (
            f"📊 **{ticker} chart · {days} trading days**\n"
            f"{ticker} ${spot:.2f} · {context['regime']} · RSI14 {rsi_text}\n"
            f"{context['reason']}\n"
            "Educational decision support only—not financial advice."
        )
        return content, chart_path


def levels_reply(ticker: str) -> str:
    spot, history = live_market_data(ticker)
    context = spy_scanner.directional_market_context(history, spot)
    closes = [
        value for day in history
        if (value := spy_scanner.as_float(day.get("close"))) is not None
    ]
    support = min(closes[-20:])
    resistance = max(closes[-20:])
    rsi = context.get("rsi14")
    rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
    return (
        f"🧭 **{ticker} levels**\n"
        f"Price: ${spot:.2f}\n"
        f"Regime: {context['regime']}\n"
        f"SMA20: {spy_scanner.fmt_money(context.get('sma20'))}\n"
        f"SMA50: {spy_scanner.fmt_money(context.get('sma50'))}\n"
        f"RSI14: {rsi_text}\n"
        f"20-day support: ${support:.2f}\n"
        f"20-day resistance: ${resistance:.2f}\n"
        "A level is context, not an automatic entry."
    )


def events_reply(ticker: str) -> str:
    items = info_engine.fetch_ticker_news(ticker)
    lines = [
        f"**{ticker} news and events**",
        f"[SEC company search](https://www.sec.gov/edgar/search/#/q={ticker})",
    ]
    lines.extend(
        f"• [{item['title']}]({item['url']})" for item in items[:8]
    )
    lines.append("Verify the original publisher before acting on a headline.")
    return "\n".join(lines)


def why_reply(ticker: str, trade_id: str) -> str:
    trade_id = trade_id.strip().upper()
    row = next(
        (
            item for item in spy_scanner.read_log()
            if item.get("trade_id", "").upper() == trade_id
            and str(item.get("ticker") or "F").upper() == ticker
        ),
        None,
    )
    if not row:
        return f"❌ No tracked {ticker} trade matched `{trade_id}`."
    reason = row.get("setup_reason") or (
        "The original detailed rationale was not recorded for this legacy/imported trade. "
        "The bot will not invent an after-the-fact justification."
    )
    result = row.get("outcome") or "UNKNOWN"
    result_detail = ""
    if result != "OPEN":
        result_detail = (
            f"\nResult: **{result}** · "
            f"{spy_scanner.fmt_pct(spy_scanner.as_float(row.get('pct_gain_loss')))}"
        )
    return (
        f"🔎 **Why {trade_id}?**\n"
        f"Structure: {row.get('play_type')} {row.get('call_or_put')} "
        f"{row.get('strike')} · expires {row.get('expiration')}\n"
        f"Entry: {spy_scanner.fmt_money(spy_scanner.as_float(row.get('entry_price')))}\n"
        f"Recorded regime: {row.get('market_regime') or 'Unavailable'}\n"
        f"Trade thesis: {row.get('thesis') or reason}\n"
        f"Entry confirmation: {row.get('entry_confirmation') or reason}\n"
        f"Invalidation: {row.get('invalidation') or 'Unavailable'}\n"
        f"Risk plan: {row.get('risk_plan') or 'Unavailable'}\n"
        f"Learning application: {row.get('learning_plan') or 'Unavailable'}\n"
        f"Evidence limits: {row.get('evidence_limitations') or 'Unavailable'}"
        f"{result_detail}\n"
        "Educational review only—not financial advice."
    )


def value_text(value: Any, *, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    number = spy_scanner.as_float(value)
    if number is None:
        return "Unavailable"
    return f"{prefix}{number:.{digits}f}{suffix}"


def help_reply() -> str:
    return "\n".join([
        "🧭 **Tradysquids dynamic ticker command guide**",
        "`/quote ticker:` — price, daily change, volume, bid/ask and timestamp",
        "`/trend` or `/levels` — trend regime, indicators, support and resistance",
        "`/chart ticker:` — generate and upload a ticker chart",
        "`/chain ticker: side:` — rank liquid calls or puts",
        "`/setup` and `/watchlist` — show qualified direction and monitored conditions",
        "`/option symbol:` — inspect one option contract",
        "`/risk premium: contracts:` — calculate premium at risk and break-even examples",
        "`/events ticker:` or `/filings ticker:` — ticker news and filings",
        "`/performance` — tracked trade results and open-position count",
        "`/why trade_id:` — show the recorded rationale for a tracked trade",
        "`/status`, `/dataage`, `/lastscan`, `/schedule` — system reliability",
        "`/scan-now scope:` — owner-only manual discovery, options, intelligence, positions, health, or everything",
        "`/explain topic:` — plain-language options education",
        "`/ticker-add ticker:` — add a verified optionable symbol to the shared universe",
        "`/ticker-pause`, `/ticker-resume`, `/ticker-remove` — owner-only universe controls",
        "`/ticker-list` and `/ticker-status` — integrated strategy status",
        "",
        "Select a command after typing `/`, complete its fields, then press Send.",
        "Educational information only—not professional financial advice.",
    ])


def require_ticker_admin(interaction: dict[str, Any]) -> None:
    if not ALLOWED_USER_ID:
        raise PermissionError(
            "Ticker editing is locked until DISCORD_ALLOWED_USER_ID is configured."
        )
    if command_user_id(interaction) != ALLOWED_USER_ID:
        raise PermissionError(
            "Only the configured server owner can change TradeBot state."
        )


def filters_reply() -> str:
    config = dynamic_universe.scanner_config()
    traders = config.get("trade_types_enabled") or {}
    status_1m = "on" if traders.get("spy_0dte_1m", False) else "off"
    status_5m = "on" if traders.get("spy_0dte_5m", False) else "off"

    return "\n".join([
        "🎛️ **Active scanner controls**",
        "",
        "**SPY 0DTE** - the only strategy family, split into two",
        f"independently-tracked live strategies that trade fully",
        f"independently of each other (both can hold a position at once):",
        f"• **1-minute** opening-range read ({status_1m})",
        f"• **5-minute** opening-range read ({status_5m})",
        f"Opening range window: **{spy_scanner.SPY_0DTE_OPENING_RANGE_MINUTES}min**",
        f"Delta range: **{spy_scanner.SPY_0DTE_DELTA_MIN:.2f}–{spy_scanner.SPY_0DTE_DELTA_MAX:.2f}**",
        f"Stop / target: **-{spy_scanner.SPY_0DTE_STOP_PCT * 100:.0f}% / +{spy_scanner.SPY_0DTE_TARGET_PCT * 100:.0f}%**",
        f"Floor lock: triggers at **+{spy_scanner.SPY_0DTE_FLOOR_TRIGGER_PCT:.0f}%**, raises stop to **{spy_scanner.SPY_0DTE_FLOOR_PCT:.0f}%**",
        f"Max contract ask / position risk: **${spy_scanner.SPY_0DTE_MAX_CONTRACT_ASK:.2f} / ${spy_scanner.SPY_0DTE_MAX_RISK_PER_TRADE:.0f}**",
        "",
        "**Shared liquidity floor**",
        f"Minimum OI/volume: **{spy_scanner.MIN_OPEN_INTEREST} / {spy_scanner.MIN_OPTION_VOLUME}**",
        f"Maximum bid/ask width: **{spy_scanner.MAX_BID_ASK_PCT * 100:.0f}%**",
        "",
        "Paper trading only. Filters never place brokerage orders.",
    ])


def reset_trading_data_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    confirm = str(option_value(interaction, "confirm", "")).strip()
    archive = bool(option_value(interaction, "archive", False))
    if confirm != "RESET":
        raise ValueError('Type "RESET" exactly (all caps) in the confirm field to proceed.')
    tracker = spy_scanner.initialize_discord()
    result = spy_scanner.reset_all_trade_data(tracker, archive=archive)
    lines = [
        "✅ **Trading data reset complete**",
        f"Cleared **{result['cleared_trades']}** tracked trade(s).",
        f"Deleted **{result['deleted_threads']}** trade-journal thread(s) - gone, not just archived.",
        f"Cleared **{result['cleared_cards']}** per-trade card(s) - held-positions, new-positions, and individual win/loss/scratch results - and zeroed out every summary dashboard immediately.",
    ]
    if archive and result["backup_path"]:
        lines.append(f"Backup saved locally: `{result['backup_path']}`")
    elif archive:
        lines.append("No backup file needed - there was nothing to save.")
    else:
        lines.append("No backup was saved, as requested.")
    lines.append(
        "Held positions, wins, losses, and performance dashboards will show empty "
        "on their next refresh - they render from the live log, not a separate store."
    )
    return "\n".join(lines)


def clear_chat_history_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    confirm = str(option_value(interaction, "confirm", "")).strip()
    if confirm != "CLEAR":
        raise ValueError('Type "CLEAR" exactly (all caps) in the confirm field to proceed.')
    tracker = spy_scanner.initialize_discord()
    removed = tracker.wipe_channel_messages("general_chat", preserve_pinned=True)
    return (
        "✅ **Chat history cleared**\n"
        f"Deleted **{removed}** bot-authored message(s) from #general-chat.\n"
        "Pinned messages were left untouched. Messages a real person posted "
        "were never touched either way - this only ever removes command "
        "replies and other bot-authored messages."
    )


def publish_ticker_configuration() -> str:
    """Legacy compatibility: configuration changes stay local until reviewed."""
    return "Saved locally; no GitHub commit, workflow, or push was triggered."


def set_universe_symbol(symbol: str, active: bool) -> None:
    symbol = dynamic_universe.normalize_symbol(symbol)
    payload = dynamic_universe.universe_config()
    seeds = {str(item).upper() for item in payload.get("seed_symbols") or []}
    excluded = {str(item).upper() for item in payload.get("exclude_symbols") or []}
    seeds.add(symbol)
    if active:
        excluded.discard(symbol)
    else:
        excluded.add(symbol)
    payload["seed_symbols"] = sorted(seeds)
    payload["exclude_symbols"] = sorted(excluded)
    dynamic_universe.CONFIG_PATH.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def universe_add_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = dynamic_universe.normalize_symbol(str(option_value(interaction, "ticker", "")))
    quote = spy_scanner.get_quote(ticker) or {}
    price = spy_scanner.as_float(quote.get("last"))
    if price is None or not spy_scanner.get_expirations(ticker):
        raise ValueError(f"Tradier could not verify optionable ticker {ticker}.")
    set_universe_symbol(ticker, True)
    dynamic_universe.upsert_candidates([
        dynamic_universe.Candidate(
            ticker, "owner", 200, price, options_available=True,
            reason="owner-added universe symbol",
        )
    ])
    return (
        f"✅ **{ticker} added to the shared scanner universe** at ${price:.2f}.\n"
        "It will enter the rotating scan pool. No channel, GitHub run, or trade was created."
    )


def universe_pause_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = dynamic_universe.normalize_symbol(str(option_value(interaction, "ticker", "")))
    set_universe_symbol(ticker, False)
    return (
        f"⏸️ **{ticker} removed from new scans.** Existing positions remain tracked."
    )


def universe_resume_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = dynamic_universe.normalize_symbol(str(option_value(interaction, "ticker", "")))
    set_universe_symbol(ticker, True)
    return f"▶️ **{ticker} restored to the rotating scanner universe.**"


def universe_list_reply() -> str:
    active = dynamic_universe.initialize()
    excluded = dynamic_universe.universe_config().get("exclude_symbols") or []
    return "\n".join([
        "📚 **Dynamic scanner universe**",
        f"**Active ({len(active)}):** {', '.join(active) if active else 'None'}",
        f"**Excluded:** {', '.join(excluded) if excluded else 'None'}",
        "Open positions remain tracked even after a ticker is excluded.",
    ])


def universe_status_reply(ticker: str) -> str:
    symbol = dynamic_universe.normalize_symbol(ticker)
    active = symbol in dynamic_universe.initialize()
    return (
        f"🧩 **{symbol}** · **{'ACTIVE' if active else 'NOT ACTIVE'}**\n"
        "Shared filters, lifecycle channels, and performance tracking apply."
    )


def ticker_add_reply(interaction: dict[str, Any]) -> str:
    ticker = ticker_registry.normalize_ticker(
        str(option_value(interaction, "ticker", ""))
    )
    quote = spy_scanner.get_quote(ticker) or {}
    price = spy_scanner.as_float(quote.get("last"))
    if price is None:
        raise ValueError(f"Tradier could not verify stock ticker {ticker}.")
    expirations = spy_scanner.get_expirations(ticker)
    if not expirations:
        raise ValueError(f"{ticker} does not currently have a usable options chain.")
    dynamic_universe.upsert_candidates([
        dynamic_universe.Candidate(
            ticker,
            "discord_member",
            score=25,
            last_price=price,
            options_available=True,
            reason=f"Added through Discord by user {command_user_id(interaction)}",
        )
    ])
    ticker_registry.save(
        ticker,
        status="ACTIVE",
        note="Added to the shared scanner universe through Discord",
    )
    sync_status = publish_ticker_configuration()
    return "\n".join([
        f"✅ **{ticker} added to the shared scanner universe**",
        f"Verified price: **${price:.2f}** · listed expirations: **{len(expirations)}**",
        "No ticker category or ticker-specific channels were created.",
        "Scheduled research, charts, news, and eligible options scans are enabled.",
        "Results use the shared scanner, intelligence, lifecycle, and performance channels.",
        sync_status,
    ])


def ticker_pause_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = str(option_value(interaction, "ticker", ""))
    duration = str(option_value(interaction, "duration", "today"))
    item = ticker_registry.pause(ticker, today_only=duration == "today")
    sync_status = publish_ticker_configuration()
    resume = (
        f" It will resume automatically on **{item['resume_on']}**."
        if item.get("resume_on") else " Use `/ticker-resume` to enable it again."
    )
    return (
        f"⏸️ **{item['ticker']} paused.** No new positions will be generated."
        f"{resume} Existing positions continue to be tracked. {sync_status}"
    )


def ticker_resume_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = str(option_value(interaction, "ticker", ""))
    item = ticker_registry.resume(ticker)
    dynamic_universe.upsert_candidates([
        dynamic_universe.Candidate(
            item["ticker"], "owner_resume", score=25, reason="Restored by owner"
        )
    ])
    sync_status = publish_ticker_configuration()
    return (
        f"▶️ **{item['ticker']} resumed.** Scheduled research and eligible "
        f"trade generation are active. {sync_status}"
    )


def ticker_remove_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = str(option_value(interaction, "ticker", ""))
    item = ticker_registry.archive(ticker)
    set_universe_symbol(item["ticker"], False)
    sync_status = publish_ticker_configuration()
    return "\n".join([
        f"📦 **{item['ticker']} archived.**",
        "No new positions will be generated.",
        "Trade history, performance, and filters were preserved.",
        "Any existing position will continue through the shared lifecycle until closed.",
        "Use `/ticker-resume` to restore it.",
        sync_status,
    ])


def ticker_list_reply() -> str:
    groups: dict[str, list[str]] = {"ACTIVE": [], "PAUSED": [], "ARCHIVED": []}
    for item in ticker_registry.all_tickers():
        groups.setdefault(str(item["status"]), []).append(str(item["ticker"]))
    lines = ["📚 **Integrated ticker strategies**"]
    for status in ("ACTIVE", "PAUSED", "ARCHIVED"):
        values = groups.get(status) or []
        lines.append(f"**{status.title()}:** {', '.join(values) if values else 'None'}")
    lines.append(
        "SPY is protected. Pausing or archiving never stops existing-position tracking."
    )
    return "\n".join(lines)


def ticker_status_reply(ticker: str) -> str:
    item = ticker_registry.get(ticker)
    if not item:
        return f"❌ `{ticker.upper()}` is not integrated."
    return "\n".join([
        f"🧩 **{item['ticker']} ticker strategy**",
        f"Status: **{item['status']}**",
        f"Resume date: **{item.get('resume_on') or 'manual / not applicable'}**",
        "Discord routing: **shared universe channels**",
        f"Last registry update: {item['updated_at']}",
        f"Note: {item.get('note') or 'None'}",
    ])


def quote_reply(ticker: str) -> str:
    snapshot = info_engine.market_snapshot(ticker)
    return "\n".join([
        f"💵 **{ticker} quote**",
        (
            f"{ticker} **{value_text(snapshot['price'], prefix='$')}** · "
            f"{value_text(snapshot.get('change_pct'), suffix='%')}"
        ),
        (
            f"Bid {value_text(snapshot.get('bid'), prefix='$')} · "
            f"Ask {value_text(snapshot.get('ask'), prefix='$')} · "
            f"Spread {value_text((snapshot.get('spread_pct') or 0) * 100, suffix='%')}"
        ),
        (
            f"Volume {int(snapshot.get('volume') or 0):,} · "
            f"Relative volume {value_text(snapshot.get('relative_volume'), suffix='x')}"
        ),
        f"Day range {value_text(snapshot.get('day_low'), prefix='$')}–{value_text(snapshot.get('day_high'), prefix='$')}",
        f"Data timestamp: {snapshot['observed_at']}",
    ])


def trend_reply(ticker: str) -> str:
    snapshot = info_engine.market_snapshot(ticker)
    return "\n".join([
        f"📐 **{ticker} technical dashboard**",
        f"Regime: **{snapshot['regime']}** · Price {value_text(snapshot['price'], prefix='$')}",
        (
            f"SMA20 {value_text(snapshot.get('sma20'), prefix='$')} · "
            f"SMA50 {value_text(snapshot.get('sma50'), prefix='$')} · "
            f"SMA200 {value_text(snapshot.get('sma200'), prefix='$')}"
        ),
        (
            f"RSI14 {value_text(snapshot.get('rsi14'), digits=1)} · "
            f"MACD {value_text(snapshot.get('macd'), digits=3)} · "
            f"ATR14 {value_text(snapshot.get('atr14'), prefix='$')}"
        ),
        (
            f"Bollinger range {value_text(snapshot.get('bollinger_lower'), prefix='$')}–"
            f"{value_text(snapshot.get('bollinger_upper'), prefix='$')}"
        ),
        (
            f"20-day support {value_text(snapshot.get('support20'), prefix='$')} · "
            f"resistance {value_text(snapshot.get('resistance20'), prefix='$')}"
        ),
        f"Read: {snapshot.get('reason') or 'No controlled setup.'}",
        "Indicators describe conditions; they do not guarantee direction.",
    ])


def chain_reply(ticker: str, side: str) -> str:
    side = side.lower()
    if side not in {"call", "put"}:
        side = "call"
    ranked = info_engine.ranked_option_chain(side=side, limit=8, symbol=ticker)
    lines = [f"🔗 **{ticker} {side} liquidity ranking**"]
    if not ranked:
        return "\n".join(lines + ["No contracts were available for the configured DTE range."])
    for item in ranked:
        marker = "✅" if item["liquidity_pass"] else "⚠️"
        lines.append(
            f"{marker} `{item['symbol']}` · strike ${item['strike']:g} · "
            f"mid {value_text(item['mid'], prefix='$')} · "
            f"Δ {value_text(item['delta'])} · OI {item['open_interest']:,} · "
            f"vol {item['volume']:,} · spread "
            f"{value_text((item['width_pct'] or 0) * 100, suffix='%')} · "
            f"score {item['quality_score']:.0f}"
        )
    lines.append("✅ meets configured liquidity rules; ⚠️ is informational only.")
    return "\n".join(lines)


def setup_reply(ticker: str) -> str:
    snapshot = info_engine.market_snapshot(ticker)
    regime = str(snapshot.get("regime") or "NO TRADE")
    if regime == "NO TRADE":
        return "\n".join([
            f"🚦 **{ticker} setup check**",
            "**Current state: NO TRADE**",
            f"Reason: {snapshot.get('reason') or '; '.join(snapshot.get('failures') or [])}",
            (
                f"Price {value_text(snapshot['price'], prefix='$')} · "
                f"RSI14 {value_text(snapshot.get('rsi14'), digits=1)} · "
                f"support {value_text(snapshot.get('support20'), prefix='$')} · "
                f"resistance {value_text(snapshot.get('resistance20'), prefix='$')}"
            ),
            "The bot will not force an options idea when the configured regime gate fails.",
        ])
    side = "call" if "BULLISH" in regime else "put"
    ranked = info_engine.ranked_option_chain(side=side, limit=3, symbol=ticker)
    lines = [
        f"🚦 **{ticker} setup check**",
        f"Qualified direction: **{regime}**",
        f"Reason: {snapshot.get('reason')}",
        f"Highest-ranked liquid {side}s for research:",
    ]
    for item in ranked:
        lines.append(
            f"• `{item['symbol']}` · ${item['strike']:g} · "
            f"Δ {value_text(item['delta'])} · spread "
            f"{value_text((item['width_pct'] or 0) * 100, suffix='%')}"
        )
    lines.append("Research shortlist only—not an instruction to enter a trade.")
    return "\n".join(lines)


def watchlist_reply(ticker: str) -> str:
    snapshot = info_engine.market_snapshot(ticker)
    return "\n".join([
        f"👀 **{ticker} reactive watchlist**",
        f"Current price: {value_text(snapshot['price'], prefix='$')} · {snapshot['regime']}",
        f"Upside confirmation: sustained trade above {value_text(snapshot.get('resistance20'), prefix='$')}",
        f"Downside warning: sustained trade below {value_text(snapshot.get('support20'), prefix='$')}",
        f"Momentum: RSI14 {value_text(snapshot.get('rsi14'), digits=1)}",
        f"Unusual-volume trigger: 1.75x · current {value_text(snapshot.get('relative_volume'), suffix='x')}",
        "Alerts require material change and are deduplicated to limit noise.",
    ])


def option_reply(ticker: str, symbol: str) -> str:
    item = info_engine.contract_snapshot(symbol)
    if not item:
        return f"❌ Tradier did not return option contract `{symbol.strip().upper()}`."
    underlying = str(item.get("underlying") or "").upper()
    if underlying and underlying != ticker:
        return (
            f"`{symbol.strip().upper()}` belongs to {underlying}, not {ticker}. "
            f"Use the {underlying} desk or explicitly select ticker:{underlying}."
        )
    return "\n".join([
        f"🔬 **Option inspection · `{item['symbol']}`**",
        (
            f"Bid {value_text(item['bid'], prefix='$')} · "
            f"Ask {value_text(item['ask'], prefix='$')} · "
            f"Mid {value_text(item['mid'], prefix='$')}"
        ),
        (
            f"Spread {value_text((item['width_pct'] or 0) * 100, suffix='%')} · "
            f"OI {item['open_interest']:,} · volume {item['volume']:,}"
        ),
        (
            f"Delta {value_text(item['delta'])} · theta {value_text(item['theta'], digits=3)} · "
            f"IV {value_text((item['iv'] or 0) * 100, suffix='%')}"
        ),
        (
            f"Intrinsic {value_text(item['intrinsic'], prefix='$')} · "
            f"extrinsic {value_text(item['extrinsic'], prefix='$')}"
        ),
        f"Configured liquidity test: **{'PASS' if item['liquidity_pass'] else 'FAIL'}**",
        "Use executable bid/ask prices; a midpoint is not a guaranteed fill.",
    ])


def risk_reply(ticker: str, premium: float, contracts: int, side: str) -> str:
    premium = max(0.0, float(premium))
    contracts = max(1, min(int(contracts), 100))
    capital = premium * 100 * contracts
    target_value = premium * (1 + spy_scanner.SPY_0DTE_TARGET_PCT)
    stop_value = premium * (1 - spy_scanner.SPY_0DTE_STOP_PCT)
    target_dollars = (target_value - premium) * 100 * contracts
    stop_dollars = (stop_value - premium) * 100 * contracts
    return "\n".join([
        f"🛡️ **{ticker} long-option risk calculator**",
        f"Example: {contracts} contract(s) at ${premium:.2f} · {side.lower()}",
        f"Premium committed / maximum long-option loss: **${capital:,.0f}**",
        (
            f"Configured +{spy_scanner.SPY_0DTE_TARGET_PCT * 100:.0f}% target: "
            f"${target_value:.2f} · approximately **+${target_dollars:,.0f}**"
        ),
        (
            f"Configured -{spy_scanner.SPY_0DTE_STOP_PCT * 100:.0f}% stop reference: "
            f"${stop_value:.2f} · approximately **${stop_dollars:,.0f}**"
        ),
        (
            "Underlying break-even at expiration requires a strike; use `/option` for "
            "contract details. Stops can gap and fills are not guaranteed."
        ),
        "Calculator only—not individualized financial advice.",
    ])


def performance_reply(ticker: str) -> str:
    snapshot = info_engine.performance_snapshot(ticker)
    metrics = snapshot["metrics"]
    win_rate = spy_scanner.as_float(metrics.get("win_rate"), 0.0) or 0.0
    return "\n".join([
        f"📊 **Tracked {ticker} performance**",
        (
            f"Tracked {snapshot['tracked']} · open {snapshot['open']} · "
            f"closed {snapshot['closed']}"
        ),
        (
            f"Wins {int(metrics.get('wins', 0))} · losses {int(metrics.get('losses', 0))} · "
            f"scratches {int(metrics.get('scratches', 0))} · win rate {win_rate:.1f}%"
        ),
        f"Recorded realized P/L: {spy_scanner.fmt_money(metrics.get('total_pnl'))}",
        "Results are based only on recorded rows and may include incomplete legacy data.",
    ])


def status_reply(ticker: str) -> str:
    market_kind = "market" if ticker == "F" else f"ticker-market:{ticker}"
    latest_market = info_engine.latest_observation(market_kind)
    latest_status = info_engine.latest_observation("status")
    ticker_state = ticker_registry.get(ticker) or {}
    return "\n".join([
        f"🩺 **{ticker} Tradysquids status**",
        f"Ticker strategy: **{ticker_state.get('status', 'UNKNOWN')}**",
        "Command service: **ONLINE**",
        f"Tradier configured: **{'YES' if spy_scanner.TRADIER_TOKEN else 'NO'}**",
        (
            "Scheduled Discord posting: **"
            + (
                "ON"
                if spy_scanner.DISCORD_BOT_TOKEN or spy_scanner.DISCORD_WEBHOOK_URL
                else "WAITING FOR LOCAL BOT TOKEN OR WEBHOOK"
            )
            + "**"
        ),
        f"News-feed identification: **{'ON' if spy_scanner.SEC_USER_AGENT else 'WAITING FOR SEC_USER_AGENT'}**",
        (
            "Latest local market observation: **"
            + info_engine.data_age_text(
                latest_market["observed_at"] if latest_market else None
            )
            + " ago**"
        ),
        f"Local scheduler state: **{'RECORDED' if latest_status else 'NOT YET RECORDED'}**",
    ])


def schedule_reply(ticker: str) -> str:
    return "\n".join([
        f"⏰ **{ticker} local information schedule**",
        f"Market and technical snapshot: every {info_engine.MARKET_REFRESH_MINUTES} minutes",
        f"{ticker} news/event check: every {info_engine.FILINGS_REFRESH_MINUTES} minutes",
        "Integrated ticker dashboards/options: every 15 minutes; ticker news: every 30 minutes",
        f"Health snapshot: every {info_engine.STATUS_REFRESH_MINUTES} minutes",
        "Material alerts: regime changes, tracked-level crosses, unusual relative volume and new filings",
        "Duplicate/unchanged alerts are suppressed.",
        "These jobs run on the laptop and do not consume GitHub Actions minutes.",
    ])


def dataage_reply(ticker: str) -> str:
    rows = []
    kinds = (f"ticker-market:{ticker}", f"ticker-news:{ticker}")
    for kind in kinds:
        item = info_engine.latest_observation(kind)
        label = kind.split(":")[0].replace("ticker-", "").title()
        rows.append(
            f"{label}: {info_engine.data_age_text(item['observed_at'] if item else None)} ago"
        )
    return f"🕒 **{ticker} local data freshness**\n" + "\n".join(rows)


def lastscan_reply(ticker: str) -> str:
    connection = info_engine.connect_db()
    try:
        rows = connection.execute(
            """
            SELECT job_name, finished_at, status, detail
            FROM job_runs
            WHERE status != 'RUNNING'
            ORDER BY id DESC
            LIMIT 30
            """
        ).fetchall()
    finally:
        connection.close()
    rows = [
        row for row in rows
        if ticker in str(row["detail"]).upper()
    ][:6]
    if not rows:
        return f"No recent {ticker} scheduled jobs have completed yet."
    lines = [f"🧾 **Recent {ticker} local jobs**"]
    for row in rows:
        lines.append(
            f"**{row['job_name']}** · {row['status']} · {row['finished_at']} · "
            f"{str(row['detail'])[:180]}"
        )
    return "\n".join(lines)


EXPLANATIONS = {
    "delta": "Delta estimates how much an option may move for a $1 underlying move and is not a fixed probability.",
    "theta": "Theta estimates daily time-value decay, with decay generally accelerating near expiration.",
    "iv": "Implied volatility reflects option-market expectations embedded in premium; high IV makes options more expensive.",
    "spread": "The bid/ask spread is a trading cost and liquidity signal. Wide spreads make displayed midpoint prices less reliable.",
    "open-interest": "Open interest is the number of outstanding contracts. It helps assess liquidity but does not predict direction.",
    "dte": "DTE means days to expiration. More time usually costs more but reduces near-term time-decay pressure.",
    "rsi": "RSI measures recent momentum. Overbought does not automatically mean sell, and oversold does not automatically mean buy.",
    "atr": "ATR measures average price range and helps describe volatility; it does not predict direction.",
}


def explain_reply(topic: str) -> str:
    normalized = topic.strip().lower().replace("_", "-").replace(" ", "-")
    explanation = EXPLANATIONS.get(normalized)
    if not explanation:
        return (
            "Available topics: `" + "`, `".join(EXPLANATIONS) + "`. "
            "Use `/explain topic:` followed by one topic."
        )
    return f"📚 **{topic.strip().title()}**\n{explanation}\nEducational explanation only."


def ask_reply(question: str) -> str:
    normalized = " ".join(question.lower().replace("?", " ").split())
    padded = f" {normalized} "
    for phrases, answer in LEARNING_ANSWERS:
        if any(phrase in padded or phrase in normalized for phrase in phrases):
            return (
                f"**Question:** {question.strip()}\n\n{answer}\n\n"
                "Educational information only. Use `/help` for live ticker "
                "commands, or ask in #general-chat if this did not cover what "
                "you meant."
            )
    return (
        f"**Question:** {question.strip()}\n\n"
        "I do not have a reliable curated answer for that yet. Try asking about "
        "calls, puts, strikes, premiums, expiration, moneyness, breakeven, "
        "bid/ask spreads, liquidity, Greeks, credit spreads, assignment, order "
        "types, support/resistance, RSI, ATR, paper trading, or risk sizing. "
        "For live ticker information use `/quote`, `/levels`, `/chart`, "
        "`/chain`, or `/events`. You can also ask in #general-chat.\n\n"
        "I will not invent an answer or provide personalized financial advice."
    )


def process_command(interaction: dict[str, Any]) -> None:
    application_id = str(interaction.get("application_id") or "")
    token = str(interaction.get("token") or "")
    name = str(interaction.get("data", {}).get("name") or "")
    try:
        if name in OWNER_ONLY_COMMANDS:
            require_ticker_admin(interaction)
        if name == "scan-now":
            scope = str(option_value(interaction, "scope", "all"))
            result = info_engine.run_manual_scan(scope)
            patch_original(
                application_id,
                token,
                content=(
                    "✅ **Manual local run finished**\n"
                    f"Scope: **{scope}**\n{result}\n"
                    "Results were routed to their normal Discord channels. "
                    "Options entries are created only while the market is open."
                )[:1900],
            )
        elif name == "filters":
            patch_original(application_id, token, content=filters_reply())
        elif name == "reset-trading-data":
            patch_original(
                application_id, token, content=reset_trading_data_reply(interaction)
            )
        elif name == "clear-chat-history":
            patch_original(
                application_id, token, content=clear_chat_history_reply(interaction)
            )
        elif name == "ticker-add":
            patch_original(application_id, token, content=universe_add_reply(interaction))
        elif name == "ticker-pause":
            patch_original(application_id, token, content=universe_pause_reply(interaction))
        elif name == "ticker-resume":
            patch_original(application_id, token, content=universe_resume_reply(interaction))
        elif name == "ticker-remove":
            patch_original(application_id, token, content=universe_pause_reply(interaction))
        elif name == "ticker-list":
            patch_original(application_id, token, content=universe_list_reply())
        elif name == "ticker-status":
            patch_original(
                application_id,
                token,
                content=universe_status_reply(str(option_value(interaction, "ticker", ""))),
            )
        elif name == "chart":
            days = int(option_value(interaction, "days", 90))
            ticker = interaction_ticker(interaction)
            content, chart_path = chart_reply(ticker, days)
            patch_original(application_id, token, content=content, file_path=chart_path)
        elif name == "levels":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=levels_reply(ticker))
        elif name == "events":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=events_reply(ticker))
        elif name == "why":
            ticker = interaction_ticker(interaction)
            patch_original(
                application_id,
                token,
                content=why_reply(
                    ticker, str(option_value(interaction, "trade_id", ""))
                ),
            )
        elif name == "help":
            patch_original(application_id, token, content=help_reply())
        elif name == "quote":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=quote_reply(ticker))
        elif name == "trend":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=trend_reply(ticker))
        elif name == "chain":
            ticker = interaction_ticker(interaction)
            patch_original(
                application_id,
                token,
                content=chain_reply(
                    ticker, str(option_value(interaction, "side", "call"))
                ),
            )
        elif name == "setup":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=setup_reply(ticker))
        elif name == "watchlist":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=watchlist_reply(ticker))
        elif name == "option":
            ticker = interaction_ticker(interaction)
            patch_original(
                application_id,
                token,
                content=option_reply(
                    ticker, str(option_value(interaction, "symbol", ""))
                ),
            )
        elif name == "risk":
            ticker = interaction_ticker(interaction)
            patch_original(
                application_id,
                token,
                content=risk_reply(
                    ticker,
                    float(option_value(interaction, "premium", 0)),
                    int(option_value(interaction, "contracts", 1)),
                    str(option_value(interaction, "side", "call")),
                ),
            )
        elif name == "performance":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=performance_reply(ticker))
        elif name == "status":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=status_reply(ticker))
        elif name == "schedule":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=schedule_reply(ticker))
        elif name == "dataage":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=dataage_reply(ticker))
        elif name == "lastscan":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=lastscan_reply(ticker))
        elif name == "calendar":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=events_reply(ticker))
        elif name == "explain":
            patch_original(
                application_id,
                token,
                content=explain_reply(str(option_value(interaction, "topic", ""))),
            )
        elif name == "ask":
            patch_original(
                application_id,
                token,
                content=ask_reply(str(option_value(interaction, "question", ""))),
            )
        else:
            patch_original(application_id, token, content=f"Unknown command: `{name}`")
    except Exception as exc:
        safe_error = f"{type(exc).__name__}: {exc}"[:1200]
        try:
            patch_original(
                application_id,
                token,
                content=f"⚠️ Command failed safely.\n```{safe_error}```",
            )
        except requests.RequestException:
            pass


@APP.get("/health")
def health() -> Response:
    return jsonify({
        "ok": True,
        "service": "Tradysquids local command and signal gateway",
        "tradingview_ready": bool(TRADINGVIEW_WEBHOOK_SECRET),
        "robinhood_scan_ready": bool(ROBINHOOD_SCAN_WEBHOOK_SECRET),
        "paper_trading_only": True,
    })


@APP.post("/tradingview")
def tradingview_webhook() -> Response:
    """Acknowledge TradingView quickly and enqueue the signal for local processing."""
    if not TRADINGVIEW_WEBHOOK_SECRET:
        abort(503, "TRADINGVIEW_WEBHOOK_SECRET is not configured")
    supplied = (
        request.headers.get("X-Tradysquids-Secret", "")
        or request.args.get("secret", "")
    )
    if supplied != TRADINGVIEW_WEBHOOK_SECRET:
        abort(401, "invalid webhook secret")
    if request.content_length and request.content_length > 32_768:
        abort(413, "payload too large")
    payload = request.get_json(force=True)
    ticker = (
        payload.get("ticker")
        or payload.get("symbol")
        or payload.get("syminfo", {}).get("ticker")
        or ""
    )
    symbol = dynamic_universe.normalize_symbol(str(ticker).split(":")[-1])
    event_type = str(payload.get("event") or payload.get("action") or "alert")[:80]
    event_key = str(payload.get("id") or payload.get("event_id") or "")[:200]
    inserted = dynamic_universe.enqueue_event(
        "tradingview",
        event_type,
        symbol,
        payload,
        priority=100,
        event_key=event_key,
    )
    dynamic_universe.upsert_candidates([
        dynamic_universe.Candidate(
            symbol,
            "tradingview",
            score=100,
            reason=f"TradingView {event_type}",
            ttl_minutes=240,
        )
    ])
    return jsonify({"ok": True, "queued": inserted, "symbol": symbol}), 202


@APP.post("/robinhood-scan")
def robinhood_scan_webhook() -> Response:
    """Accept a batch of tickers a Robinhood MCP scan surfaced (run by a
    scheduled Claude routine, since the scan tools only work through an
    active session - not something this always-on local process can call
    itself). Read-only discovery only: import_robinhood_snapshot rejects
    any order/trade/transfer-shaped field structurally, so this can never
    become a trading pathway no matter what a caller sends."""
    if not ROBINHOOD_SCAN_WEBHOOK_SECRET:
        abort(503, "ROBINHOOD_SCAN_WEBHOOK_SECRET is not configured")
    supplied = (
        request.headers.get("X-Tradysquids-Secret", "")
        or request.args.get("secret", "")
    )
    if supplied != ROBINHOOD_SCAN_WEBHOOK_SECRET:
        abort(401, "invalid webhook secret")
    if request.content_length and request.content_length > 32_768:
        abort(413, "payload too large")
    payload = request.get_json(force=True)
    scan = str(payload.get("scan") or "").strip().upper()
    if scan not in ROBINHOOD_SCAN_PRESETS:
        abort(400, f"scan must be one of {sorted(ROBINHOOD_SCAN_PRESETS)}")
    raw_symbols = payload.get("symbols") or []
    if not isinstance(raw_symbols, list):
        abort(400, "symbols must be a list")
    symbols: list[str] = []
    for value in raw_symbols[:100]:
        try:
            symbols.append(dynamic_universe.normalize_symbol(str(value)))
        except ValueError:
            continue
    inserted = dynamic_universe.import_robinhood_snapshot({
        "source": "robinhood_mcp",
        "generated_at": spy_scanner.now_ct().isoformat(),
        "symbols": [
            {
                "symbol": symbol,
                "score": 60,
                "options_available": True,
                "reason": f"Robinhood {scan} scan",
            }
            for symbol in symbols
        ],
    })
    return jsonify({"ok": True, "queued": inserted, "scan": scan, "symbols": symbols}), 202


def handle_message_component(interaction: dict[str, Any]) -> Response:
    custom_id = str((interaction.get("data") or {}).get("custom_id") or "")
    if not custom_id.startswith("archive-trade:"):
        return jsonify({"type": 6})
    trade_id = custom_id.split(":", 1)[1]
    try:
        require_ticker_admin(interaction)
    except PermissionError as exc:
        return jsonify({
            "type": 4,
            "data": {"content": str(exc), "flags": 64},
        })
    result = spy_scanner.archive_trade_for_comparison(trade_id)
    label = {
        "archived": "✅ Archived for comparison",
        "already archived": "✅ Already archived",
    }.get(result, f"⚠️ {result}")
    return jsonify({
        "type": 7,
        "data": {
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 2,
                            "label": label,
                            "custom_id": "archive-trade:done",
                            "disabled": True,
                        }
                    ],
                }
            ]
        },
    })


@APP.post("/interactions")
def interactions() -> Response:
    verify_discord_request()
    interaction = request.get_json(force=True)
    if interaction.get("type") == 1:
        return jsonify({"type": 1})
    if interaction.get("type") == 3:
        return handle_message_component(interaction)
    if interaction.get("type") != 2:
        return jsonify({
            "type": 4,
            "data": {"content": "Unsupported interaction.", "flags": 64},
        })
    if ALLOWED_GUILD_ID and str(interaction.get("guild_id") or "") != ALLOWED_GUILD_ID:
        return jsonify({
            "type": 4,
            "data": {"content": "This command is not enabled in this server.", "flags": 64},
        })
    threading.Thread(target=process_command, args=(interaction,), daemon=True).start()
    return jsonify({"type": 5})


if __name__ == "__main__":
    if not PUBLIC_KEY:
        raise SystemExit("DISCORD_PUBLIC_KEY is required")
    try:
        instance_lock = acquire_instance_lock()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    with instance_lock:
        APP.run(host=HOST, port=PORT, debug=False, threaded=True)
