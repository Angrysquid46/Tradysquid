"""HTTP Discord slash-command and provider-signal gateway.

Run locally and expose only the /interactions endpoint through ngrok.
Discord request signatures are verified before any command is processed.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any

import requests
from flask import Flask, Response, abort, jsonify, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

import activity_log
import local_information_engine as info_engine
import market_data
import upgrade_batch_44

HOST = os.environ.get("COMMAND_BOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMMAND_BOT_PORT", "8080"))
LOCK_PORT = int(os.environ.get("COMMAND_BOT_LOCK_PORT", "8081"))
PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "").strip()
ALLOWED_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID", "").strip()
OWNER_ONLY_COMMANDS: set[str] = set()
ROOT = Path(__file__).resolve().parent

APP = Flask(__name__)

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
    """This system trades SPY exclusively - defaults to it, and any
    explicit symbol is just a read-only informational lookup (a live
    quote/chart/technical read), never a scan or trade target. There is no
    more "active universe" to validate against - that concept, and the
    Discord commands that grew it, were removed entirely."""
    return (value or "SPY").strip().upper()


def interaction_ticker(interaction: dict[str, Any]) -> str:
    """Use the requested ticker or default to SPY."""
    explicit = str(option_value(interaction, "ticker", "") or "").strip()
    return command_ticker(explicit or None)


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


def value_text(value: Any, *, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    try:
        number = None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        number = None
    if number is None:
        return "Unavailable"
    return f"{prefix}{number:.{digits}f}{suffix}"


def help_reply() -> str:
    return "\n".join([
        "🧭 **Tradysquids dynamic ticker command guide**",
        "`/quote ticker:` — price, daily change, volume, bid/ask and timestamp",
        "`/trend` — trend regime, indicators, support and resistance",
        "`/chain ticker: side:` — rank liquid calls or puts",
        "`/setup` and `/watchlist` — show qualified direction and monitored conditions",
        "`/option symbol:` — inspect one option contract",
        "`/events ticker:` or `/filings ticker:` — ticker news and filings",
        "`/dataage`, `/lastscan`, `/schedule` — system reliability",
        "`/explain topic:` — plain-language options education",
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


def levels_reply(ticker: str) -> str:
    snapshot = info_engine.market_snapshot(ticker)
    return "\n".join([
        f"📏 **{ticker} levels**",
        f"Price {value_text(snapshot['price'], prefix='$')} · Regime: **{snapshot['regime']}**",
        (
            f"20-day support {value_text(snapshot.get('support20'), prefix='$')} · "
            f"resistance {value_text(snapshot.get('resistance20'), prefix='$')}"
        ),
        "Levels are computed from real recorded bars, not predictions.",
    ])


def chart_reply_file(ticker: str) -> tuple[str, Path | None]:
    from datetime import datetime

    bars = market_data.get_intraday_history(ticker)
    timeframe = "5-minute session"
    if len(bars) < 2:
        bars = market_data.get_daily_history(ticker, days=45)[-30:]
        timeframe = "30-session fallback"
    output = Path("docs") / "tickers" / f"{ticker.lower()}-command-chart.png"
    try:
        variant = datetime.now().toordinal() % upgrade_batch_44.CHART_VARIANT_COUNT
        metrics = upgrade_batch_44._render_intraday_chart(ticker, bars, output, variant=variant)
    except ValueError as exc:
        return f"Could not render a chart for {ticker}: {exc}", None
    caption = (
        f"📈 **{ticker} {timeframe}** · {metrics['change_pct']:+.2f}% · "
        f"support ${metrics['support']:.2f} · resistance ${metrics['resistance']:.2f}"
    )
    return caption, output


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
        if name == "events":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=events_reply(ticker))
        elif name == "help":
            patch_original(application_id, token, content=help_reply())
        elif name == "quote":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=quote_reply(ticker))
        elif name == "trend":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=trend_reply(ticker))
        elif name == "levels":
            ticker = interaction_ticker(interaction)
            patch_original(application_id, token, content=levels_reply(ticker))
        elif name == "chart":
            ticker = interaction_ticker(interaction)
            caption, chart_path = chart_reply_file(ticker)
            patch_original(application_id, token, content=caption, file_path=chart_path)
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
        "paper_trading_only": True,
    })


def handle_message_component(interaction: dict[str, Any]) -> Response:
    # The archive-trade button interaction was Phase 3-purged along with the
    # trade log it archived. No component interactions are handled now; this
    # stays as a no-op acknowledgement so an existing Discord message with a
    # stale button (if any survive from before the purge) does not error.
    return jsonify({"type": 6})


@APP.post("/interactions")
def interactions() -> Response:
    # Recorded BEFORE verification and before any work, because the case
    # this exists for left no other trace: on 2026-08-20 twelve positions
    # opened stamped "/force-all-strategies", the owner had not run it, and
    # a scan of all 123 Discord channels found zero interactions that day.
    # A rejected or replayed request must still leave a line here.
    raw = request.get_json(force=True, silent=True) or {}
    data = raw.get("data") or {}
    invoker = (raw.get("member") or {}).get("user") or raw.get("user") or {}
    activity_log.record(
        "discord.interaction",
        interaction_id=raw.get("id"),
        interaction_type=raw.get("type"),
        command=data.get("name"),
        user=invoker.get("username"),
        user_id=invoker.get("id"),
        guild_id=raw.get("guild_id"),
        channel_id=raw.get("channel_id"),
        # A Discord RETRY reuses the interaction id and application id but
        # carries a fresh signature timestamp - which is how a replayed
        # command is told apart from a new one.
        signature_timestamp=request.headers.get("X-Signature-Timestamp"),
        has_signature=bool(request.headers.get("X-Signature-Ed25519")),
        remote_addr=request.headers.get("X-Forwarded-For") or request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    try:
        verify_discord_request()
    except Exception as exc:
        activity_log.record("discord.interaction.rejected",
                            interaction_id=raw.get("id"),
                            reason=type(exc).__name__,
                            detail=str(exc)[:200])
        raise
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
    activity_log.record("discord.command.dispatched",
                        interaction_id=interaction.get("id"),
                        command=(interaction.get("data") or {}).get("name"),
                        user=((interaction.get("member") or {}).get("user")
                              or interaction.get("user") or {}).get("username"))
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
