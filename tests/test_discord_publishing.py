from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from tradysquid.core.config import AppConfig
from tradysquid.data.database import Database
from tradysquid.discord.bot import format_command_response
from tradysquid.discord.publishing import DiscordPublishingService, _payload
from tradysquid.learning.center import LearningCenter

ROOT = Path(__file__).resolve().parents[1]


class FakeReconciler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, str]] = []

    def reconcile(self, stable_id, channel_id, payload, version):
        self.calls.append((stable_id, channel_id, payload, version))
        return {
            "stable_id": stable_id,
            "channel_id": channel_id,
            "message_id": str(len(self.calls)),
            "version": version,
            "signature": "signature",
            "acknowledged": True,
        }


def _publisher(tmp_path: Path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "tradysquid.db")
    database.initialize()
    database.register_strategies(config.strategies)
    services = {
        "health": lambda: {"status": "PASS", "provider_budget": {"available": 100}},
        "version": lambda: "test",
        "open_positions": lambda: [],
        "report": lambda name, value="": {"report": name, "sample_size": 0},
        "strategies": lambda: [{"strategy_id": "regular-call"}],
    }
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        services,
    )
    channels = {
        channel_name: SimpleNamespace(id=index + 1)
        for index, (_, channel_name, _) in enumerate(
            publisher.REQUIRED_BOOTSTRAP_CARDS
        )
    }
    channels.update(
        {
            lesson["channel_name"]: SimpleNamespace(id=100 + index)
            for index, lesson in enumerate(config.learning_center["lessons"])
        }
    )
    channels["learning-search"] = SimpleNamespace(id=500)
    channels["trade-journal"] = SimpleNamespace(id=501)
    publisher.channel_by_name = {name.casefold(): value for name, value in channels.items()}
    publisher.reconciler = FakeReconciler()
    return publisher


def test_command_response_formats_dicts_and_splits_safely() -> None:
    chunks = format_command_response({"items": list(range(1000))})
    assert len(chunks) > 1
    assert all(len(chunk) <= 1900 for chunk in chunks)


def test_card_payload_respects_discord_content_limit() -> None:
    payload = _payload("Large", {"value": "x" * 10000})
    assert len(payload["content"]) <= 2000
    assert "truncated" in payload["content"]


def test_bootstrap_card_set_includes_required_operational_views(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    stable_ids = {item[0] for item in publisher.REQUIRED_BOOTSTRAP_CARDS}
    assert {
        "system-health",
        "active-universe",
        "latest-scan",
        "open-positions",
        "daily-recap",
        "strategy-control",
        "learning-results",
    } <= stable_ids


def test_bootstrap_cards_reconcile_stable_messages(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    totals = asyncio.run(publisher._publish_bootstrap_cards())
    assert totals["failed"] == 0
    calls = publisher.reconciler.calls
    assert len(calls) == len(publisher.REQUIRED_BOOTSTRAP_CARDS)
    assert len({call[0] for call in calls}) == len(calls)
    assert all(call[2]["content"] for call in calls)


def test_event_refresh_updates_only_relevant_cards(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    publisher.ready = True
    asyncio.run(publisher.refresh("universe"))
    stable_ids = {call[0] for call in publisher.reconciler.calls}
    assert stable_ids == {"active-universe", "provider-status", "system-health"}
