"""Apply Discord structure, public ticker policy, cards, and complete lessons."""

from __future__ import annotations

import sys

import discord_transport
import strict_learning_order
import sync_discord_cards
import sync_discord_structure as sync
import sync_learning_center
from learning_center_catalog import (
    LEARNING_CHANNEL_ORDER,
    LEGACY_CHANNEL_ALIASES,
    LESSONS,
    ORDERED_CHANNELS,
)


def _learning_specs() -> list[sync.ChannelSpec]:
    specs = [
        sync.ChannelSpec(
            "LEARNING CENTER",
            "learning-index",
            "Numbered stock-and-options curriculum, reading path, and subject map.",
        )
    ]
    specs.extend(
        sync.ChannelSpec("LEARNING CENTER", item.channel, item.topic)
        for item in LESSONS
    )
    specs.extend(
        [
            sync.ChannelSpec(
                "LEARNING CENTER",
                "ask-tradebot",
                "Use /ask and /explain for library-grounded answers with lesson citations.",
            ),
            sync.ChannelSpec(
                "LEARNING CENTER",
                "examples-and-reviews",
                "Evidence-based paper-trade walkthroughs, outcome causes, and learning records.",
            ),
        ]
    )
    return specs


def _rebuild_channel_specs() -> list[sync.ChannelSpec]:
    rebuilt: list[sync.ChannelSpec] = []
    inserted_learning = False
    inserted_activity = False
    inserted_diagnostics = False
    for item in sync.CHANNELS:
        if item.category == "LEARNING CENTER":
            if not inserted_learning:
                rebuilt.extend(_learning_specs())
                inserted_learning = True
            continue
        if item.name == "scanner-controls":
            item = sync.ChannelSpec(
                item.category,
                item.name,
                "Public ticker add/remove status plus owner-only filters, pauses, and manual scans.",
                item.channel_type,
            )
        elif item.name == "upgrade-review":
            item = sync.ChannelSpec(
                item.category,
                item.name,
                "Unanswered TradeBot questions, member suggestions, and curriculum gaps awaiting owner review.",
                item.channel_type,
            )
        rebuilt.append(item)
        if item.name == "universe-watch" and not inserted_activity:
            rebuilt.append(
                sync.ChannelSpec(
                    "SYSTEM",
                    "system-activity",
                    "Always-on interval receipts, off-hours SPY research, event sweeps, and data freshness.",
                )
            )
            inserted_activity = True
        if item.name == "scanner-controls" and not inserted_diagnostics:
            rebuilt.append(
                sync.ChannelSpec(
                    "SYSTEM",
                    "automation-diagnostics",
                    "Missed jobs, overdue intervals, stale runs, automatic repair attempts, retry limits, and unresolved failures.",
                )
            )
            inserted_diagnostics = True
    if not inserted_learning:
        rebuilt.extend(_learning_specs())
    if not inserted_activity:
        rebuilt.append(
            sync.ChannelSpec(
                "SYSTEM",
                "system-activity",
                "Always-on interval receipts, off-hours SPY research, event sweeps, and data freshness.",
            )
        )
    if not inserted_diagnostics:
        rebuilt.append(
            sync.ChannelSpec(
                "SYSTEM",
                "automation-diagnostics",
                "Missed jobs, overdue intervals, stale runs, automatic repair attempts, retry limits, and unresolved failures.",
            )
        )
    return rebuilt


sync.CHANNELS = _rebuild_channel_specs()
sync.CHANNEL_STARTERS.update(
    {
        "scanner-feed": (
            "Live options scans run during regular market hours. When markets are closed, "
            "a research-only SPY screen updates this channel without opening positions."
        ),
        "universe-watch": (
            "Shows the latest SPY off-hours screen and on-demand snapshot."
        ),
        "news-and-events": (
            "News and event sweeps continue during market hours, evenings, overnight periods, and weekends."
        ),
        "system-activity": (
            "Always-on run ledger showing what fired, when it ran, the expected interval, the current universe batch, and off-hours research activity."
        ),
        "system-health": (
            "Updated by the supervisor and scheduler heartbeat. A responding process is not considered healthy unless scheduled work is also firing."
        ),
        "automation-diagnostics": (
            "Lists jobs that failed, never fired, became stale, or ran overdue, plus every automatic repair attempt and unresolved retry limit."
        ),
        "upgrade-review": (
            "Unanswered `/ask` questions are deduplicated here with closest lesson matches, "
            "ask counts, and the information needed to expand TradeBot safely."
        ),
    }
)

