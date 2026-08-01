"""Run TradeBot with public ticker controls and library-grounded education.

Sensitive scanner controls remain owner-only. Any server member may add or
remove verified optionable tickers within the shared cap. Educational commands
search the comprehensive Learning Center, cite its channels, apply lessons to
read-only live ticker observations, and queue unanswered questions for review.
"""

from __future__ import annotations

import time

import always_on_operations
import discord_command_bot as bot
import learning_application as application
import learning_center_content as learning
import learning_question_gaps as question_gaps
import learning_search_router as routed


routed.install()
always_on_operations.install()
bot.OWNER_ONLY_COMMANDS.discard("ticker-remove")
bot.ticker_registry.CONFIG_PATH = (
    bot.ticker_registry.ROOT / "state" / "member-ticker-registry.json"
)
MEMBER_ADD_COOLDOWN_SECONDS = 15
LAST_MEMBER_ADD: dict[str, float] = {}
ORIGINAL_PROCESS_COMMAND = bot.process_command
ORIGINAL_STATUS_REPLY = bot.status_reply


def card_patch_original(
    application_id: str,
    token: str,
    *,
    content: str,
    file_path=None,
) -> None:
    """Allow full Discord embed-length answers instead of 2,000-char truncation."""
    url = (
        f"https://discord.com/api/v10/webhooks/{application_id}/{token}"
        "/messages/@original"
    )
    payload = {
        "content": str(content or "")[:3900],
        "allowed_mentions": {"parse": []},
    }
    if file_path and file_path.exists():
        payload["attachments"] = [{"id": 0, "filename": file_path.name}]
        with file_path.open("rb") as handle:
            response = bot.requests.patch(
                url,
                data={"payload_json": bot.json.dumps(payload)},
                files={"files[0]": (file_path.name, handle, "image/png")},
                timeout=30,
            )
    else:
        response = bot.requests.patch(url, json=payload, timeout=20)
    response.raise_for_status()


def public_ticker_add_reply(interaction: dict) -> str:
    ticker = bot.dynamic_universe.normalize_symbol(
        str(bot.option_value(interaction, "ticker", ""))
    )
    user_id = bot.command_user_id(interaction)
    now = time.monotonic()
    previous = LAST_MEMBER_ADD.get(user_id, 0.0)
    remaining = MEMBER_ADD_COOLDOWN_SECONDS - (now - previous)
    if remaining > 0:
        raise ValueError(
            f"Please wait {remaining:.0f} seconds before verifying another ticker."
        )

    active = bot.dynamic_universe.initialize()
    maximum = bot.dynamic_universe.max_active_symbols()
    if ticker in active:
        return (
            f"ℹ️ **{ticker} is already active.**\n"
            f"Universe usage: **{len(active)}/{maximum} tickers**."
        )
    if len(active) >= maximum:
        raise ValueError(
            f"The shared universe is full at {maximum} active tickers. "
            "Remove one with `/ticker-remove` before adding another."
        )

    LAST_MEMBER_ADD[user_id] = now
    quote = bot.ford_scan.get_quote(ticker) or {}
    price = bot.ford_scan.as_float(quote.get("last"))
    expirations = bot.ford_scan.get_expirations(ticker)
    if price is None or not expirations:
        raise ValueError(
            f"Tradier could not verify {ticker} as a currently optionable ticker."
        )

    bot.dynamic_universe.add_member_symbol(ticker, user_id=user_id)
    bot.dynamic_universe.upsert_candidates(
        [
            bot.dynamic_universe.Candidate(
                ticker,
                "discord_member",
                score=200,
                last_price=price,
                options_available=True,
                reason=f"Added through Discord by user {user_id}",
            )
        ]
    )
    bot.ticker_registry.save(
        ticker,
        status="ACTIVE",
        note=f"Added to shared universe by Discord user {user_id}",
    )
    updated = bot.dynamic_universe.initialize()
    return "\n".join(
        [
            f"✅ **{ticker} added to the shared scanner universe**",
            f"Verified price: **${price:.2f}** · expirations: **{len(expirations)}**",
            f"Universe usage: **{len(updated)}/{maximum} tickers**",
            "It will enter the rotating scan pool. No ticker-specific channels were created.",
            "Paper trading only; adding a ticker never places an order.",
        ]
    )


def public_ticker_remove_reply(interaction: dict) -> str:
    ticker = bot.dynamic_universe.normalize_symbol(
        str(bot.option_value(interaction, "ticker", ""))
    )
    active = bot.dynamic_universe.initialize()
    if ticker not in active:
        return f"ℹ️ **{ticker} is not currently active.** No change was needed."

    user_id = bot.command_user_id(interaction)
    bot.dynamic_universe.remove_member_symbol(ticker, user_id=user_id)
    bot.ticker_registry.save(
        ticker,
        status="ARCHIVED",
        note=f"Removed from new scans by Discord user {user_id}",
    )
    updated = bot.dynamic_universe.initialize()
    maximum = bot.dynamic_universe.max_active_symbols()
    return "\n".join(
        [
            f"📦 **{ticker} removed from new scans**",
            f"Universe usage: **{len(updated)}/{maximum} tickers**",
            "Existing paper positions remain tracked until they close.",
            "Trade history and performance records were preserved.",
            "Any member can add it again with `/ticker-add`.",
        ]
    )


