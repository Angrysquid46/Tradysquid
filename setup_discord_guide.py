"""Create or refresh the pinned Tradysquids command guide channel."""

from __future__ import annotations

import ford_scan

CATEGORY_NAME = "Start Here"
CHANNEL_NAME = "bot-commands"
GUIDE_MARKER = "Tradysquids Command Guide"
CHANNEL_TOPIC = (
    "How to use TradeBot's dynamic ticker market, options, chart, risk, research, "
    "performance, and reliability commands."
)

GUIDE = """# 🧭 Tradysquids Command Guide

## How to run a command
1. Open any Discord text channel.
2. Type `/`.
3. Select a TradeBot command.
4. Complete any fields Discord displays.
5. Press **Send**.

## Market and charts
- `/quote ticker:` — price, daily change, volume, bid/ask and timestamp.
- `/trend ticker:` — SMA20/50/200, RSI, MACD, ATR and Bollinger range.
- `/levels ticker:` — trend regime plus support and resistance.
- `/chart ticker: days:` — generate a fresh 30, 60, 90 or 120-day chart.
- `/watchlist ticker:` — reactive levels and monitored conditions.
- `/setup ticker:` — qualified direction and a research shortlist, or NO TRADE.

## Ticker options
- `/chain ticker: side:` — rank calls or puts by liquidity and contract quality.
- `/option symbol:` — inspect bid/ask, spread, OI, volume, Greeks and IV.
- `/risk premium: contracts: side:` — premium risk and management examples.

## Research and learning
- `/events ticker:` or `/calendar ticker:` — ticker event, news, and filing links.
- `/filings ticker:` — ticker filing links and recent news.
- `/explain topic:` — delta, theta, IV, spread, OI, DTE, RSI or ATR.
- `/why trade_id:` — recorded evidence and rationale for a tracked trade.

## Ticker management (owner only)
- `/ticker-add ticker:` — integrate a ticker and create its five-channel desk.
- `/ticker-pause ticker: duration:` — stop new positions today or indefinitely.
- `/ticker-resume ticker:` — reactivate a paused or archived ticker.
- `/ticker-remove ticker:` — archive without deleting trades or history.
- `/ticker-list` — show active, paused, and archived strategies.
- `/ticker-status ticker:` — inspect one ticker's registry and desk status.

## Tracking and reliability
- `/performance ticker:` — recorded wins, losses, open trades and P/L.
- `/status` — bot, Tradier, scheduler, Discord and SEC configuration.
- `/dataage ticker:` — freshness of locally cached ticker data.
- `/lastscan` — recent local monitoring results.
- `/schedule` — the no-GitHub local monitoring schedule.
- `/help` — display the command list in any channel.

## What must remain running
Keep these laptop windows open:
- **Tradysquids Command Bot**
- **Tradysquids Information Engine**
- **Tradysquids ngrok Tunnel**

The local engine performs frequent work without GitHub Actions. It suppresses
unchanged alerts to reduce noise. Information can be delayed, incomplete, or
incorrect. Options can lose 100% of premium. This is educational information,
not professional financial advice or a guarantee of profit."""


def main() -> int:
    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise SystemExit("Local DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required")

    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category = next(
        (
            channel
            for channel in channels
            if channel.get("type") == 4
            and str(channel.get("name") or "").casefold() == CATEGORY_NAME.casefold()
        ),
        None,
    )
    if not category:
        raise SystemExit(f"Discord category '{CATEGORY_NAME}' was not found")

    channel = next(
        (
            item
            for item in channels
            if item.get("type") == 0
            and str(item.get("name") or "").casefold() == CHANNEL_NAME.casefold()
        ),
        None,
    )
    if not channel:
        channel = tracker._request(
            "POST",
            f"/guilds/{tracker.guild_id}/channels",
            {
                "name": CHANNEL_NAME,
                "type": 0,
                "parent_id": category["id"],
                "topic": CHANNEL_TOPIC,
            },
        )
        print(f"Created #{CHANNEL_NAME}.")
    else:
        print(f"Found #{CHANNEL_NAME}.")

    recent = tracker._request("GET", f"/channels/{channel['id']}/messages?limit=50")
    message = next(
        (
            item
            for item in recent
            if (item.get("author") or {}).get("bot")
            and GUIDE_MARKER in ford_scan.message_search_text(item)
        ),
        None,
    )
    payload = {
        "content": GUIDE[:2000],
        "allowed_mentions": {"parse": []},
    }
    if message:
        message = tracker._request(
            "PATCH",
            f"/channels/{channel['id']}/messages/{message['id']}",
            payload,
        )
        print("Updated the command guide.")
    else:
        message = tracker._request(
            "POST", f"/channels/{channel['id']}/messages", payload
        )
        print("Posted the command guide.")

    try:
        tracker._request(
            "PUT", f"/channels/{channel['id']}/pins/{message['id']}"
        )
        print("Pinned the command guide.")
    except ford_scan.DiscordError as exc:
        if "HTTP 403" not in str(exc):
            raise
        print(
            "Guide posted. Pin it with the Discord owner account because "
            "TradeBot does not have Manage Messages permission."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
