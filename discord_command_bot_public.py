"""Run TradeBot with public, capped ticker add/remove commands.

This wrapper keeps sensitive scanner controls owner-only while allowing any
server member to add or remove verified optionable tickers from the shared
universe. Member changes are stored under state/ so automatic GitHub updates do
not overwrite them or treat them as dirty tracked configuration.
"""

from __future__ import annotations

import discord_command_bot as bot


bot.OWNER_ONLY_COMMANDS.discard("ticker-remove")


def public_ticker_add_reply(interaction: dict) -> str:
    ticker = bot.dynamic_universe.normalize_symbol(
        str(bot.option_value(interaction, "ticker", ""))
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

    quote = bot.ford_scan.get_quote(ticker) or {}
    price = bot.ford_scan.as_float(quote.get("last"))
    expirations = bot.ford_scan.get_expirations(ticker)
    if price is None or not expirations:
        raise ValueError(
            f"Tradier could not verify {ticker} as a currently optionable ticker."
        )

    user_id = bot.command_user_id(interaction)
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


bot.universe_add_reply = public_ticker_add_reply
bot.universe_pause_reply = public_ticker_remove_reply


if __name__ == "__main__":
    if not bot.PUBLIC_KEY:
        raise SystemExit("DISCORD_PUBLIC_KEY is required")
    try:
        instance_lock = bot.acquire_instance_lock()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    with instance_lock:
        bot.APP.run(host=bot.HOST, port=bot.PORT, debug=False, threaded=True)
