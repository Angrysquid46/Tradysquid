from __future__ import annotations

from typing import Any

CANONICAL_CATEGORY_ORDER = (
    "START HERE",
    "COMMUNITY",
    "LIVE TRADING DESK",
    "MARKET INTELLIGENCE",
    "LEARNING CENTER",
    "PERFORMANCE",
    "SYSTEM",
    "STRATEGY CONTROL",
    "OWNER CONTROL",
)

INVENTED_CATEGORIES = frozenset(
    {
        "SCANNING",
        "PAPER TRADING",
        "LEARNING CENTER 2",
    }
)

ORIGINAL_LEARNING_CHANNELS = (
    "01-stock-market-foundations",
    "02-company-fundamentals",
    "03-financial-statements",
    "04-valuation-and-quality",
    "05-market-mechanics-orders",
    "06-charts-price-action",
    "07-technical-analysis",
    "08-volume-breadth-internals",
    "09-macro-sectors-catalysts",
    "10-stock-trading-strategies",
    "11-short-selling-margin",
    "12-portfolio-risk",
    "13-options-basics",
    "14-option-chain-liquidity",
    "15-option-pricing-greeks",
    "16-volatility",
    "17-directional-options",
    "18-income-and-hedging",
    "19-spreads-multi-leg",
    "20-trade-planning-execution",
    "21-expiration-assignment",
    "22-events-corporate-actions",
    "23-psychology-journaling",
    "24-backtesting-statistics",
    "25-brokers-accounts-taxes",
    "26-research-data-tools",
    "27-scams-security-myths",
)

ORIGINAL_CHANNELS: dict[str, tuple[str, ...]] = {
    "START HERE": (
        "welcome",
        "rules-and-risk",
        "how-to-use-tradebot",
        "how-trades-are-found",
    ),
    "COMMUNITY": ("general-chat",),
    "LIVE TRADING DESK": (
        "scanner-feed",
        "new-positions",
        "held-positions",
        "wins",
        "losses",
        "trade-journal",
    ),
    "MARKET INTELLIGENCE": (
        "premarket",
        "breaking-alerts",
        "charts-and-levels",
        "news-and-events",
        "market-regime",
        "universe-watch",
    ),
    "LEARNING CENTER": (
        "learning-index",
        *ORIGINAL_LEARNING_CHANNELS,
        "learning-search",
        "ask-tradebot",
        "examples-and-reviews",
    ),
    "PERFORMANCE": (
        "performance-dashboard",
        "strategy-results",
        "regular-calls",
        "regular-puts",
        "swing-calls",
        "swing-puts",
        "bull-put-spreads",
        "bear-call-spreads",
        "ticker-results",
        "learning-results",
    ),
    "SYSTEM": (
        "scanner-status",
        "api-errors",
        "system-health",
        "system-activity",
        "diagnostics",
        "update-status",
        "provider-status",
    ),
    "STRATEGY CONTROL": (
        "strategy-control",
        "strategy-settings",
        "strategy-versions",
        "trade-overrides",
        "strategy-change-log",
        "strategy-recommendations",
    ),
    "OWNER CONTROL": (
        "owner-controls",
        "scanner-controls",
        "workflow-log",
        "upgrade-requests",
        "upgrade-review",
        "security-log",
        "automation-diagnostics",
        "applied-upgrades",
        "admin-notes",
    ),
}


def _route(
    category: str,
    channel: str,
    *,
    mandatory: bool = False,
    owner_only: bool = False,
) -> dict[str, Any]:
    return {
        "category": category,
        "channel": channel,
        "mandatory": mandatory,
        "owner_only": owner_only,
    }


