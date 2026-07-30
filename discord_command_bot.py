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
