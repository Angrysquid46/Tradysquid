"""HTTP Discord slash-command service for the Ford scanner.

Run locally and expose only the /interactions endpoint through ngrok.
Discord request signatures are verified before any command is processed.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import requests
from flask import Flask, Response, abort, jsonify, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

import ford_scan
import local_information_engine as info_engine

HOST = os.environ.get("COMMAND_BOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMMAND_BOT_PORT", "8080"))
PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "").strip()
ALLOWED_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID", "").strip()

APP = Flask(__name__)
CHART_LOCK = threading.Lock()


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


def live_market_data(days: int = 120) -> tuple[float, list[dict[str, Any]]]:
    quote = ford_scan.get_quote(ford_scan.TICKER)
    spot = ford_scan.as_float((quote or {}).get("last"))
    history = ford_scan.get_daily_history(ford_scan.TICKER, days=max(60, days))
    if spot is None or not history:
        raise ford_scan.TradierError("Ford quote or price history is unavailable")
    return spot, history


def chart_reply(days: int) -> tuple[str, Path]:
    with CHART_LOCK:
        spot, history = live_market_data(days)
        ford_scan.render_market_chart(history[-days:], spot)
        context = ford_scan.directional_market_context(history, spot)
        rsi = context.get("rsi14")
        rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
        content = (
            f"📊 **Ford chart · {days} trading days**\n"
            f"F ${spot:.2f} · {context['regime']} · RSI14 {rsi_text}\n"
            f"{context['reason']}\n"
            "Educational decision support only—not financial advice."
        )
        return content, ford_scan.CHART_SCREENSHOT_PATH


def levels_reply() -> str:
    spot, history = live_market_data()
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
        "🧭 **Ford levels**\n"
        f"Price: ${spot:.2f}\n"
        f"Regime: {context['regime']}\n"
        f"SMA20: {ford_scan.fmt_money(context.get('sma20'))}\n"
        f"SMA50: {ford_scan.fmt_money(context.get('sma50'))}\n"
        f"RSI14: {rsi_text}\n"
        f"20-day support: ${support:.2f}\n"
        f"20-day resistance: ${resistance:.2f}\n"
        "A level is context, not an automatic entry."
    )


def events_reply() -> str:
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


def why_reply(trade_id: str) -> str:
    trade_id = trade_id.strip().upper()
    row = next(
        (item for item in ford_scan.read_log() if item.get("trade_id", "").upper() == trade_id),
        None,
    )
    if not row:
        return f"❌ No tracked Ford trade matched `{trade_id}`."
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
        "🧭 **Tradysquids Ford command guide**",
        "`/quote` — price, daily change, volume, bid/ask and data timestamp",
        "`/trend` or `/levels` — trend regime, indicators, support and resistance",
        "`/chart` — generate and upload a Ford chart",
        "`/chain side:` — rank liquid Ford calls or puts",
        "`/setup` and `/watchlist` — show qualified direction and monitored conditions",
        "`/option symbol:` — inspect one option contract",
        "`/risk premium: contracts:` — calculate premium at risk and break-even examples",
        "`/events` or `/filings` — official Ford events and SEC filings",
        "`/performance` — tracked trade results and open-position count",
        "`/why trade_id:` — show the recorded rationale for a tracked trade",
        "`/status`, `/dataage`, `/lastscan`, `/schedule` — system reliability",
        "`/explain topic:` — plain-language options education",
        "",
        "Select a command after typing `/`, complete its fields, then press Send.",
        "Educational information only—not professional financial advice.",
    ])


def quote_reply() -> str:
    snapshot = info_engine.market_snapshot()
    return "\n".join([
        "💵 **Ford quote**",
        (
            f"F **{value_text(snapshot['price'], prefix='$')}** · "
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


def trend_reply() -> str:
    snapshot = info_engine.market_snapshot()
    return "\n".join([
        "📐 **Ford technical dashboard**",
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


def chain_reply(side: str) -> str:
    side = side.lower()
    if side not in {"call", "put"}:
        side = "call"
    ranked = info_engine.ranked_option_chain(side=side, limit=8)
    lines = [f"🔗 **Ford {side} liquidity ranking**"]
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


def setup_reply() -> str:
    snapshot = info_engine.market_snapshot()
    regime = str(snapshot.get("regime") or "NO TRADE")
    if regime == "NO TRADE":
        return "\n".join([
            "🚦 **Ford setup check**",
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
    ranked = info_engine.ranked_option_chain(side=side, limit=3)
    lines = [
        "🚦 **Ford setup check**",
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


def watchlist_reply() -> str:
    snapshot = info_engine.market_snapshot()
    return "\n".join([
        "👀 **Ford reactive watchlist**",
        f"Current price: {value_text(snapshot['price'], prefix='$')} · {snapshot['regime']}",
        f"Upside confirmation: sustained trade above {value_text(snapshot.get('resistance20'), prefix='$')}",
        f"Downside warning: sustained trade below {value_text(snapshot.get('support20'), prefix='$')}",
        f"Momentum: RSI14 {value_text(snapshot.get('rsi14'), digits=1)}",
        f"Unusual-volume trigger: 1.75x · current {value_text(snapshot.get('relative_volume'), suffix='x')}",
        "Alerts require material change and are deduplicated to limit noise.",
    ])


def option_reply(symbol: str) -> str:
    item = info_engine.contract_snapshot(symbol)
    if not item:
        return f"❌ Tradier did not return option contract `{symbol.strip().upper()}`."
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


def risk_reply(premium: float, contracts: int, side: str) -> str:
    premium = max(0.0, float(premium))
    contracts = max(1, min(int(contracts), 100))
    capital = premium * 100 * contracts
    target_value = premium * (1 + ford_scan.SINGLE_TAKE_PROFIT_PCT)
    stop_value = premium * (1 - ford_scan.SINGLE_STOP_PCT)
    target_dollars = (target_value - premium) * 100 * contracts
    stop_dollars = (stop_value - premium) * 100 * contracts
    return "\n".join([
        "🛡️ **Long-option risk calculator**",
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


def performance_reply() -> str:
    snapshot = info_engine.performance_snapshot()
    metrics = snapshot["metrics"]
    win_rate = ford_scan.as_float(metrics.get("win_rate"), 0.0) or 0.0
    return "\n".join([
        "📊 **Tracked Ford performance**",
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


def status_reply() -> str:
    latest_market = info_engine.latest_observation("market")
    latest_status = info_engine.latest_observation("status")
    return "\n".join([
        "🩺 **Tradysquids status**",
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


def schedule_reply() -> str:
    return "\n".join([
        "⏰ **Local information schedule**",
        f"Market and technical snapshot: every {info_engine.MARKET_REFRESH_MINUTES} minutes",
        f"Ford SEC filing check: every {info_engine.FILINGS_REFRESH_MINUTES} minutes",
        f"Health snapshot: every {info_engine.STATUS_REFRESH_MINUTES} minutes",
        "Material alerts: regime changes, tracked-level crosses, unusual relative volume and new filings",
        "Duplicate/unchanged alerts are suppressed.",
        "These jobs run on the laptop and do not consume GitHub Actions minutes.",
    ])


def dataage_reply() -> str:
    rows = []
    for kind in ("market", "filings", "status"):
        item = info_engine.latest_observation(kind)
        rows.append(
            f"{kind.title()}: {info_engine.data_age_text(item['observed_at'] if item else None)} ago"
        )
    return "🕒 **Local data freshness**\n" + "\n".join(rows)


def lastscan_reply() -> str:
    connection = info_engine.connect_db()
    try:
        rows = connection.execute(
            """
            SELECT job_name, finished_at, status, detail
            FROM job_runs
            WHERE status != 'RUNNING'
            ORDER BY id DESC
            LIMIT 6
            """
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        return "No local scheduled jobs have completed yet."
    lines = ["🧾 **Recent local jobs**"]
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


def filings_reply() -> str:
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
        if name == "chart":
            days = int(option_value(interaction, "days", 90))
            content, chart_path = chart_reply(days)
            patch_original(application_id, token, content=content, file_path=chart_path)
        elif name == "levels":
            patch_original(application_id, token, content=levels_reply())
        elif name == "events":
            patch_original(application_id, token, content=events_reply())
        elif name == "why":
            patch_original(
                application_id,
                token,
                content=why_reply(str(option_value(interaction, "trade_id", ""))),
            )
        elif name == "help":
            patch_original(application_id, token, content=help_reply())
        elif name == "quote":
            patch_original(application_id, token, content=quote_reply())
        elif name == "trend":
            patch_original(application_id, token, content=trend_reply())
        elif name == "chain":
            patch_original(
                application_id,
                token,
                content=chain_reply(str(option_value(interaction, "side", "call"))),
            )
        elif name == "setup":
            patch_original(application_id, token, content=setup_reply())
        elif name == "watchlist":
            patch_original(application_id, token, content=watchlist_reply())
        elif name == "option":
            patch_original(
                application_id,
                token,
                content=option_reply(str(option_value(interaction, "symbol", ""))),
            )
        elif name == "risk":
            patch_original(
                application_id,
                token,
                content=risk_reply(
                    float(option_value(interaction, "premium", 0)),
                    int(option_value(interaction, "contracts", 1)),
                    str(option_value(interaction, "side", "call")),
                ),
            )
        elif name == "performance":
            patch_original(application_id, token, content=performance_reply())
        elif name == "status":
            patch_original(application_id, token, content=status_reply())
        elif name == "schedule":
            patch_original(application_id, token, content=schedule_reply())
        elif name == "dataage":
            patch_original(application_id, token, content=dataage_reply())
        elif name == "lastscan":
            patch_original(application_id, token, content=lastscan_reply())
        elif name == "filings":
            patch_original(application_id, token, content=filings_reply())
        elif name == "calendar":
            patch_original(application_id, token, content=events_reply())
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
    APP.run(host=HOST, port=PORT, debug=False, threaded=True)