# Long-form cards own every numbered lesson. Remove old single-message guides
# and aliases so the base synchronizer cannot recreate duplicate beginner tabs.
for lesson_channel in set(ORDERED_CHANNELS) | set(LEGACY_CHANNEL_ALIASES) | set(LEGACY_CHANNEL_ALIASES.values()):
    sync.GUIDES.pop(lesson_channel, None)

sync.GUIDES["learning-index"] = """# Complete Trading Learning Center
Read the numbered channels in order or jump to the exact subject you need.

**Stocks and business**
01 foundations → 02 fundamentals → 03 statements → 04 valuation

**Trading mechanics and analysis**
05 orders → 06 price action → 07 indicators → 08 volume/breadth →
09 macro/sectors → 10 stock strategies → 11 shorting/margin → 12 portfolio risk

**Options**
13 foundations → 14 chains/liquidity → 15 pricing/Greeks → 16 volatility →
17 directional strategies → 18 income/hedging → 19 multi-leg spreads

**Execution and improvement**
20 planning/management → 21 expiration/assignment → 22 events/actions →
23 psychology/journaling → 24 testing/statistics → 25 accounts/taxes →
26 research/data → 27 scams/security

Every topic contains detailed cards, examples, formulas, failure modes,
checklists, and review questions. `/ask` and `/explain` search the same library
and cite the exact channel and section used. Educational information only."""

sync.GUIDES["how-to-use-tradebot"] = """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.

• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — detailed answers grounded in Learning Center lessons.
• Ask `/ask` to **apply** a lesson to `$TICKER` for a read-only walkthrough.
• Unanswered questions are saved and posted to #upgrade-review for expansion.
• `/ticker-add`, `/ticker-remove` — public capped universe management.
• `/ticker-list`, `/ticker-status` — current universe and capacity.
• `/filters` — configuration status; guarded changes remain owner-only.

The universe is capped at **25 active tickers**. Market-hours scans rotate through
up to **12** symbols per pass. Closed-market research rotates through smaller
batches every 30 minutes, checks events every hour, and opens no position.
#system-activity proves what ran. #automation-diagnostics shows missed intervals
and repair attempts. All output uses readable cards. Paper trading only; no
brokerage orders are placed."""

sync.GUIDES["how-trades-are-found"] = """# How TradeBot Finds Paper Trades
Nothing is selected randomly. SPY 0DTE is the only strategy family this system
trades, split into two independently-tracked live strategies that run at the
same time and never share a position - #1-minute-strategy and
#5-minute-strategy. They differ in exactly one thing: how often the bot checks
SPY's price to read the opening range and the breakout. Everything else below
is identical for both.

**1. Establish the opening range**
The bot watches SPY's first 30 minutes of trading and records the high/low of
that range from its own bar interval (1-minute or 5-minute). Nothing opens
before the range is established.

**2. Wait for a real breakout**
The first bar to close outside the opening range fires the signal - above for
bullish, below for bearish. A signal fires once per session, at the first
breach, not on every bar that stays outside the range.

**3. Choose an eligible contract**
Same-day (0DTE) expiration only. Absolute delta must be 0.40-0.60 and the
contract must cost $5.00 or less per share ($500 or less per contract). Both
strategies use the same delta band and the same $500-per-trade risk cap - each
one independently, so both can hold a position on the same underlying move at
once.

**4. Manage the position**
Target +50% / stop -50%. Once a trade peaks past +30% profit, the stop raises
ONCE to -15% and holds there - it does not keep trailing behind every tick.
Every position force-closes at end of day; 0DTE never holds overnight.

**Lifecycle:** duplicates are blocked per strategy, positions are monitored,
and every close receives a trade-specific review separating exit trigger from
probable cause. Cause tags feed the review-first learning archive, grouped by
strategy so the two are compared honestly; filters never change without
adequate evidence and owner approval."""

