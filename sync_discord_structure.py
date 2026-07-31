"""Idempotently synchronize the shared Tradysquids Discord information layout."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import ford_scan
from run_with_env import load_env

BOT_CHANNEL_ALLOW = (
    1024  # view channel
    | 2048  # send messages
    | 16384  # embed links
    | 32768  # attach files
    | 65536  # read message history
    | (1 << 34)  # manage threads and forum posts
    | (1 << 38)  # send messages in threads
)
ADMINISTRATOR_PERMISSION = 1 << 3
BAN_MEMBERS_PERMISSION = 1 << 2
BOT_ROLE_REQUIRED_PERMISSIONS = {
    "Kick Members": 1 << 1,
    "Manage Channels": 1 << 4,
    "Manage Server": 1 << 5,
    "View Audit Log": 1 << 7,
    "View Channels": 1 << 10,
    "Send Messages": 1 << 11,
    "Manage Messages": 1 << 13,
    "Embed Links": 1 << 14,
    "Attach Files": 1 << 15,
    "Read Message History": 1 << 16,
    "Change Nickname": 1 << 26,
    "Manage Nicknames": 1 << 27,
    "Manage Roles": 1 << 28,
    "Manage Webhooks": 1 << 29,
    "Manage Expressions": 1 << 30,
    "Use Application Commands": 1 << 31,
    "Manage Events": 1 << 33,
    "Manage Threads and Posts": 1 << 34,
    "Send Messages in Threads": 1 << 38,
    "Timeout Members": 1 << 40,
}


@dataclass(frozen=True)
class ChannelSpec:
    category: str
    name: str
    topic: str
    channel_type: int = 0


CATEGORY_ORDER = [
    "START HERE",
    "COMMUNITY",
    "LIVE TRADING DESK",
    "MARKET INTELLIGENCE",
    "PERFORMANCE",
    "LEARNING CENTER",
    "OWNER CONTROL",
]

CHANNELS = [
    ChannelSpec("START HERE", "welcome", "What Tradysquids is, paper-trading status, and navigation."),
    ChannelSpec("START HERE", "rules-and-risk", "Rules, options risk, educational-only disclaimer, privacy, and conduct."),
    ChannelSpec("START HERE", "how-to-use-tradebot", "TradeBot commands, examples, schedules, and data limitations."),
    ChannelSpec("COMMUNITY", "general-chat", "The main member conversation channel."),
    ChannelSpec("LIVE TRADING DESK", "scanner-feed", "Every scanned ticker, filter result, and data timestamp."),
    ChannelSpec("LIVE TRADING DESK", "new-positions", "New paper positions that passed all active filters."),
    ChannelSpec("LIVE TRADING DESK", "held-positions", "Updating cards for open paper positions."),
    ChannelSpec("LIVE TRADING DESK", "wins", "Closed profitable paper positions."),
    ChannelSpec("LIVE TRADING DESK", "losses", "All other closed paper positions; no scratch outcome."),
    ChannelSpec("LIVE TRADING DESK", "trade-journal", "One complete lifecycle thread per paper trade.", 15),
    ChannelSpec("MARKET INTELLIGENCE", "premarket", "Premarket universe, gaps, calendars, and scheduled events."),
    ChannelSpec("MARKET INTELLIGENCE", "breaking-alerts", "Deduplicated TradingView and provider events."),
    ChannelSpec("MARKET INTELLIGENCE", "charts-and-levels", "Requested and scheduled charts, support, and resistance."),
    ChannelSpec("MARKET INTELLIGENCE", "news-and-events", "Cached company and market news with timestamps."),
    ChannelSpec("MARKET INTELLIGENCE", "market-regime", "Broad-market context, trend, and volatility conditions."),
    ChannelSpec("MARKET INTELLIGENCE", "universe-watch", "Active symbols, discovery source, rank, and exclusions."),
    ChannelSpec("PERFORMANCE", "performance-dashboard", "Lifecycle totals and recorded paper performance."),
    ChannelSpec("PERFORMANCE", "strategy-results", "Results by strategy, DTE, delta, and regime."),
    ChannelSpec("PERFORMANCE", "ticker-results", "Results by underlying without ticker-specific desks."),
    ChannelSpec("PERFORMANCE", "learning-results", "Evidence summaries that never change filters automatically."),
    ChannelSpec("LEARNING CENTER", "learning-index", "Beginner curriculum for options, risk, execution, and review."),
    ChannelSpec("LEARNING CENTER", "ask-tradebot", "Use /ask and /explain for curated educational answers."),
    ChannelSpec("LEARNING CENTER", "examples-and-reviews", "Paper-trade walkthroughs and post-trade reviews."),
    ChannelSpec("OWNER CONTROL", "scanner-controls", "Owner-only universe, filter, and schedule controls."),
    ChannelSpec("OWNER CONTROL", "system-health", "Local service health, freshness, queue depth, and restarts."),
    ChannelSpec("OWNER CONTROL", "provider-status", "Tradier, TradingView, Discord, and read-only MCP status."),
    ChannelSpec("OWNER CONTROL", "workflow-log", "Release and rare GitHub backup-run history."),
    ChannelSpec("OWNER CONTROL", "upgrade-review", "Member suggestions pending owner approval or decline."),
    ChannelSpec("OWNER CONTROL", "security-log", "Rejected requests and configuration warnings without secrets."),
]

DELETE_CHANNELS = {
    "qualified-trades", "scratches", "expired", "exit-alerts",
    "f-dashboard", "f-options-setups", "f-charts", "f-news-events",
    "f-research-performance", "vale-dashboard", "vale-options-setups",
    "vale-charts", "vale-news-events", "vale-research-performance",
}

DELETE_CATEGORIES = {
    "ARCHIVE - LEGACY",
    "TICKER • F",
    "TICKER • VALE",
}

CHANNEL_STARTERS = {
    "scanner-feed": "Runs every 15 minutes during regular market hours.",
    "new-positions": "Updates only when a paper setup passes every active filter.",
    "held-positions": "Updates from live streamed quotes while a paper position is open.",
    "wins": "Updates immediately when a tracked paper position closes profitably.",
    "losses": "Updates immediately when a tracked paper position closes without a profit.",
    "premarket": "Updated on weekday premarket research runs.",
    "breaking-alerts": "Event-driven TradingView and provider alerts appear here.",
    "charts-and-levels": "Updated by scheduled research and `/chart` or `/levels` requests.",
    "news-and-events": "Updated by scheduled news checks and `/events` requests.",
    "market-regime": "Updated with broad-market and scanner context.",
    "universe-watch": "Updated when the rotating scanner universe is refreshed.",
    "performance-dashboard": "Updated as paper trades open and close.",
    "strategy-results": "Updated from recorded paper-trade outcomes.",
    "ticker-results": "Updated from recorded outcomes grouped by underlying.",
    "learning-results": "Updated by the six-hour local learning review.",
    "ask-tradebot": "Use `/ask` or `/explain`; general conversation belongs in #general-chat.",
    "examples-and-reviews": "Paper-trade examples and completed reviews appear here.",
    "system-health": "Updated every 15 minutes by the local engine.",
    "provider-status": "Shows the current data-provider and webhook status.",
    "workflow-log": "Used only for releases and rare GitHub backup runs.",
    "upgrade-review": "Manual owner review only. No background upgrade polling.",
    "security-log": "Receives rejected requests and configuration warnings.",
}

GUIDES = {
    "welcome": """# Tradysquids
