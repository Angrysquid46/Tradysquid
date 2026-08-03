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
    "OWNER CONTROL",
)

INVENTED_CATEGORIES = frozenset(
    {
        "SCANNING",
        "PAPER TRADING",
        "STRATEGY CONTROL",
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
        "strategy-settings",
        "strategy-versions",
        "trade-overrides",
        "strategy-change-log",
        "strategy-recommendations",
    ),
}

CARD_ROUTES: dict[str, dict[str, Any]] = {
    "system-health": {"category": "SYSTEM", "channel": "system-health", "mandatory": True},
    "system-activity": {"category": "SYSTEM", "channel": "system-activity", "mandatory": False},
    "diagnostics": {"category": "SYSTEM", "channel": "diagnostics", "mandatory": False},
    "update-status": {"category": "SYSTEM", "channel": "update-status", "mandatory": False},
    "provider-status": {"category": "SYSTEM", "channel": "provider-status", "mandatory": True},
    "scanner-status": {"category": "SYSTEM", "channel": "scanner-status", "mandatory": False},
    "active-universe": {"category": "MARKET INTELLIGENCE", "channel": "universe-watch", "mandatory": True},
    "market-regime": {"category": "MARKET INTELLIGENCE", "channel": "market-regime", "mandatory": True},
    "latest-scan": {"category": "LIVE TRADING DESK", "channel": "scanner-feed", "mandatory": True},
    "accepted-candidates": {"category": "LIVE TRADING DESK", "channel": "scanner-feed", "mandatory": False},
    "rejected-candidates": {"category": "LIVE TRADING DESK", "channel": "scanner-feed", "mandatory": False},
    "shadow-candidates": {"category": "LIVE TRADING DESK", "channel": "scanner-feed", "mandatory": False},
    "new-positions": {"category": "LIVE TRADING DESK", "channel": "new-positions", "mandatory": False},
    "open-positions": {"category": "LIVE TRADING DESK", "channel": "held-positions", "mandatory": True},
    "recent-lifecycle-events": {"category": "LIVE TRADING DESK", "channel": "held-positions", "mandatory": False},
    "wins": {"category": "LIVE TRADING DESK", "channel": "wins", "mandatory": False},
    "losses": {"category": "LIVE TRADING DESK", "channel": "losses", "mandatory": False},
    "daily-recap": {"category": "PERFORMANCE", "channel": "performance-dashboard", "mandatory": True},
    "weekly-report": {"category": "PERFORMANCE", "channel": "performance-dashboard", "mandatory": False},
    "monthly-dashboard": {"category": "PERFORMANCE", "channel": "performance-dashboard", "mandatory": False},
    "ticker-results": {"category": "PERFORMANCE", "channel": "ticker-results", "mandatory": False},
    "strategy-breakdown": {"category": "PERFORMANCE", "channel": "strategy-results", "mandatory": True},
    "regular-call": {"category": "PERFORMANCE", "channel": "regular-calls", "mandatory": False},
    "regular-put": {"category": "PERFORMANCE", "channel": "regular-puts", "mandatory": False},
    "swing-call": {"category": "PERFORMANCE", "channel": "swing-calls", "mandatory": False},
    "swing-put": {"category": "PERFORMANCE", "channel": "swing-puts", "mandatory": False},
    "bull-put-spread": {"category": "PERFORMANCE", "channel": "bull-put-spreads", "mandatory": False},
    "bear-call-spread": {"category": "PERFORMANCE", "channel": "bear-call-spreads", "mandatory": False},
    "learning-results": {"category": "PERFORMANCE", "channel": "learning-results", "mandatory": True},
    "strategy-control": {"category": "OWNER CONTROL", "channel": "scanner-controls", "mandatory": True, "owner_only": True},
    "strategy-settings": {"category": "OWNER CONTROL", "channel": "strategy-settings", "mandatory": False, "owner_only": True},
    "strategy-versions": {"category": "OWNER CONTROL", "channel": "strategy-versions", "mandatory": False, "owner_only": True},
    "strategy-recommendations": {"category": "OWNER CONTROL", "channel": "strategy-recommendations", "mandatory": False, "owner_only": True},
}

LESSON_ROUTES: dict[str, str] = {
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

CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "scanner-feed": ("scan-results", "accepted-candidates", "rejected-candidates", "shadow-candidates"),
    "new-positions": ("accepted-candidates",),
    "held-positions": ("open-positions", "lifecycle-events"),
    "universe-watch": ("active-universe",),
    "premarket": ("session-preparation",),
    "breaking-alerts": ("breaking-events",),
    "news-and-events": ("ticker-intelligence",),
    "performance-dashboard": ("daily-recap", "weekly-report", "monthly-dashboard"),
    "strategy-results": ("strategy-breakdown",),
    "scanner-controls": ("strategy-control",),
    "strategy-settings": (),
    "strategy-versions": (),
    "strategy-recommendations": (),
    "trade-journal": (),
    "system-health": (),
    "system-activity": (),
    "diagnostics": (),
    "update-status": (),
    "provider-status": (),
}

for lesson_id, original_channel in LESSON_ROUTES.items():
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
