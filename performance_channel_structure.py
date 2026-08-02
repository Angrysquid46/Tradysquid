"""Install the four distinct Performance-category reporting destinations."""

from __future__ import annotations

from typing import Any


PERFORMANCE_CHANNELS = (
    (
        "performance-dashboard",
        "Monthly paper-trade performance using weekly-style summaries plus complete trade history.",
    ),
    (
        "daily-recap",
        "One summary per recorded trading day plus paginated history containing every closed trade.",
    ),
    (
        "weekly-report",
        "One weekly summary plus paginated history containing every closed trade from that week.",
    ),
    (
        "strategy-breakdown",
        "Ranked strategy results plus paginated history containing every closed trade by strategy.",
    ),
)


def install(sync: Any) -> None:
    """Replace the ambiguous consolidated routes with explicit channels."""
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
                "Monthly performance summaries use the weekly layout. Every monthly trade is listed in paginated history cards."
            ),
            "daily-recap": (
                "Every recorded trading day receives a summary and complete paginated closed-trade history."
            ),
            "weekly-report": (
                "Every recorded week receives a summary and complete paginated closed-trade history."
            ),
            "strategy-breakdown": (
                "Every closed trade is grouped by strategy and retained in paginated history cards."
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
    print("Separate Performance report channels validated")
