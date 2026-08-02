"""Install the four distinct Performance-category scorecard destinations."""

from __future__ import annotations

from typing import Any


PERFORMANCE_CHANNELS = (
    (
        "performance-dashboard",
        "One updating monthly scorecard per calendar month; trade detail remains in the journal.",
    ),
    (
        "daily-recap",
        "One updating scorecard per trading day with wins, losses, P/L, expectancy, and best/worst.",
    ),
    (
        "weekly-report",
        "One updating scorecard per trading week; a new card begins with each new trading week.",
    ),
    (
        "strategy-breakdown",
        "One updating scorecard for each play type: regular, swing, and spread calls and puts.",
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
            "performance-dashboard": (
                "Monthly scoreboard only: one updating summary card per calendar month. Trade details remain in #trade-journal."
            ),
            "daily-recap": (
                "Daily scoreboard only: one updating summary card per recorded trading day."
            ),
            "weekly-report": (
                "Weekly scoreboard only: one updating card for the active trading week, followed by a new card next week."
            ),
            "strategy-breakdown": (
                "One updating scorecard per play type. No duplicated trade-history pages are posted here."
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
