"""Install the shared, non-strategy-specific Performance-category scorecard
destinations. Monthly performance and strategy-breakdown scorecards used to
live here too, back when there was only one live strategy - now that SPY
0DTE is split into two independently-tracked live strategies (1-minute and
5-minute), those two report types moved into their own per-strategy
categories (1-MINUTE STRATEGY / 5-MINUTE STRATEGY, channels
1m-performance/1m-results/5m-performance/5m-results) instead of being
recreated here. Daily and weekly recaps stay here deliberately - they're
calendar summaries across BOTH strategies combined, not something the split
duplicated, matching the explicit "we just need 1 of all the trackers"
direction for anything that isn't strategy-specific.
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
