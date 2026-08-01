"""Apply Discord structure, public ticker policy, cards, and full lessons."""

from __future__ import annotations

import sys

import ford_scan
import sync_discord_cards
import sync_discord_structure as sync
import sync_learning_center


def _channel_spec(item: sync.ChannelSpec) -> sync.ChannelSpec:
    if item.name == "01-market-basics":
        return sync.ChannelSpec(
            item.category,
            "01-stock-basics",
            "Stocks, ETFs, indexes, market mechanics, orders, liquidity, and corporate actions.",
            item.channel_type,
        )
    if item.name == "scanner-controls":
        return sync.ChannelSpec(
            item.category,
            item.name,
            "Public ticker add/remove status plus owner-only filters, pauses, and manual scans.",
            item.channel_type,
        )
    return item


sync.CHANNELS = [_channel_spec(item) for item in sync.CHANNELS]

# Numbered channels are synchronized as long-form embed cards. Remove the old
# one-message versions so users see one organized lesson, not duplicate debris.
for lesson_channel in set(sync_learning_center.load_lessons()) | {"01-market-basics"}:
    sync.GUIDES.pop(lesson_channel, None)

sync.GUIDES["learning-index"] = """# Complete Learning Center
Use the numbered channels in order or jump directly to the subject you need.

**Foundations**
#01-stock-basics → #02-options-basics → #03-option-chain

**Pricing and analysis**
#04-pricing-and-greeks → #05-volatility → #06-charts → #07-technical-analysis

**Structures and risk**
#08-strategies → #09-spreads → #10-risk-management → #11-trade-management

**Lifecycle and improvement**
#12-expiration-assignment → #13-events-and-catalysts →
#14-psychology-journaling → #15-backtesting-stats

**Real-world protection**
#16-taxes-and-rules → #17-scams-and-myths

Every lesson is presented as readable cards with examples, calculations,
mistakes, checklists, and practical application. Use `/ask` and `/explain`
for definitions. Educational information only—not financial advice."""

sync.GUIDES["how-to-use-tradebot"] = """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.

• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/filings`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — educational answers.
• `/ticker-add ticker:` — any member may add a verified optionable ticker.
• `/ticker-remove ticker:` — any member may remove a ticker from new scans.
• `/ticker-list`, `/ticker-status` — show current universe and capacity.
• `/filters` — show configuration; guarded changes remain owner-only.

The universe has a hard cap of **25 active tickers**, with no more than **12**
processed in one rotating scan batch. Removal preserves history and keeps any
open paper position tracked until it closes. All TradeBot output uses readable
Discord cards. The system is paper-trading only and cannot place orders."""

sync.GUIDES["how-trades-are-found"] = """# How TradeBot Finds Paper Trades
Nothing is selected randomly. Every paper position must pass a recorded process.

**1. Universe**
Verified optionable symbols come from the baseline list, member additions, and
approved provider discovery. The universe is capped at 25 active symbols and
rotates through no more than 12 per scan.

**2. Market context**
Trend, momentum, volatility, support/resistance, VWAP, and intraday evidence
classify the setup. A score ranks candidates; it is not a win probability.

**3. Contract quality**
DTE, strike distance, bid, ask, volume, open interest, spread width, delta,
cost, and modeled maximum risk are checked.

**4. Structure and lifecycle**
Directional evidence must match the call, put, or spread. Duplicates are
blocked, positions are monitored, and every close receives a trade-specific
win/loss review with learning cause tags. Removing a ticker never abandons an
open position."""

sync.GUIDES["scanner-controls"] = """# Ticker and Scanner Controls
**Available to every member**
• `/ticker-add ticker:` verifies and adds an optionable symbol if space exists.
• `/ticker-remove ticker:` stops new scans while preserving history.
• `/ticker-list` shows active symbols and remaining capacity.
• `/ticker-status ticker:` shows whether one symbol is active.

**Capacity**
• Hard maximum: **25 active tickers**
• Rotating scan batch: **12 tickers**
• Additions require a Tradier quote and usable option expirations
• Removal never stops tracking an existing paper position

**Owner-only**
Filter changes, pauses, resumes, and full manual scans remain guarded."""


def main() -> int:
    result = sync.main()
    if result:
        return result

    if "--apply" not in sys.argv:
        counts = sync_learning_center.validate_curriculum()
        print(
            "Dry run: card-backed Learning Center would synchronize "
            f"{len(counts)} channels and {sum(counts.values())} lesson cards."
        )
        return 0

    tracker = ford_scan.DiscordTracker(
        ford_scan.DISCORD_BOT_TOKEN,
        ford_scan.DISCORD_GUILD_ID,
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")

    removed = sync_discord_cards.cleanup_duplicate_learning_channels(tracker)
    sync_learning_center.synchronize_curriculum(tracker)
    migration_pid = sync_discord_cards.launch_background_migration()
    print(
        "Discord presentation cleanup complete: "
        f"{removed} duplicate channels removed; "
        f"historical card migration started as PID {migration_pid}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