CARD_ROUTES: dict[str, dict[str, Any]] = {
    "system-health": _route("SYSTEM", "system-health", mandatory=True),
    "system-activity": _route("SYSTEM", "system-activity"),
    "diagnostics": _route("SYSTEM", "diagnostics"),
    "update-status": _route("SYSTEM", "update-status"),
    "provider-status": _route("SYSTEM", "provider-status", mandatory=True),
    "scanner-status": _route("SYSTEM", "scanner-status"),
    "api-errors": _route("SYSTEM", "api-errors"),
    "active-universe": _route(
        "MARKET INTELLIGENCE", "universe-watch", mandatory=True
    ),
    "market-regime": _route(
        "MARKET INTELLIGENCE", "market-regime", mandatory=True
    ),
    "session-preparation": _route("MARKET INTELLIGENCE", "premarket"),
    "breaking-events": _route("MARKET INTELLIGENCE", "breaking-alerts"),
    "ticker-intelligence": _route("MARKET INTELLIGENCE", "news-and-events"),
    "charts-and-levels": _route("MARKET INTELLIGENCE", "charts-and-levels"),
    "latest-scan": _route(
        "LIVE TRADING DESK", "scanner-feed", mandatory=True
    ),
    "accepted-candidates": _route("LIVE TRADING DESK", "scanner-feed"),
    "rejected-candidates": _route("LIVE TRADING DESK", "scanner-feed"),
    "new-positions": _route("LIVE TRADING DESK", "new-positions"),
    "open-positions": _route(
        "LIVE TRADING DESK", "held-positions", mandatory=True
    ),
    "recent-lifecycle-events": _route(
        "LIVE TRADING DESK", "held-positions"
    ),
    "wins": _route("LIVE TRADING DESK", "wins"),
    "losses": _route("LIVE TRADING DESK", "losses"),
    "daily-recap": _route(
        "PERFORMANCE", "performance-dashboard", mandatory=True
    ),
    "weekly-report": _route("PERFORMANCE", "performance-dashboard"),
    "monthly-dashboard": _route("PERFORMANCE", "performance-dashboard"),
    "ticker-results": _route("PERFORMANCE", "ticker-results"),
    "strategy-breakdown": _route(
        "PERFORMANCE", "strategy-results", mandatory=True
    ),
    "regular-call": _route("PERFORMANCE", "regular-calls"),
    "regular-put": _route("PERFORMANCE", "regular-puts"),
    "swing-call": _route("PERFORMANCE", "swing-calls"),
    "swing-put": _route("PERFORMANCE", "swing-puts"),
    "bull-put-spread": _route("PERFORMANCE", "bull-put-spreads"),
    "bear-call-spread": _route("PERFORMANCE", "bear-call-spreads"),
    "learning-results": _route(
        "PERFORMANCE", "learning-results", mandatory=True
    ),
    "strategy-control": _route(
        "STRATEGY CONTROL", "strategy-control", mandatory=True, owner_only=True
    ),
    "strategy-settings": _route(
        "STRATEGY CONTROL", "strategy-settings", owner_only=True
    ),
    "strategy-versions": _route(
        "STRATEGY CONTROL", "strategy-versions", owner_only=True
    ),
    "trade-overrides": _route(
        "STRATEGY CONTROL", "trade-overrides", owner_only=True
    ),
    "strategy-change-log": _route(
        "STRATEGY CONTROL", "strategy-change-log", owner_only=True
    ),
    "strategy-recommendations": _route(
        "STRATEGY CONTROL", "strategy-recommendations", owner_only=True
    ),
    "owner-controls": _route(
        "OWNER CONTROL", "owner-controls", mandatory=True, owner_only=True
    ),
    "scanner-controls": _route(
        "OWNER CONTROL", "scanner-controls", owner_only=True
    ),
    "workflow-log": _route("OWNER CONTROL", "workflow-log", owner_only=True),
    "upgrade-requests": _route(
        "OWNER CONTROL", "upgrade-requests", owner_only=True
    ),
    "upgrade-review": _route(
        "OWNER CONTROL", "upgrade-review", owner_only=True
    ),
    "security-log": _route("OWNER CONTROL", "security-log", owner_only=True),
    "automation-diagnostics": _route(
        "OWNER CONTROL", "automation-diagnostics", owner_only=True
    ),
    "applied-upgrades": _route(
        "OWNER CONTROL", "applied-upgrades", owner_only=True
    ),
    "admin-notes": _route("OWNER CONTROL", "admin-notes", owner_only=True),
}

CARD_TITLES = {
    stable_id: stable_id.replace("-", " ").title() for stable_id in CARD_ROUTES
}
CARD_TITLES.update(
    {
        "api-errors": "API and Provider Errors",
        "active-universe": "Active Universe",
        "session-preparation": "Session Preparation",
        "breaking-events": "Breaking Alerts",
        "ticker-intelligence": "Ticker News and Events",
        "charts-and-levels": "Charts and Levels",
        "latest-scan": "Latest Scan",
        "recent-lifecycle-events": "Position Lifecycle",
        "daily-recap": "Daily Performance",
        "weekly-report": "Weekly Performance",
        "monthly-dashboard": "Monthly Performance",
        "strategy-breakdown": "Strategy Results",
        "learning-results": "Learning Results",
        "strategy-control": "Strategy Control",
        "trade-overrides": "Trade Overrides",
        "strategy-change-log": "Strategy Change Log",
        "owner-controls": "Owner Control Center",
        "scanner-controls": "Scanner and Universe Controls",
        "upgrade-requests": "Upgrade Requests",
        "upgrade-review": "Upgrade Review",
        "security-log": "Security Log",
        "automation-diagnostics": "Automation Diagnostics",
        "applied-upgrades": "Applied Upgrades",
        "admin-notes": "Admin Notes",
    }
)