def owner_ticker_resume_reply(interaction: dict) -> str:
    bot.require_ticker_admin(interaction)
    ticker = bot.dynamic_universe.normalize_symbol(
        str(bot.option_value(interaction, "ticker", ""))
    )
    active = bot.dynamic_universe.initialize()
    maximum = bot.dynamic_universe.max_active_symbols()
    if ticker in active:
        return f"ℹ️ **{ticker} is already active.**"
    if len(active) >= maximum:
        raise ValueError(
            f"The shared universe is full at {maximum} active tickers. "
            "Remove one before resuming another."
        )
    quote = bot.ford_scan.get_quote(ticker) or {}
    price = bot.ford_scan.as_float(quote.get("last"))
    if price is None or not bot.ford_scan.get_expirations(ticker):
        raise ValueError(f"Tradier could not verify optionable ticker {ticker}.")
    bot.dynamic_universe.add_member_symbol(
        ticker, user_id=bot.command_user_id(interaction)
    )
    bot.dynamic_universe.upsert_candidates(
        [
            bot.dynamic_universe.Candidate(
                ticker,
                "owner_resume",
                score=200,
                last_price=price,
                options_available=True,
                reason="Restored through owner-only resume command",
            )
        ]
    )
    bot.ticker_registry.save(
        ticker,
        status="ACTIVE",
        note="Restored through owner-only resume command",
    )
    return (
        f"▶️ **{ticker} resumed.** Universe usage: "
        f"**{len(bot.dynamic_universe.initialize())}/{maximum} tickers**."
    )


def public_ticker_list_reply() -> str:
    active = bot.dynamic_universe.initialize()
    config = bot.dynamic_universe.universe_config()
    excluded = config.get("exclude_symbols") or []
    maximum = bot.dynamic_universe.max_active_symbols()
    remaining = max(0, maximum - len(active))
    return "\n".join(
        [
            "📚 **Dynamic scanner universe**",
            f"**Active ({len(active)}/{maximum}):** {', '.join(active) if active else 'None'}",
            f"**Open slots:** {remaining}",
            f"**Excluded:** {', '.join(excluded) if excluded else 'None'}",
            "Market-hours scan batch: **up to 12 tickers**.",
            "Off-hours research rotates smaller batches automatically every 30 minutes.",
            "Any member may add or remove tickers; open positions remain tracked.",
        ]
    )


def public_ticker_status_reply(ticker: str) -> str:
    symbol = bot.dynamic_universe.normalize_symbol(ticker)
    active = bot.dynamic_universe.initialize()
    maximum = bot.dynamic_universe.max_active_symbols()
    return "\n".join(
        [
            f"🧩 **{symbol}** · **{'ACTIVE' if symbol in active else 'NOT ACTIVE'}**",
            f"Universe usage: **{len(active)}/{maximum} tickers**",
            "Shared filters, lifecycle channels, and performance tracking apply.",
            "Active symbols rotate through market-hours scans and closed-market research batches.",
            "Removing a ticker blocks new scans but never abandons an open paper position.",
        ]
    )


def public_status_reply(ticker: str) -> str:
    base = ORIGINAL_STATUS_REPLY(ticker)
    try:
        operations = always_on_operations.operations_status_summary()
    except Exception as exc:
        operations = (
            "## Automation\nScheduler diagnostics could not be read: "
            f"`{type(exc).__name__}: {str(exc)[:180]}`. The failure remains visible in "
            "#automation-diagnostics."
        )
    return f"{base}\n\n{operations}"[:3900]


def public_process_command(interaction: dict) -> None:
    """Preserve all commands while giving `/ask` full interaction context."""
    name = str(interaction.get("data", {}).get("name") or "")
    if name != "ask":
        ORIGINAL_PROCESS_COMMAND(interaction)
        return

    application_id = str(interaction.get("application_id") or "")
    token = str(interaction.get("token") or "")
    try:
        question = str(bot.option_value(interaction, "question", ""))
        bot.patch_original(
            application_id,
            token,
            content=question_gaps.answer_with_gap_tracking(interaction, question),
        )
    except Exception as exc:
        safe_error = f"{type(exc).__name__}: {exc}"[:1200]
        try:
            bot.patch_original(
                application_id,
                token,
                content=f"⚠️ Command failed safely.\n```{safe_error}```",
            )
        except bot.requests.RequestException:
            pass


bot.patch_original = card_patch_original
bot.universe_add_reply = public_ticker_add_reply
bot.universe_pause_reply = public_ticker_remove_reply
bot.universe_resume_reply = owner_ticker_resume_reply
bot.universe_list_reply = public_ticker_list_reply
bot.universe_status_reply = public_ticker_status_reply
bot.status_reply = public_status_reply
bot.ask_reply = application.answer
bot.explain_reply = routed.explain
bot.process_command = public_process_command


if __name__ == "__main__":
    if not bot.PUBLIC_KEY:
        raise SystemExit("DISCORD_PUBLIC_KEY is required")
    try:
        instance_lock = bot.acquire_instance_lock()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    with instance_lock:
        bot.APP.run(host=bot.HOST, port=bot.PORT, debug=False, threaded=True)
