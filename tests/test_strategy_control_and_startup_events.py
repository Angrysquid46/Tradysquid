from __future__ import annotations

from pathlib import Path

from tradysquid.core.config import AppConfig
from tradysquid.discord.layout import CARD_ROUTES, ORIGINAL_CHANNELS
from tradysquid.discord.publishing import DiscordPublishingService
from tradysquid.learning.center import LearningCenter


ROOT = Path(__file__).resolve().parents[1]


class EmptyDatabase:
    def query(self, sql: str, parameters=()):
        return []

    def execute(self, sql: str, parameters=()):
        return None


def test_every_strategy_control_channel_has_a_persistent_route() -> None:
    routed = {
        route["channel"]
        for route in CARD_ROUTES.values()
        if route["category"] == "STRATEGY CONTROL"
    }
    assert routed == set(ORIGINAL_CHANNELS["STRATEGY CONTROL"])
    assert all(
        route["owner_only"]
        for route in CARD_ROUTES.values()
        if route["category"] == "STRATEGY CONTROL"
    )


def test_scan_event_is_retained_until_discord_publishing_is_ready(tmp_path: Path) -> None:
    config = AppConfig.load(ROOT)
    publisher = DiscordPublishingService(
        EmptyDatabase(),
        tmp_path,
        LearningCenter(config.learning_center),
        {},
    )

    publisher.notify("scan")
    publisher.notify("paper")

    assert publisher.ready is False
    assert publisher._pending_events == {"scan", "paper"}


def test_restored_feature_cards_have_real_data_sources(tmp_path: Path) -> None:
    config = AppConfig.load(ROOT)

    class RecordingDatabase(EmptyDatabase):
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query(self, sql: str, parameters=()):
            self.queries.append(" ".join(sql.split()))
            return []

    database = RecordingDatabase()
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        {
            "health": lambda: {"status": "PASS", "provider_budget": {}},
            "version": lambda: "test",
            "strategies": lambda: [],
        },
    )

    for stable_id in (
        "api-errors",
        "session-preparation",
        "breaking-events",
        "ticker-intelligence",
        "charts-and-levels",
        "trade-overrides",
        "strategy-change-log",
        "workflow-log",
        "automation-diagnostics",
        "applied-upgrades",
        "upgrade-review",
    ):
        value = publisher._card_value(stable_id)
        assert value != {"status": "NO DATA"}, stable_id

    combined = "\n".join(database.queries)
    for table in (
        "provider_failures",
        "provider_requests",
        "provider_cache_metadata",
        "levels",
        "overrides",
        "strategy_versions",
        "deployment_receipts",
        "scheduler_runs",
        "learning_recommendations",
    ):
        assert table in combined
