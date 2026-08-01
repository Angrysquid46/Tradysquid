"""Apply Discord structure with public ticker-management policy details."""

from __future__ import annotations

import sync_discord_structure as sync


sync.CHANNELS = [
    (
        sync.ChannelSpec(
            item.category,
            item.name,
            "Public ticker add/remove status plus owner-only filters, pauses, and manual scans."
            if item.name == "scanner-controls"
            else item.topic,
            item.channel_type,
        )
    )
    for item in sync.CHANNELS
]

sync.GUIDES["how-to-use-tradebot"] = """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.
• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/filings`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — educational answers.
• `/ticker-add ticker:` — any member may add a verified optionable ticker.
• `/ticker-remove ticker:` — any member may remove a ticker from new scans.
• `/ticker-list`, `/ticker-status` — show the current universe and capacity.
• `/filters` — show configuration; filter changes and manual scans remain owner-only.

The universe has a hard cap of **25 active tickers**, with no more than **12**
processed in one rotating scan batch. Removal preserves history and keeps any
open paper position tracked until it closes. The hidden supervisor deploys
approved releases, restarts services, synchronizes Discord, and reports failures.
The system is paper-trading only and cannot place brokerage orders."""

sync.GUIDES["how-trades-are-found"] = """# How TradeBot Finds Paper Trades
Nothing is selected randomly. Every position must pass a recorded process.

**1. Universe:** verified optionable symbols come from the baseline list,
member additions, and approved provider discovery. Any member may add or remove
a ticker. The universe is capped at 25 active symbols and scans rotate through
no more than 12 at a time to protect provider usage.
**2. Market context:** trend, momentum, volatility, support/resistance, and
intraday evidence classify the setup. A score ranks candidates; it is not a
probability of profit.
**3. Contract quality:** DTE, strike distance, bid, ask, volume, open interest,
spread width, delta, cost, and modeled maximum risk are checked.
**4. Structure:** directional evidence must match the call, put, or spread.
**5. Lifecycle:** duplicates are blocked, open positions are monitored, and
every close is classified as a win or loss for paper-trade learning.

Removing a ticker blocks new positions but never abandons an existing one.
Quotes, slippage, assignment, exercise, and total-loss risk still require
independent review. Educational only—not financial advice."""

sync.GUIDES["scanner-controls"] = """# Ticker and Scanner Controls
**Available to every member**
• `/ticker-add ticker:` verifies an optionable symbol and adds it if capacity exists.
• `/ticker-remove ticker:` stops new scans while preserving trades and history.
• `/ticker-list` shows active symbols, exclusions, and current usage.
• `/ticker-status ticker:` shows whether one symbol is active.

**Capacity rules**
• Hard maximum: **25 active tickers**.
• Maximum rotating scan batch: **12 tickers**.
• Additions require a live Tradier quote and usable option expirations.
• Removing a ticker never stops an existing paper position from being tracked.

**Owner-only controls**
`/filter-set`, `/ticker-pause`, `/ticker-resume`, and `/scan-now` remain guarded.
The runtime is read-only toward brokerages and cannot place trades."""


if __name__ == "__main__":
    raise SystemExit(sync.main())