Tradysquids is a local-first, paper-trading research system for learning how
options setups are found, tracked, and reviewed. It scans a rotating universe
instead of favoring one ticker. Start with #rules-and-risk, then use
#how-to-use-tradebot and #learning-index. No brokerage orders are placed.""",
    "rules-and-risk": """# Rules, Risk, and Conduct
1. Educational information only—not professional financial advice.
2. Options can lose 100% of premium. Spreads still carry assignment, exercise,
expiration, pin, liquidity, and maximum-loss risk.
3. Never promise returns, pressure another member, impersonate a professional,
share private information, spam, harass, or manipulate markets.
4. General conversation belongs in #general-chat. Use information channels for
their named bot features.
5. Verify every quote and contract independently. You alone decide and place
your trades. Paper results and historical performance do not guarantee profit.""",
    "how-to-use-tradebot": """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.
• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/filings`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — beginner education.
• `/filters`, `/ticker-list`, `/ticker-status` — public configuration status.
• `/scan-now scope:` — owner-only manual discovery, scanning, and reporting.
Universe and filter changes are owner-only. Commands use local services and do
not consume GitHub Actions minutes. Discord maintenance is reviewed manually on
Monday, Wednesday, and Friday. Upgrade suggestions are never auto-approved.""",
    "learning-index": """# Learning Center
Learn in this order: bid/ask and limit orders; calls and puts; strike, premium,
expiration and DTE; delta, theta and implied volatility; liquidity; maximum
loss and position sizing; assignment/exercise; support/resistance and trend;
then paper-trade journaling and evidence review.
Use `/ask question:` or `/explain topic:` for curated definitions. Cheap does
not automatically mean safe. Review the complete risk before every decision.""",
    "scanner-controls": """# Owner Scanner Controls
`/filters` shows active limits. `/filter-set` changes a guarded local value.
`/ticker-add`, `/ticker-pause`, `/ticker-resume`, and `/ticker-remove` manage
the rotating universe without creating ticker-specific desks or triggering
GitHub. `/scan-now scope:Everything` immediately runs discovery, market
intelligence, every active ticker, position tracking, and health reporting.
Existing paper positions remain tracked after removal. The runtime is read-only
toward brokerages and cannot place trades.""",
}


