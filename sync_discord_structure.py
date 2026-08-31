"""Idempotently synchronize the shared Tradysquids Discord information layout."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import discord_transport
import learning_center_index
from run_with_env import load_env

BOT_CHANNEL_ALLOW = (
    1024
    | 2048
    | 16384
    | 32768
    | 65536
    | (1 << 34)
    | (1 << 38)
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


STRATEGIES_CATEGORY_NAME = "STRATEGIES"
_OLD_STRATEGY_CATEGORY_NAMES = [
    "1-MINUTE STRATEGY", "5-MINUTE STRATEGY", "KEY-LEVELS STRATEGY", "EXPANSION-LEVEL STRATEGY",
]

CATEGORY_ORDER = [
    "START HERE",
    "COMMUNITY",
    "MARKET INTELLIGENCE",
    "LEARNING CENTER",
    "BLACKTIDE",
    "RIPTIDE",
    "SURGE",
    "GROK",
    "OWNER CONTROL",
]

CHANNELS = [
    ChannelSpec("START HERE", "welcome", "What Tradysquids is, paper-trading status, and navigation."),
    ChannelSpec("START HERE", "rules-and-risk", "Rules, options risk, educational-only disclaimer, privacy, and conduct."),
    ChannelSpec("START HERE", "how-to-use-tradebot", "TradeBot commands, examples, schedules, and data limitations."),
    ChannelSpec("START HERE", "how-trades-are-found", "Transparent scanner discovery, qualification, play-selection, and rejection rules."),
    ChannelSpec("COMMUNITY", "general-chat", "The main member conversation channel."),
    ChannelSpec("MARKET INTELLIGENCE", "premarket", "Premarket universe, gaps, calendars, and scheduled events."),
    ChannelSpec("MARKET INTELLIGENCE", "breaking-alerts", "Deduplicated TradingView and provider events."),
    ChannelSpec("MARKET INTELLIGENCE", "charts-and-levels", "Requested and scheduled charts, support, and resistance."),
    ChannelSpec("MARKET INTELLIGENCE", "news-and-events", "Cached company and market news with timestamps."),
    ChannelSpec("MARKET INTELLIGENCE", "market-regime", "Broad-market context, trend, and volatility conditions."),
    ChannelSpec("MARKET INTELLIGENCE", "spy-technicals", "SPY technical history from the standalone market-memory store."),
    ChannelSpec("OWNER CONTROL", "system-health", "Local service health, freshness, queue depth, and restarts."),
    ChannelSpec("OWNER CONTROL", "workflow-log", "Release and deployment history."),
    ChannelSpec("BLACKTIDE", "blacktide-dashboard", "BLACKTIDE stat cards (balance, generation, P/L, win rate, streak, drawdown) plus a bankroll history chart."),
    ChannelSpec("BLACKTIDE", "blacktide-held-trades", "BLACKTIDE's current live position, updated on open/close."),
    ChannelSpec("BLACKTIDE", "blacktide-winners", "BLACKTIDE's winning closed trades."),
    ChannelSpec("BLACKTIDE", "blacktide-losers", "BLACKTIDE's losing closed trades."),
    ChannelSpec("RIPTIDE", "riptide-dashboard", "RIPTIDE stat cards (balance, generation, P/L, win rate, streak, drawdown) plus a bankroll history chart."),
    ChannelSpec("RIPTIDE", "riptide-held-trades", "RIPTIDE's current live position, updated on open/close."),
    ChannelSpec("RIPTIDE", "riptide-winners", "RIPTIDE's winning closed trades."),
    ChannelSpec("RIPTIDE", "riptide-losers", "RIPTIDE's losing closed trades."),
    ChannelSpec("SURGE", "surge-dashboard", "SURGE stat cards (balance, generation, P/L, win rate, streak, drawdown) plus a bankroll history chart."),
    ChannelSpec("SURGE", "surge-held-trades", "SURGE's current live position, updated on open/close."),
    ChannelSpec("SURGE", "surge-winners", "SURGE's winning closed trades."),
    ChannelSpec("SURGE", "surge-losers", "SURGE's losing closed trades."),
    ChannelSpec("GROK", "grok-dashboard", "GROK stat cards (balance, generation, P/L, win rate, streak, drawdown) plus a bankroll history chart."),
    ChannelSpec("GROK", "grok-held-trades", "GROK's current live position, updated on open/close."),
    ChannelSpec("GROK", "grok-winners", "GROK's winning closed trades."),
    ChannelSpec("GROK", "grok-losers", "GROK's losing closed trades."),
    ChannelSpec("START HERE", "bot-commands", "Complete TradeBot slash-command reference and ticker-context instructions."),
    ChannelSpec("START HERE", "risk-management", "Options risk disclosures and pre-trade safety checklist."),
    ChannelSpec("LEARNING CENTER", "learning-index", "Start here: the complete 43-chapter curriculum."),
]

# GROK's category addition must not retire the existing curriculum topology.
# Generate these declarations from the canonical chapter registry so Discord
# reconciliation and the Learning Center index cannot drift apart again.
CHANNELS.extend(
    ChannelSpec(
        "LEARNING CENTER",
        learning_center_index.chapter_channel_name(chapter),
        f"Chapter {chapter}: {title}.",
    )
    for chapter, title in learning_center_index.CHAPTERS.items()
)

DELETE_CHANNELS = {
    "strategies-dashboard", "strategies-results",
    "held-positions",
    "qualified-trades", "scratches", "expired", "exit-alerts",
    "f-dashboard", "f-options-setups", "f-charts", "f-news-events",
    "f-research-performance", "vale-dashboard", "vale-options-setups",
    "vale-charts", "vale-news-events", "vale-research-performance",
    "regular-calls", "regular-puts", "swing-calls", "swing-puts",
    "bull-put-spreads", "bear-call-spreads",
    "performance-dashboard", "strategy-results", "strategy-breakdown",
    "1m-performance", "1m-results", "5m-performance", "5m-results",
    "key-levels-performance", "key-levels-results",
    "expansion-performance", "expansion-results",
    "scanner-feed", "new-positions", "wins", "losses", "trade-journal",
    "backtest-results", "ticker-results", "learning-results",
    "strategy-control", "strategy-settings", "strategy-versions",
    "trade-overrides", "strategy-change-log", "strategy-recommendations",
    "strategy-rules", "daily-recap", "weekly-report", "monthly-dashboard",
    "01-stock-market-foundations", "02-company-fundamentals",
    "03-financial-statements", "04-valuation-and-quality",
    "05-market-mechanics-orders", "06-charts-price-action",
    "07-technical-analysis", "08-volume-breadth-internals",
    "09-macro-sectors-catalysts", "10-stock-trading-strategies",
    "11-short-selling-margin", "12-portfolio-risk", "13-options-basics",
    "14-option-chain-liquidity", "15-option-pricing-greeks", "16-volatility",
    "17-directional-options", "18-income-and-hedging",
    "19-spreads-multi-leg", "20-trade-planning-execution",
    "21-expiration-assignment", "22-events-corporate-actions",
    "23-psychology-journaling", "24-backtesting-statistics",
    "25-brokers-accounts-taxes", "26-research-data-tools",
    "27-scams-security-myths", "32-dealer-gamma-and-hedging",
    "33-fair-value-and-mean-reversion", "34-the-market-clock",
    "35-algorithmic-glossary", "36-commodities-and-fixed-income",
    "ask-tradebot", "examples-and-reviews", "learning-start",
    "upgrade-requests", "upgrade-review", "applied-upgrades", "security-log",
    "scanner-controls",
    "scanner-status", "api-errors", "update-status", "provider-status",
    "system-activity", "automation-diagnostics", "universe-watch",
    "axiom-winners-losers", "blacktide-winners-losers",
    "axiom-dashboard", "axiom-held-trades", "axiom-winners", "axiom-losers",
    "blacktide-vs-claude",
}

DELETE_CATEGORIES = {
    "ARCHIVE - LEGACY", "TICKER • F", "TICKER • VALE",
    "LIVE TRADING DESK", "PERFORMANCE", "STRATEGY CONTROL", "SYSTEM",
    "RIVALRY", "AXIOM",
    *_OLD_STRATEGY_CATEGORY_NAMES,
    STRATEGIES_CATEGORY_NAME,
}

CHANNEL_STARTERS = {
    "system-health": "Updated by the local supervisor and engine.",
    "blacktide-dashboard": "Updated every 5 minutes: stat cards plus a bankroll history chart.",
    "blacktide-held-trades": "Updated when BLACKTIDE opens or closes its position.",
    "blacktide-winners": "Updated immediately when a BLACKTIDE position closes profitably.",
    "blacktide-losers": "Updated immediately when a BLACKTIDE position closes without a profit.",
    "riptide-dashboard": "Updated every 5 minutes: stat cards plus a bankroll history chart.",
    "riptide-held-trades": "Updated when RIPTIDE opens or closes its position.",
    "riptide-winners": "Updated immediately when a RIPTIDE position closes profitably.",
    "riptide-losers": "Updated immediately when a RIPTIDE position closes without a profit.",
    "surge-dashboard": "Updated every 5 minutes: stat cards plus a bankroll history chart.",
    "surge-held-trades": "Updated when SURGE opens or closes its position.",
    "surge-winners": "Updated immediately when a SURGE position closes profitably.",
    "surge-losers": "Updated immediately when a SURGE position closes without a profit.",
    "grok-dashboard": "Updated every 5 minutes: stat cards plus a bankroll history chart.",
    "grok-held-trades": "Updated when GROK opens or closes its position.",
    "grok-winners": "Updated immediately when a GROK position closes profitably.",
    "grok-losers": "Updated immediately when a GROK position closes without a profit.",
    "workflow-log": "Used for releases, deployments, and rollback reports.",
}

GUIDES = {
    "welcome": """# Tradysquids
