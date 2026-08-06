from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from tradysquid.core.config import AppConfig
from tradysquid.core.models import utc_now
from tradysquid.data.database import Database
from tradysquid.discord.bot import format_command_response
from tradysquid.discord.layout import CARD_ROUTES, ORIGINAL_LEARNING_CHANNELS
from tradysquid.discord.publishing import DiscordPublishingService, _payload
from tradysquid.discord.reconciliation import MessageReconciler
from tradysquid.learning.center import LearningCenter
from tradysquid.reporting.service import ReportingService

ROOT = Path(__file__).resolve().parents[1]


class FakeReconciler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, str]] = []
        self.state: dict[str, tuple[str, str]] = {}

    def reconcile(self, stable_id, channel_id, payload, version):
        previous = self.state.get(stable_id)
        action = "created"
        if previous:
            action = (
                "unchanged"
                if previous == (str(channel_id), payload["content"])
                else "updated"
            )
        self.state[stable_id] = (str(channel_id), payload["content"])
        self.calls.append((stable_id, str(channel_id), payload, version))
        return {
            "stable_id": stable_id,
            "channel_id": str(channel_id),
            "message_id": str(len(self.calls)),
            "version": version,
            "signature": "signature",
            "acknowledged": True,
            "action": action,
        }


class FakeApi:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self.messages: dict[tuple[str, str], dict[str, str]] = {}

    def create_message(self, channel_id, payload):
        message_id = str(len(self.created) + 1)
        self.created.append((str(channel_id), payload))
        self.messages[(str(channel_id), message_id)] = {"id": message_id}
        return {"id": message_id}

    def update_message(self, channel_id, message_id, payload):
        self.updated.append((str(channel_id), str(message_id), payload))
        self.messages[(str(channel_id), str(message_id))] = {
            "id": str(message_id)
        }
        return {"id": str(message_id)}

    def get_message(self, channel_id, message_id):
        return self.messages.get((str(channel_id), str(message_id)))


class FakeState:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self, stable_id):
        return self.value

    def put(self, stable_id, value):
        self.value = value


def _publisher(tmp_path: Path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "tradysquid.db")
    database.initialize()
    database.register_strategies(config.strategies)
    reporting = ReportingService(database)

    def report(name, value=""):
        if name == "strategy-report":
            return reporting.by_strategy()
        if name == "ticker-report":
            return reporting.by_ticker()
        if name == "learning-results":
            return {"closed_trade_metrics": reporting.overall()}
        return reporting.overall()

    services = {
        "health": lambda: {
            "status": "PASS",
            "provider_budget": {"available": 100},
        },
        "version": lambda: "test",
        "open_positions": lambda: database.query(
            "SELECT * FROM paper_positions WHERE state IN "
            "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
        ),
        "report": report,
        "strategies": lambda: [{"strategy_id": "regular-call"}],
    }
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        services,
    )
    route_channels = {str(route["channel"]) for route in CARD_ROUTES.values()}
    route_channels.update(ORIGINAL_LEARNING_CHANNELS)
    route_channels.update(
        {
            "learning-index",
            "learning-search",
            "ask-tradebot",
            "examples-and-reviews",
            "trade-journal",
        }
    )
    channels = {
        channel_name: SimpleNamespace(id=index + 1, name=channel_name)
        for index, channel_name in enumerate(sorted(route_channels))
    }
    publisher.channel_by_name = {
        name.casefold(): value for name, value in channels.items()
    }
    publisher.reconciler = FakeReconciler()
    return publisher


