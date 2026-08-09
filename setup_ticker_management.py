"""Create or refresh the owner-facing Discord ticker management guide."""

from __future__ import annotations

import spy_scanner

CATEGORY_NAME = "Start Here"
CHANNEL_NAME = "ticker-management"
GUIDE_MARKER = "Tradysquids Ticker Management"
CHANNEL_TOPIC = (
    "Owner commands for adding, pausing, resuming, archiving, and inspecting "
    "ticker strategies."
)

GUIDE = """# Tradysquids Ticker Management

This channel explains the shared scanner universe. Any member may add a verified
optionable ticker. Pausing, resuming, and removing remain owner-only.

## Add a ticker
`/ticker-add ticker:VALE`

The bot verifies the stock and options chain, adds the symbol to the shared
universe, and enables scheduled research and eligible trade generation. It does
not create a ticker category or ticker-specific channels.

## Pause a ticker for today
`/ticker-pause ticker:VALE duration:Today only`

No new VALE positions will be generated. It resumes automatically on the next
market day. Existing positions continue to be tracked.

## Pause until you decide
`/ticker-pause ticker:VALE duration:Until resumed`

Use `/ticker-resume ticker:VALE` when you want it active again.

## Remove a ticker from active scanning
`/ticker-remove ticker:VALE`

Remove means **archive**, not delete. New positions stop while trades, filters,
and performance history remain.
Existing positions continue through the normal lifecycle.

## Inspect the registry
- `/ticker-list` — active, paused, and archived strategies.
- `/ticker-status ticker:VALE` — one symbol's shared-universe state.

## Shared trade lifecycle
All tickers use the same channels:
`scanner-feed` → `new-positions` → `held-positions` → `wins` or `losses`.

Charts, news, market intelligence, and performance also stay in their shared
channels. A setup becomes a trade only when every configured chart, event,
liquidity, DTE, delta, spread, and risk rule passes. Educational information
only—not professional financial advice."""


def main() -> int:
    tracker = spy_scanner.DiscordTracker(
        spy_scanner.DISCORD_BOT_TOKEN, spy_scanner.DISCORD_GUILD_ID
    )
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category = next(
        (
            channel for channel in channels
            if channel.get("type") == 4
            and str(channel.get("name") or "").casefold() == CATEGORY_NAME.casefold()
        ),
        None,
    )
    if not category:
        raise SystemExit(f"Discord category '{CATEGORY_NAME}' was not found")
    channel = next(
        (
            item for item in channels
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
    recent = tracker._request("GET", f"/channels/{channel['id']}/messages?limit=50")
    message = next(
        (
            item for item in recent
            if (item.get("author") or {}).get("bot")
            and GUIDE_MARKER in spy_scanner.message_search_text(item)
        ),
        None,
    )
    payload = {
        "content": GUIDE[:2000],
        "allowed_mentions": {"parse": []},
    }
    if message:
        tracker._request(
            "PATCH", f"/channels/{channel['id']}/messages/{message['id']}", payload
        )
    else:
        tracker._request("POST", f"/channels/{channel['id']}/messages", payload)
    print(f"Ticker management guide ready in #{CHANNEL_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