Tradysquids is a local-first, paper-trading research system for learning how
options setups are found, tracked, and reviewed. No brokerage orders are ever
placed - everything here is paper money.

Independent paper-trader records: BLACKTIDE, RIPTIDE, SURGE, and GROK each have
their own dashboard, held-trades, winners, and losers channels.

Start with #rules-and-risk, then #how-to-use-tradebot.""",
}


def normalized(value: str) -> str:
    return str(value or "").strip().casefold()


def main() -> int:
    load_env()
    apply = "--apply" in sys.argv
    tracker = discord_transport.DiscordTracker(
        os.environ.get("DISCORD_BOT_TOKEN", "").strip(),
        os.environ.get("DISCORD_GUILD_ID", "").strip(),
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
        warnings.append("TradeBot has Administrator; remove it because Administrator includes bans.")
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
                    {"name": name, "type": 4, "position": position},
                )
        if item:
            categories[name] = item
            if apply and bot_role_id:
                try:
                    tracker._request(
                        "PUT",
                        f"/channels/{item['id']}/permissions/{bot_role_id}",
                        {"type": 0, "allow": str(BOT_CHANNEL_ALLOW), "deny": "0"},
                    )
                except discord_transport.DiscordError as exc:
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
                        "parent_id": category["id"] if category else None,
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
                    {"type": 0, "allow": str(BOT_CHANNEL_ALLOW), "deny": "0"},
                )
            except discord_transport.DiscordError as exc:
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
                except discord_transport.DiscordError as exc:
                    warnings.append(f"#{spec.name}: {exc}")

    all_by_name = {
        normalized(item.get("name")): item
        for item in existing
        if item.get("type") != 4
    }
    deleted_ids: list[tuple[str, str]] = []
    for name in sorted(DELETE_CHANNELS):
        item = all_by_name.get(normalized(name))
        if not item:
            continue
        if not apply:
            print(f"WOULD DELETE #{name}")
            continue
        try:
            tracker._request("DELETE", f"/channels/{item['id']}")
            deleted_ids.append((name, str(item["id"])))
        except discord_transport.DiscordError as exc:
            print(f"DELETE FAILED #{name}: {exc}")
            warnings.append(f"delete #{name}: {exc}")

    if apply and deleted_ids:
        try:
            remaining = {
                str(item["id"])
                for item in tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
            }
        except discord_transport.DiscordError as exc:
            remaining = set()
            warnings.append(f"could not verify deletions: {exc}")
        for name, channel_id in deleted_ids:
            if channel_id in remaining:
                print(f"DELETE UNCONFIRMED #{name} - still present after delete")
                warnings.append(f"#{name} still present after delete")
            else:
                print(f"DELETE #{name}")

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
                except discord_transport.DiscordError as exc:
                    warnings.append(f"delete category {category_name}: {exc}")

    print("Discord structure synchronized." if apply else "Dry run complete; no Discord changes made.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
