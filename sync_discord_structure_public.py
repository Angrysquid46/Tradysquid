"""Apply Discord structure, public ticker policy, and cards."""

from __future__ import annotations

import sys

import discord_transport
import sync_discord_structure as sync


def _rebuild_channel_specs() -> list[sync.ChannelSpec]:
    rebuilt: list[sync.ChannelSpec] = []
    inserted_activity = False
    for item in sync.CHANNELS:
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
    if not inserted_activity:
        rebuilt.append(
            sync.ChannelSpec(
                "SYSTEM",
                "system-activity",
                "Always-on interval receipts, off-hours SPY research, event sweeps, and data freshness.",
            )
        )
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
            "Always-on run ledger showing what fired, when it ran, the expected interval, and off-hours SPY research activity."
        ),
        "system-health": (
            "Updated by the supervisor and scheduler heartbeat. A responding process is not considered healthy unless scheduled work is also firing."
        ),
        "automation-diagnostics": (
            "Lists jobs that failed, never fired, became stale, or ran overdue, plus every automatic repair attempt and unresolved retry limit."
        ),
    }
)

sync.GUIDES["how-to-use-tradebot"] = """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.

• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — curated educational answers.
• `/filters` — configuration status; guarded changes remain owner-only.

This system trades SPY exclusively - there is no ticker roster to add,
remove, or manage. Closed-market research continues on its own schedule,
checks events every hour, and opens no position outside regular hours.
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
activity, latest off-hours SPY research, event-sweep freshness, and the next
expected work.

During regular market hours, the options scanner may create paper positions when
all gates pass. Outside regular hours and on weekends, the system continues
research-only stock screening, chart and level refreshes, news and event checks,
learning reviews, reporting, diagnostics, and repairs. No brokerage order is ever
placed by Tradysquids."""

def _tracker() -> discord_transport.DiscordTracker:
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")
    return tracker


def main() -> int:
    apply = "--apply" in sys.argv
    result = sync.main()
    if result:
        return result
    if not apply:
        print("Dry run: structure synchronized above; no live changes made.")
    else:
        print("Discord release complete: structure synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