LESSON_ROUTES: dict[str, str] = {
    channel: channel for channel in ORIGINAL_LEARNING_CHANNELS
}
LESSON_ROUTES.update(
    {
        "01-market-foundations": "01-stock-market-foundations",
        "02-instrument-identification": "01-stock-market-foundations",
        "03-market-sessions": "05-market-mechanics-orders",
        "04-underlying-liquidity": "05-market-mechanics-orders",
        "05-chart-structure": "06-charts-price-action",
        "06-price-action": "06-charts-price-action",
        "07-technical-indicators": "07-technical-analysis",
        "08-trend": "06-charts-price-action",
        "09-momentum": "07-technical-analysis",
        "10-support-resistance": "06-charts-price-action",
        "11-volatility": "16-volatility",
        "12-market-regimes": "09-macro-sectors-catalysts",
        "13-options-foundations": "13-options-basics",
        "14-option-chains": "14-option-chain-liquidity",
        "15-contract-liquidity": "14-option-chain-liquidity",
        "16-bid-ask-behavior": "05-market-mechanics-orders",
        "17-option-pricing": "15-option-pricing-greeks",
        "18-greeks": "15-option-pricing-greeks",
        "19-implied-volatility": "16-volatility",
        "20-directional-long-options": "17-directional-options",
        "21-defined-risk-spreads": "19-spreads-multi-leg",
        "22-position-sizing": "12-portfolio-risk",
        "23-risk-limits": "12-portfolio-risk",
        "24-trade-planning": "20-trade-planning-execution",
        "25-execution-assumptions": "20-trade-planning-execution",
        "26-journaling": "23-psychology-journaling",
        "27-backtesting-review": "24-backtesting-statistics",
    }
)

CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "scanner-feed": (
        "scan-results",
        "accepted-candidates",
        "rejected-candidates",
    ),
    "new-positions": ("accepted-candidates",),
    "held-positions": ("open-positions", "lifecycle-events"),
    "universe-watch": ("active-universe",),
    "premarket": ("session-preparation",),
    "breaking-alerts": ("breaking-events",),
    "news-and-events": ("ticker-intelligence",),
    "performance-dashboard": (
        "daily-recap",
        "weekly-report",
        "monthly-dashboard",
    ),
    "strategy-results": ("strategy-breakdown",),
    "scanner-controls": (),
    "workflow-log": (),
    "upgrade-requests": (),
    "upgrade-review": (),
    "security-log": (),
    "automation-diagnostics": (),
    "applied-upgrades": (),
    "admin-notes": (),
    "owner-controls": (),
    "api-errors": (),
    "strategy-control": (),
    "strategy-settings": (),
    "strategy-versions": (),
    "strategy-recommendations": (),
    "trade-overrides": (),
    "strategy-change-log": (),
    "trade-journal": (),
    "system-health": (),
    "system-activity": (),
    "diagnostics": (),
    "update-status": (),
    "provider-status": (),
}

for lesson_id, original_channel in LESSON_ROUTES.items():
    if lesson_id == original_channel:
        continue
    existing = list(CHANNEL_ALIASES.get(original_channel, ()))
    if lesson_id not in existing:
        existing.append(lesson_id)
    CHANNEL_ALIASES[original_channel] = tuple(existing)

ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.casefold(): canonical
    for canonical, aliases in CHANNEL_ALIASES.items()
    for alias in aliases
}

MIGRATION_CHANNEL_NAMES = frozenset(ALIAS_TO_CANONICAL)


def route_for(stable_id: str) -> dict[str, Any]:
    route = CARD_ROUTES[stable_id]
    return {
        "stable_id": stable_id,
        "category": route["category"],
        "channel": route["channel"],
        "mandatory": bool(route.get("mandatory", False)),
        "owner_only": bool(route.get("owner_only", False)),
        "updates_in_place": True,
    }
