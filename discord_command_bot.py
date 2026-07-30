"""HTTP Discord slash-command service for the Ford scanner.

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

import ford_scan
import local_information_engine as info_engine
import ticker_registry

HOST = os.environ.get("COMMAND_BOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMMAND_BOT_PORT", "8080"))
LOCK_PORT = int(os.environ.get("COMMAND_BOT_LOCK_PORT", "8081"))
PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "").strip()
ALLOWED_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID", "").strip()

APP = Flask(__name__)
CHART_LOCK = threading.Lock()


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
    ticker = ticker_registry.normalize_ticker(value or "F")
    item = ticker_registry.get(ticker)
    if not item:
        raise ValueError(
            f"{ticker} is not integrated. Use `/ticker-add ticker:{ticker}` first."
        )
    if item.get("status") == "ARCHIVED":
        raise ValueError(
            f"{ticker} is archived. Use `/ticker-resume ticker:{ticker}` first."
        )
    return ticker


def interaction_ticker(interaction: dict[str, Any]) -> str:
    """Use an explicit ticker, then the ticker desk channel, then Ford."""
    explicit = str(option_value(interaction, "ticker", "") or "").strip()
    if explicit:
        return command_ticker(explicit)
    channel_id = str(interaction.get("channel_id") or "")
    if channel_id:
        for item in ticker_registry.all_tickers():
            channels = item.get("channels") or {}
            if channel_id in {str(value) for value in channels.values()}:
                return command_ticker(str(item["ticker"]))
    return command_ticker("F")


def live_market_data(ticker: str, days: int = 120) -> tuple[float, list[dict[str, Any]]]:
    quote = ford_scan.get_quote(ticker)
    spot = ford_scan.as_float((quote or {}).get("last"))
    history = ford_scan.get_daily_history(ticker, days=max(60, days))
    if spot is None or not history:
        raise ford_scan.TradierError(f"{ticker} quote or price history is unavailable")
    return spot, history


def chart_reply(ticker: str, days: int) -> tuple[str, Path]:
    with CHART_LOCK:
        spot, history = live_market_data(ticker, days)
        context = ford_scan.directional_market_context(history, spot)
        closes = [
            value for day in history[-days:]
            if (value := ford_scan.as_float(day.get("close"))) is not None
        ]
        chart_path = (
            info_engine.TICKER_CHART_DIR
            / f"{ticker.lower()}-command-chart.png"
        )
        ford_scan.render_market_chart_png(
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
            f"📊 **Ford chart · {days} trading days**\n"
            f"F ${spot:.2f} · {context['regime']} · RSI14 {rsi_text}\n"
            f"{context['reason']}\n"
            "Educational decision support only—not financial advice."
        )
        return (
            content.replace("Ford", ticker).replace("F $", f"{ticker} $"),
            chart_path,
        )


def levels_reply(ticker: str) -> str:
    spot, history = live_market_data(ticker)
    context = ford_scan.directional_market_context(history, spot)
    closes = [
        value for day in history
        if (value := ford_scan.as_float(day.get("close"))) is not None
    ]
    support = min(closes[-20:])
    resistance = max(closes[-20:])
    rsi = context.get("rsi14")
    rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
    return (
        f"🧭 **{ticker} levels**\n"
        f"Price: ${spot:.2f}\n"
        f"Regime: {context['regime']}\n"
        f"SMA20: {ford_scan.fmt_money(context.get('sma20'))}\n"
        f"SMA50: {ford_scan.fmt_money(context.get('sma50'))}\n"
        f"RSI14: {rsi_text}\n"
        f"20-day support: ${support:.2f}\n"
        f"20-day resistance: ${resistance:.2f}\n"
        "A level is context, not an automatic entry."
    )


def events_reply(ticker: str) -> str:
    if ticker != "F":
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
    filings = ford_scan.fetch_recent_ford_filings()
    lines = [
        "🗓️ **Ford events and filings**",
        f"[Ford investor events]({ford_scan.FORD_IR_EVENTS_URL})",
        "[Ford investor news](https://shareholder.ford.com/news/default.aspx)",
        "[Ford SEC filings](https://www.sec.gov/edgar/browse/?CIK=37996)",
    ]
    if filings:
        lines.append("\n**Recent material filings**")
        for filing in filings[:5]:
            lines.append(
                f"• {filing['date']} · {filing['form']} · [Open]({filing['url']})"
            )
    elif not ford_scan.SEC_USER_AGENT:
        lines.append(
            "\nSEC detail is disabled until SEC_USER_AGENT is configured; "
            "official links remain available."
        )
    return "\n".join(lines)


def why_reply(ticker: str, trade_id: str) -> str:
    trade_id = trade_id.strip().upper()
    row = next(
        (
            item for item in ford_scan.read_log()
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
            f"{ford_scan.fmt_pct(ford_scan.as_float(row.get('pct_gain_loss')))}"
        )
    return (
        f"🔎 **Why {trade_id}?**\n"
        f"Structure: {row.get('play_type')} {row.get('call_or_put')} "
        f"{row.get('strike')} · expires {row.get('expiration')}\n"
        f"Entry: {ford_scan.fmt_money(ford_scan.as_float(row.get('entry_price')))}\n"
        f"Recorded regime: {row.get('market_regime') or 'Unavailable'}\n"
        f"Recorded rationale: {reason}"
        f"{result_detail}\n"
        "Educational review only—not financial advice."
    )


def value_text(value: Any, *, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    number = ford_scan.as_float(value)
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
        "`/explain topic:` — plain-language options education",
        "`/ticker-add`, `/ticker-pause`, `/ticker-resume`, `/ticker-remove` — owner ticker controls",
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
        raise PermissionError("Only the configured server owner can manage tickers.")


def publish_ticker_configuration() -> str:
    """Commit and push only the tracked ticker list for cloud-backup parity."""
    root = Path(__file__).resolve().parent
    add = subprocess.run(
        ["git", "add", "--", "config/tickers.json"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if add.returncode:
        raise RuntimeError("Could not stage the tracked ticker configuration.")
    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", "config/tickers.json"],
        cwd=root,
        timeout=20,
    )
    if changed.returncode == 0:
        return "GitHub ticker configuration already matched."
    if changed.returncode != 1:
        raise RuntimeError("Could not verify the tracked ticker configuration.")
    commit = subprocess.run(
        ["git", "commit", "-m", "Sync active ticker configuration"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if commit.returncode:
        raise RuntimeError("Could not commit the tracked ticker configuration.")
    push = subprocess.run(
        ["git", "push", "origin", "HEAD:main"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if push.returncode:
        raise RuntimeError(
            "Ticker changed locally, but GitHub sync failed. Run the sync again."
        )
    return "GitHub backup ticker configuration synchronized."


def ticker_add_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = ticker_registry.normalize_ticker(
        str(option_value(interaction, "ticker", ""))
    )
    quote = ford_scan.get_quote(ticker) or {}
    price = ford_scan.as_float(quote.get("last"))
    if price is None:
        raise ValueError(f"Tradier could not verify stock ticker {ticker}.")
    expirations = ford_scan.get_expirations(ticker)
    if not expirations:
        raise ValueError(f"{ticker} does not currently have a usable options chain.")
    item = ticker_registry.provision_discord_desk(ticker)
    sync_status = publish_ticker_configuration()
    return "\n".join([
        f"✅ **{ticker} fully integrated**",
        f"Verified price: **${price:.2f}** · listed expirations: **{len(expirations)}**",
        "Created or connected its five-channel information desk.",
        "Status: **ACTIVE** · scheduled research and eligible trade scanning enabled.",
        f"Category ID: `{item.get('category_id')}`",
        "Existing positions remain in the shared lifecycle desk.",
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
    ).replace("Ford", ticker)


def ticker_resume_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = str(option_value(interaction, "ticker", ""))
    ticker_registry.rename_category(ticker, archived=False)
    item = ticker_registry.resume(ticker)
    sync_status = publish_ticker_configuration()
    return (
        f"▶️ **{item['ticker']} resumed.** Scheduled research and eligible "
        f"trade generation are active. {sync_status}"
    )


def ticker_remove_reply(interaction: dict[str, Any]) -> str:
    require_ticker_admin(interaction)
    ticker = str(option_value(interaction, "ticker", ""))
    item = ticker_registry.archive(ticker)
    ticker_registry.rename_category(ticker, archived=True)
    sync_status = publish_ticker_configuration()
    return "\n".join([
        f"📦 **{item['ticker']} archived.**",
        "No new positions will be generated.",
        "Channels, trade history, performance, and filters were preserved.",
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
        "Ford is protected. Pausing or archiving never stops existing-position tracking."
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
        f"Discord desk: **{'connected' if item.get('category_id') else 'not provisioned'}**",
        f"Information channels: **{len(item.get('channels') or {})}/5**",
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
    target_value = premium * (1 + ford_scan.SINGLE_TAKE_PROFIT_PCT)
    stop_value = premium * (1 - ford_scan.SINGLE_STOP_PCT)
    target_dollars = (target_value - premium) * 100 * contracts
    stop_dollars = (stop_value - premium) * 100 * contracts
    return "\n".join([
        f"🛡️ **{ticker} long-option risk calculator**",
        f"Example: {contracts} contract(s) at ${premium:.2f} · {side.lower()}",
        f"Premium committed / maximum long-option loss: **${capital:,.0f}**",
        (
            f"Configured +{ford_scan.SINGLE_TAKE_PROFIT_PCT * 100:.0f}% target: "
            f"${target_value:.2f} · approximately **+${target_dollars:,.0f}**"
        ),
        (
            f"Configured -{ford_scan.SINGLE_STOP_PCT * 100:.0f}% stop reference: "
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
    win_rate = ford_scan.as_float(metrics.get("win_rate"), 0.0) or 0.0
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
        f"Recorded realized P/L: {ford_scan.fmt_money(metrics.get('total_pnl'))}",
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
        f"Tradier configured: **{'YES' if ford_scan.TRADIER_TOKEN else 'NO'}**",
        (
            "Scheduled Discord posting: **"
            + (
                "ON"
                if ford_scan.DISCORD_BOT_TOKEN or ford_scan.DISCORD_WEBHOOK_URL
                else "WAITING FOR LOCAL BOT TOKEN OR WEBHOOK"
            )
            + "**"
        ),
        f"SEC filing detail: **{'ON' if ford_scan.SEC_USER_AGENT else 'WAITING FOR SEC_USER_AGENT'}**",
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
    kinds = (
        ("market", "filings", "status")
        if ticker == "F"
        else (f"ticker-market:{ticker}", f"ticker-news:{ticker}")
    )
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
        or (
            ticker == "F"
            and row["job_name"] in {
                "market-monitor", "options-dashboard", "official-ford-news",
                "filings-monitor",
            }
        )
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


def filings_reply(ticker: str) -> str:
    if ticker != "F":
        return events_reply(ticker)
    filings = ford_scan.fetch_recent_ford_filings()
    if not filings:
        return (
            "No detailed SEC filing feed is available yet. Add a truthful "
            "`SEC_USER_AGENT` locally; official Ford filings remain available at "
            "https://www.sec.gov/edgar/browse/?CIK=37996"
        )
    lines = ["📄 **Recent Ford SEC filings**"]
    for filing in filings[:8]:
        lines.append(
            f"• {filing['date']} · **{filing['form']}** · [Open]({filing['url']})"
        )
    return "\n".join(lines)


def process_command(interaction: dict[str, Any]) -> None:
    application_id = str(interaction.get("application_id") or "")
    token = str(interaction.get("token") or "")
    name = str(interaction.get("data", {}).get("name") or "")
    try:
        if name == "ticker-add":
            patch_original(application_id, token, content=ticker_add_reply(interaction))
        elif name == "ticker-pause":
            patch_original(application_id, token, content=ticker_pause_reply(interaction))
        elif name == "ticker-resume":
            patch_original(application_id, token, content=ticker_resume_reply(interaction))
        elif name == "ticker-remove":
            patch_original(application_id, token, content=ticker_remove_reply(interaction))
        elif name == "ticker-list":
            patch_original(application_id, token, content=ticker_list_reply())
        elif name == "ticker-status":
            patch_original(
                application_id,
                token,
                content=ticker_status_reply(str(option_value(interaction, "ticker", ""))),
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
        elif name == "filings":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=filings_reply(ticker))
        elif name == "calendar":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=events_reply(ticker))
        elif name == "explain":
            patch_original(
                application_id,
                token,
                content=explain_reply(str(option_value(interaction, "topic", ""))),
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
    return jsonify({"ok": True, "service": "Tradysquids Ford command bot"})


@APP.post("/interactions")
def interactions() -> Response:
    verify_discord_request()
    interaction = request.get_json(force=True)
    if interaction.get("type") == 1:
        return jsonify({"type": 1})
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
    if ALLOWED_USER_ID and command_user_id(interaction) != ALLOWED_USER_ID:
        return jsonify({
            "type": 4,
            "data": {"content": "This command is private.", "flags": 64},
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