sync.GUIDES["scanner-controls"] = """# Ticker and Scanner Controls
**Every member:** `/ticker-add`, `/ticker-remove`, `/ticker-list`, `/ticker-status`.

**Capacity:** 25 active tickers; 12 per live scan rotation. Additions require a
live Tradier quote and usable option expirations. Removal stops new scans but
never abandons an existing paper position or erases history.

**Always-on behavior:** the market-hours options scanner pauses when trading is
closed, but rotating stock research, event checks, outcome learning, Discord
reporting, diagnostics, and repair monitoring continue automatically.

**Owner-only:** filter changes, pauses, resumes, and full manual scans."""

sync.GUIDES["automation-diagnostics"] = """# Automation Diagnostics and Self-Repair
This owner-control channel is the scheduler's fault ledger.

It records every expected job, its configured interval, last receipt, current
state, and whether it is healthy, running, intentionally paused, overdue, stale,
never started, interrupted, or failed. A process listening on a port is not
enough; the scheduler must keep writing a fresh heartbeat and interval receipts.

When a safe job fails or becomes overdue, the repair worker starts it again,
records the trigger and result, and verifies that a later successful job receipt
exists. Market-hours trading jobs are never forced to run while the market is
closed. Repeated failures remain visible after the retry limit rather than being
painted green and forgotten."""

sync.GUIDES["system-activity"] = """# Always-On Activity Ledger
This channel should never look abandoned merely because the exchange is closed.
It refreshes every few minutes with scheduler receipts, market state, service
activity, universe capacity, latest live-scan rotation, latest off-hours research
batch, event-sweep freshness, and the next expected work.

During regular market hours, the options scanner may create paper positions when
all gates pass. Outside regular hours and on weekends, the system continues
research-only stock screening, chart and level refreshes, news and event checks,
learning reviews, reporting, diagnostics, and repairs. No brokerage order is ever
placed by Tradysquids."""

sync.GUIDES["upgrade-review"] = """# Learning and Upgrade Review Queue
This owner-control channel receives unanswered TradeBot questions and member
suggestions that need deliberate review.

Each unanswered-question card includes the exact wording, member, first and last
seen time, repeat count, closest existing lesson matches, and a stable question
ID. Repeated wording updates the same card instead of posting duplicates.

To improve an answer, expand the correct Learning Center lesson, add relevant
aliases and examples, then add the real question wording to the focused tests.
TradeBot never invents an answer merely to avoid creating a review item."""


def _tracker() -> discord_transport.DiscordTracker:
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")
    return tracker


def main() -> int:
    apply = "--apply" in sys.argv
    tracker: discord_transport.DiscordTracker | None = None
    renamed = 0

    if apply:
        tracker = _tracker()
        renamed = sync_discord_cards.migrate_legacy_learning_channels(tracker)

    result = sync.main()
    if result:
        return result

    if not apply:
        counts = sync_learning_center.validate_curriculum()
        if tuple(counts) != ORDERED_CHANNELS:
            raise RuntimeError("Dry-run curriculum order does not match the catalog.")
        print(
            "Dry run: comprehensive Learning Center would synchronize "
            f"{len(counts)} channels and {sum(counts.values())} lesson cards in "
            f"{len(LEARNING_CHANNEL_ORDER)} ordered Learning Center channels."
        )
        return 0

    tracker = tracker or _tracker()
    removed = sync_discord_cards.cleanup_duplicate_learning_channels(tracker)
    channel_map = sync_discord_cards.write_learning_channel_map(tracker)
    totals = sync_learning_center.synchronize_curriculum(tracker)

    order_result = strict_learning_order.enforce_learning_channel_order(tracker)
    migration_pid = sync_discord_cards.launch_background_migration()
    print(
        "Discord release complete: "
        f"always-on activity and automation diagnostics channels synchronized; "
        f"{renamed} legacy learning channels renamed; {removed} duplicates removed; "
        f"{order_result['canonical']} canonical learning channels strictly ordered in "
        f"{order_result['attempts']} attempt(s); {order_result['extras']} extra "
        f"channels moved after the curriculum; {len(channel_map)} references mapped; "
        f"{totals['cards']} lesson cards synchronized; historical card migration "
        f"started as PID {migration_pid}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