def _insert_closed_trade(
    database: Database,
    *,
    suffix: str,
    symbol: str,
    strategy_id: str,
    pnl_dollars: float,
    outcome: str,
) -> None:
    observed = utc_now()
    candidate_id = f"candidate-{suffix}"
    cycle_id = f"cycle-{suffix}"
    position_id = f"position-{suffix}"
    database.execute(
        "INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,completed_at,status) "
        "VALUES (?,?,?,?,?,?)",
        (
            cycle_id,
            candidate_id,
            strategy_id,
            observed,
            observed,
            "CLOSED",
        ),
    )
    database.execute(
        "INSERT INTO paper_positions("
        "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,"
        "symbol,direction,structure,state,opened_at,closed_at,entry_value,current_value,"
        "maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            position_id,
            cycle_id,
            candidate_id,
            strategy_id,
            "1.0.0",
            "test-hash",
            symbol,
            "call",
            "long-option",
            "CLOSED",
            observed,
            observed,
            50.0,
            50.0 + pnl_dollars,
            100.0,
            pnl_dollars,
            pnl_dollars / 50.0,
            max(pnl_dollars / 50.0, 0.0),
            min(pnl_dollars / 50.0, 0.0),
            json.dumps(
                {
                    "management": {
                        "profit_target_pct": 0.2,
                        "hard_stop_pct": -0.15,
                    }
                }
            ),
        ),
    )
    database.execute(
        "INSERT INTO closed_outcomes(position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            position_id,
            outcome,
            "target" if pnl_dollars > 0 else "stop",
            pnl_dollars,
            pnl_dollars / 50.0,
            observed,
        ),
    )


def test_command_response_formats_dicts_and_splits_safely() -> None:
    chunks = format_command_response({"items": list(range(1000))})
    assert len(chunks) > 1
    assert all(len(chunk) <= 1900 for chunk in chunks)


def test_card_payload_is_readable_and_respects_discord_limit() -> None:
    payload = _payload(
        "Rejected Candidates",
        [
            {
                "candidate_id": "uuid-noise",
                "reason": "spread too wide",
                "rejected": 8,
            },
            {
                "candidate_id": "more-noise",
                "reason": "volume too low",
                "rejected": 4,
            },
        ],
        stable_id="rejected-candidates",
    )
    content = payload["content"]
    assert len(content) <= 2000
    assert "```json" not in content
    assert "uuid-noise" not in content
    assert "spread too wide" in content
    assert "volume too low" in content


def test_original_layout_routes_every_bootstrap_card() -> None:
    assert set(CARD_ROUTES) == {
        stable_id
        for stable_id, _, _ in DiscordPublishingService.REQUIRED_BOOTSTRAP_CARDS
    }
    assert CARD_ROUTES["latest-scan"]["channel"] == "scanner-feed"
    assert CARD_ROUTES["open-positions"]["channel"] == "held-positions"
    assert CARD_ROUTES["daily-recap"]["channel"] == "performance-dashboard"
    assert CARD_ROUTES["strategy-control"]["category"] == "STRATEGY CONTROL"
    assert CARD_ROUTES["strategy-settings"]["category"] == "STRATEGY CONTROL"
    assert CARD_ROUTES["strategy-versions"]["category"] == "STRATEGY CONTROL"
    assert CARD_ROUTES["strategy-recommendations"]["category"] == "STRATEGY CONTROL"
    assert CARD_ROUTES["system-health"]["category"] == "SYSTEM"
    assert "shadow-candidates" not in CARD_ROUTES


def test_multiple_stable_cards_share_original_channels() -> None:
    scanner_cards = {
        stable_id
        for stable_id, route in CARD_ROUTES.items()
        if route["channel"] == "scanner-feed"
    }
    performance_cards = {
        stable_id
        for stable_id, route in CARD_ROUTES.items()
        if route["channel"] == "performance-dashboard"
    }
    held_position_cards = {
        stable_id
        for stable_id, route in CARD_ROUTES.items()
        if route["channel"] == "held-positions"
    }
    assert scanner_cards == {
        "latest-scan",
        "accepted-candidates",
        "rejected-candidates",
    }
    assert performance_cards == {
        "daily-recap",
        "weekly-report",
        "monthly-dashboard",
    }
    assert held_position_cards == {
        "open-positions",
        "recent-lifecycle-events",
    }