def normalized(value: str) -> str:
    return str(value or "").strip().casefold()


def main() -> int:
    load_env()
    apply = "--apply" in sys.argv
    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise SystemExit("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required")
    existing = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    if "--inventory" in sys.argv:
        category_names = {
            str(item["id"]): item["name"]
            for item in existing
            if item.get("type") == 4
        }
        for item in sorted(
            existing,
            key=lambda row: (int(row.get("position") or 0), row.get("name") or ""),
        ):
            parent = category_names.get(str(item.get("parent_id") or ""), "(root)")
            print(f"{item.get('type')}\t{parent}\t{item.get('name')}\t{item.get('id')}")
        return 0
    warnings: list[str] = []
    bot_user = tracker._request("GET", "/users/@me")
    roles = tracker._request("GET", f"/guilds/{tracker.guild_id}/roles")
    bot_role = next(
        (
            role
            for role in roles
            if str((role.get("tags") or {}).get("bot_id") or "")
            == str(bot_user.get("id") or "")
        ),
        None,
    )
    bot_role_id = str((bot_role or {}).get("id") or "")
    bot_permissions = int((bot_role or {}).get("permissions") or 0)
    if not apply and bot_permissions & ADMINISTRATOR_PERMISSION:
        warnings.append(
            "TradeBot has Administrator; remove it because Administrator includes bans."
        )
    if not apply and bot_permissions & BAN_MEMBERS_PERMISSION:
        warnings.append("TradeBot has Ban Members; remove that permission.")
    missing_bot_permissions = [
        name
        for name, permission in BOT_ROLE_REQUIRED_PERMISSIONS.items()
        if not bot_permissions & permission
    ]
    if not apply and missing_bot_permissions:
        warnings.append(
            "TradeBot is missing required non-ban permissions: "
            + ", ".join(missing_bot_permissions)
            + "."
        )
    by_name = {normalized(item.get("name")): item for item in existing}
    categories: dict[str, dict] = {}

    for position, name in enumerate(CATEGORY_ORDER):
        item = next(
            (
                row for row in existing
                if row.get("type") == 4 and normalized(row.get("name")) == normalized(name)
            ),
            None,
        )
        if item is None:
            print(f"{'CREATE' if apply else 'WOULD CREATE'} category {name}")
            if apply:
                item = tracker._request(
                    "POST",
                    f"/guilds/{tracker.guild_id}/channels",
                    {
                        "name": name,
                        "type": 4,
                        "position": position,
                    },
                )
        if item:
            categories[name] = item
            if apply and bot_role_id:
                try:
                    tracker._request(
                        "PUT",
                        f"/channels/{item['id']}/permissions/{bot_role_id}",
                        {
                            "type": 0,
                            "allow": str(BOT_CHANNEL_ALLOW),
                            "deny": "0",
                        },
                    )
                except ford_scan.DiscordError as exc:
                    warnings.append(f"TradeBot access to {name}: {exc}")

    for spec in CHANNELS:
        category = categories.get(spec.category)
        item = by_name.get(normalized(spec.name))
        if item is None:
            print(f"{'CREATE' if apply else 'WOULD CREATE'} #{spec.name}")
            if apply:
                item = tracker._request(
                    "POST",
                    f"/guilds/{tracker.guild_id}/channels",
                    {
                        "name": spec.name,
                        "type": spec.channel_type,
                        "parent_id": category["id"],
                        "topic": spec.topic,
                    },
                )
                by_name[normalized(spec.name)] = item
            continue
        changes = {}
        if apply and bot_role_id:
            try:
                tracker._request(
                    "PUT",
                    f"/channels/{item['id']}/permissions/{bot_role_id}",
                    {
                        "type": 0,
                        "allow": str(BOT_CHANNEL_ALLOW),
                        "deny": "0",
                    },
                )
            except ford_scan.DiscordError as exc:
                warnings.append(f"TradeBot access to #{spec.name}: {exc}")
        if category and str(item.get("parent_id") or "") != str(category["id"]):
            changes["parent_id"] = category["id"]
        if spec.channel_type == 0 and str(item.get("topic") or "") != spec.topic:
            changes["topic"] = spec.topic
        if changes:
            print(f"{'UPDATE' if apply else 'WOULD UPDATE'} #{spec.name}")
            if apply:
                try:
                    tracker._request("PATCH", f"/channels/{item['id']}", changes)
                except ford_scan.DiscordError as exc:
                    warnings.append(f"#{spec.name}: {exc}")

    for name in sorted(DELETE_CHANNELS):
        item = by_name.get(normalized(name))
        if item:
            print(f"{'DELETE' if apply else 'WOULD DELETE'} #{name}")
            if apply:
                try:
                    tracker._request("DELETE", f"/channels/{item['id']}")
                except ford_scan.DiscordError as exc:
                    warnings.append(f"delete #{name}: {exc}")

    for category_name in sorted(DELETE_CATEGORIES):
        category = next(
            (
                item
                for item in existing
                if item.get("type") == 4
                and normalized(item.get("name")) == normalized(category_name)
            ),
            None,
        )
        if category:
            print(f"{'DELETE' if apply else 'WOULD DELETE'} category {category_name}")
            if apply:
                try:
                    tracker._request("DELETE", f"/channels/{category['id']}")
                except ford_scan.DiscordError as exc:
                    warnings.append(f"delete category {category_name}: {exc}")

    if apply:
        for channel_name, content in GUIDES.items():
            channel = by_name.get(normalized(channel_name))
            if not channel:
                continue
            try:
                recent = tracker._request(
                    "GET", f"/channels/{channel['id']}/messages?limit=50"
                )
                marker = content.splitlines()[0]
                message = next(
                    (
                        item for item in recent
                        if (item.get("author") or {}).get("bot")
                        and marker in ford_scan.message_search_text(item)
                    ),
                    None,
                )
                payload = {"content": content[:2000], "allowed_mentions": {"parse": []}}
                if message:
                    tracker._request(
                        "PATCH",
                        f"/channels/{channel['id']}/messages/{message['id']}",
                        payload,
                    )
                else:
                    tracker._request(
                        "POST", f"/channels/{channel['id']}/messages", payload
                    )
            except ford_scan.DiscordError as exc:
                warnings.append(f"guide #{channel_name}: {exc}")

        for channel_name, schedule in CHANNEL_STARTERS.items():
            channel = by_name.get(normalized(channel_name))
            if not channel or channel.get("type") != 0:
                continue
            try:
                recent = tracker._request(
                    "GET", f"/channels/{channel['id']}/messages?limit=1"
                )
                if recent:
                    continue
                topic = str(channel.get("topic") or "").strip()
                content = (
                    f"# {channel_name.replace('-', ' ').title()}\n"
                    f"{topic}\n\n**Update behavior:** {schedule}\n"
                    "No information is shown until a real event or scheduled update occurs."
                )
                tracker._request(
                    "POST",
                    f"/channels/{channel['id']}/messages",
                    {"content": content[:2000], "allowed_mentions": {"parse": []}},
                )
            except ford_scan.DiscordError as exc:
                warnings.append(f"starter #{channel_name}: {exc}")

    print("Discord structure synchronized." if apply else "Dry run complete; no Discord changes made.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
