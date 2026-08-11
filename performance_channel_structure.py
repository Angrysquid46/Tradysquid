"""Install the shared, non-strategy-specific Performance-category scorecard
destinations. Per-strategy monthly performance and strategy-breakdown
scorecards live in their own per-strategy categories (1-MINUTE STRATEGY /
5-MINUTE STRATEGY / etc, channels <slug>-performance/<slug>-results)
instead of being recreated here. Daily, weekly, and monthly recaps stay
here deliberately - they're calendar summaries across every live strategy
combined, not something a per-strategy split duplicated, matching the
explicit "we just need 1 of all the trackers" direction for anything that
isn't strategy-specific. Monthly wired up 2026-08-11: #monthly-dashboard
already existed as a real Discord channel but nothing in the deployed code
ever posted to it - daily and weekly both had a combined-across-everything
channel, monthly only existed broken out per strategy inside each
strategy's own channel. This closes that gap using the channel name that
was already there rather than creating a new, separate one.
"""

from __future__ import annotations

from typing import Any


PERFORMANCE_CHANNELS = (
    (
        "daily-recap",
        "One updating scorecard per trading day with wins, losses, P/L, expectancy, and best/worst.",
    ),
    (
        "weekly-report",
        "One updating scorecard per trading week; a new card begins with each new trading week.",
    ),
    (
        "monthly-dashboard",
        "One updating scorecard per trading month, combined across every live strategy - P/L, wins, losses, expectancy.",
    ),
)


def install(sync: Any) -> None:
    """Replace ambiguous consolidated routes with explicit scorecard channels."""
    required_names = {name for name, _ in PERFORMANCE_CHANNELS}
    rebuilt = []
    inserted = False
    for spec in sync.CHANNELS:
        if spec.category == "PERFORMANCE" and spec.name in required_names:
            continue
        if spec.category == "PERFORMANCE" and not inserted:
            rebuilt.extend(
                sync.ChannelSpec("PERFORMANCE", name, topic)
                for name, topic in PERFORMANCE_CHANNELS
            )
            inserted = True
        rebuilt.append(spec)
    if not inserted:
        rebuilt.extend(
            sync.ChannelSpec("PERFORMANCE", name, topic)
            for name, topic in PERFORMANCE_CHANNELS
        )
    sync.CHANNELS = rebuilt
    sync.CHANNEL_STARTERS.update(
        {
            "daily-recap": (
                "Daily scoreboard only: one updating summary card per recorded trading day."
            ),
            "weekly-report": (
                "Weekly scoreboard only: one updating card for the active trading week, followed by a new card next week."
            ),
            "monthly-dashboard": (
                "Monthly scoreboard only: one updating card for the active trading month, combined across every live strategy."
            ),
        }
    )


def validate(sync: Any) -> None:
    install(sync)
    names = [spec.name for spec in sync.CHANNELS if spec.category == "PERFORMANCE"]
    for name, _ in PERFORMANCE_CHANNELS:
        if names.count(name) != 1:
            raise RuntimeError(f"Performance channel structure invalid for {name}: {names.count(name)}")


if __name__ == "__main__":
    import sync_discord_structure as sync

    validate(sync)
    print("Separate Performance scorecard channels validated")