def test_bootstrap_cards_reconcile_stable_messages(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    totals = asyncio.run(publisher._publish_bootstrap_cards())
    assert totals["failed"] == 0
    calls = publisher.reconciler.calls
    assert len(calls) == len(publisher.REQUIRED_BOOTSTRAP_CARDS)
    assert len({call[0] for call in calls}) == len(calls)
    assert all(call[2]["content"] for call in calls)


def test_event_refresh_keeps_scanner_and_market_cards_active(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    publisher.ready = True

    asyncio.run(publisher.refresh("scan"))

    stable_ids = {call[0] for call in publisher.reconciler.calls}
    assert {
        "latest-scan",
        "accepted-candidates",
        "rejected-candidates",
        "market-regime",
        "scanner-status",
        "system-activity",
    } <= stable_ids
    assert "shadow-candidates" not in stable_ids


def test_closed_trade_history_repopulates_wins_losses_and_performance(
    tmp_path: Path,
) -> None:
    publisher = _publisher(tmp_path)
    _insert_closed_trade(
        publisher.db,
        suffix="win",
        symbol="SPY",
        strategy_id="regular-call",
        pnl_dollars=25.0,
        outcome="WIN",
    )
    _insert_closed_trade(
        publisher.db,
        suffix="loss",
        symbol="QQQ",
        strategy_id="regular-put",
        pnl_dollars=-10.0,
        outcome="LOSS",
    )

    wins = publisher._card_value("wins")
    losses = publisher._card_value("losses")
    ticker = publisher._card_value("ticker-results")
    strategy = publisher._card_value("strategy-breakdown")
    daily = publisher._card_value("daily-recap")

    assert [row["symbol"] for row in wins] == ["SPY"]
    assert [row["symbol"] for row in losses] == ["QQQ"]
    assert set(ticker) == {"QQQ", "SPY"}
    assert set(strategy) == {"regular-call@1.0.0", "regular-put@1.0.0"}
    assert daily["sample_size"] == 2
    assert daily["net_pnl"] == 15.0


def test_report_refresh_publishes_closed_trade_outputs(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)
    _insert_closed_trade(
        publisher.db,
        suffix="one",
        symbol="SPY",
        strategy_id="regular-call",
        pnl_dollars=20.0,
        outcome="WIN",
    )
    publisher.ready = True

    asyncio.run(publisher.refresh("reports"))

    stable_ids = {call[0] for call in publisher.reconciler.calls}
    assert {
        "daily-recap",
        "weekly-report",
        "monthly-dashboard",
        "ticker-results",
        "strategy-breakdown",
        "regular-call",
        "regular-put",
        "swing-call",
        "swing-put",
        "bull-put-spread",
        "bear-call-spread",
        "learning-results",
    } <= stable_ids


def test_learning_center_uses_one_original_set_of_27_channels(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path)

    totals = asyncio.run(publisher._publish_learning_center())

    lesson_calls = [
        call
        for call in publisher.reconciler.calls
        if call[0].startswith("learning-center:")
        and call[0] != "learning-center:index"
    ]
    assert totals["failed"] == 0
    assert len(lesson_calls) == 27
    assert {
        publisher.channel_by_name[name].id for name in ORIGINAL_LEARNING_CHANNELS
    } == {int(call[1]) for call in lesson_calls}


def test_cross_channel_rebinding_creates_in_original_channel_not_old_duplicate() -> None:
    api = FakeApi()
    state = FakeState(
        {
            "stable_id": "latest-scan",
            "channel_id": "999",
            "message_id": "old-message",
            "version": "1",
            "signature": "old-signature",
            "acknowledged": True,
        }
    )
    reconciler = MessageReconciler(api, state)

    result = reconciler.reconcile(
        "latest-scan",
        "100",
        {"content": "Latest scan in original scanner-feed"},
        "2",
    )

    assert result["action"] == "rebound"
    assert api.created[0][0] == "100"
    assert not api.updated
    assert state.value["channel_id"] == "100"