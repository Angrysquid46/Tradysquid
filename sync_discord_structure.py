"""Idempotently synchronize the shared Tradysquids Discord information layout."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import ford_scan
from run_with_env import load_env


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
    "ARCHIVE - LEGACY",
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

LEGACY_CHANNELS = {
    "qualified-trades", "scratches", "expired", "exit-alerts",
    "f-dashboard", "f-options-setups", "f-charts", "f-news-events",
    "f-research-performance", "vale-dashboard", "vale-options-setups",
    "vale-charts", "vale-news-events", "vale-research-performance",
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
Universe and filter changes are owner-only. Commands use local services and do
not consume GitHub Actions minutes.""",
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
GitHub. Existing paper positions remain tracked after removal. The runtime is
read-only toward brokerages and cannot place trades.""",
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
        if category and str(item.get("parent_id") or "") != str(category["id"]):
            changes["parent_id"] = category["id"]
        if spec.channel_type == 0 and str(item.get("topic") or "") != spec.topic:
            changes["topic"] = spec.topic
        if changes:
            print(f"{'UPDATE' if apply else 'WOULD UPDATE'} #{spec.name}")
            if apply:
                tracker._request("PATCH", f"/channels/{item['id']}", changes)

    archive = categories.get("ARCHIVE - LEGACY")
    for name in sorted(LEGACY_CHANNELS):
        item = by_name.get(normalized(name))
        if item and archive and str(item.get("parent_id") or "") != str(archive["id"]):
            print(f"{'ARCHIVE' if apply else 'WOULD ARCHIVE'} #{name}")
            if apply:
                tracker._request(
                    "PATCH",
                    f"/channels/{item['id']}",
                    {"parent_id": archive["id"]},
                )

    if apply:
        for channel_name, content in GUIDES.items():
            channel = by_name.get(normalized(channel_name))
            if not channel:
                continue
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

    print("Discord structure synchronized." if apply else "Dry run complete; no Discord changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
