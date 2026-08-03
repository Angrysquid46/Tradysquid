from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tradysquid.core.config import AppConfig
from tradysquid.discord.bot import REQUIRED_COMMANDS
from tradysquid.discord.layout import (
    CANONICAL_CATEGORY_ORDER,
    CARD_ROUTES,
    INVENTED_CATEGORIES,
    LESSON_ROUTES,
    ORIGINAL_CHANNELS,
)
from tradysquid.discord.publishing import DiscordPublishingService
from tradysquid.learning.center import LearningCenter
from tradysquid.operations.scheduler import (
    JOB_DEFINITIONS,
    LIVE_STARTUP_JOBS,
    SchedulerService,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STRATEGIES = {
    "regular-call",
    "regular-put",
    "swing-call",
    "swing-put",
    "bull-put-spread",
    "bear-call-spread",
}
EXPECTED_STRATEGY_CONTROL_CHANNELS = (
    "strategy-control",
    "strategy-settings",
    "strategy-versions",
    "trade-overrides",
    "strategy-change-log",
    "strategy-recommendations",
)


class FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.next_run_time = None


class FakeScheduler:
    def __init__(self) -> None:
        self.timezone = ZoneInfo("America/Chicago")
        self.running = False
        self.jobs: dict[str, FakeJob] = {}

    def add_job(self, function, kind, *, id, replace_existing, **parameters):
        self.jobs[id] = FakeJob(id)
        return self.jobs[id]

    def start(self) -> None:
        self.running = True

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def modify_job(self, job_id: str, *, next_run_time) -> None:
        self.jobs[job_id].next_run_time = next_run_time

    def shutdown(self, wait: bool = False) -> None:
        self.running = False


class RecordingDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql: str, parameters=()):
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if "closed_outcomes" in normalized and "= 'WIN'" in normalized:
            return [
                {
                    "symbol": "SPY",
                    "strategy_id": "regular-call",
                    "outcome": "WIN",
                    "exit_reason": "target",
                    "pnl_dollars": 12.5,
                    "pnl_pct": 0.125,
                    "closed_at": "2026-08-03T15:00:00+00:00",
                }
            ]
        if "closed_outcomes" in normalized and "<> 'WIN'" in normalized:
            return [
                {
                    "symbol": "QQQ",
                    "strategy_id": "regular-put",
                    "outcome": "LOSS",
                    "exit_reason": "stop",
                    "pnl_dollars": -8.0,
                    "pnl_pct": -0.08,
                    "closed_at": "2026-08-03T15:05:00+00:00",
                }
            ]
        return []

    def execute(self, sql: str, parameters=()):
        return None


def _schema_pairs() -> set[tuple[str, str]]:
    schema = json.loads(
        (ROOT / "config" / "discord-schema.json").read_text(encoding="utf-8")
    )
    pairs: set[tuple[str, str]] = set()
    for category in schema["categories"]:
        for channel in category["channels"]:
            name = channel["name"] if isinstance(channel, dict) else channel
            pairs.add((category["name"], name))
    return pairs


def test_dashboard_keeps_strategy_control_and_removes_only_failed_inventions() -> None:
    assert CANONICAL_CATEGORY_ORDER == (
        "START HERE",
        "COMMUNITY",
        "LIVE TRADING DESK",
        "MARKET INTELLIGENCE",
        "LEARNING CENTER",
        "PERFORMANCE",
        "SYSTEM",
        "STRATEGY CONTROL",
        "OWNER CONTROL",
    )
    assert INVENTED_CATEGORIES == {
        "SCANNING",
        "PAPER TRADING",
        "LEARNING CENTER 2",
    }
    assert ORIGINAL_CHANNELS["STRATEGY CONTROL"] == EXPECTED_STRATEGY_CONTROL_CHANNELS


def test_every_card_route_points_to_an_approved_existing_channel() -> None:
    pairs = _schema_pairs()
    assert CARD_ROUTES
    for stable_id, route in CARD_ROUTES.items():
        assert (route["category"], route["channel"]) in pairs, stable_id

    assert CARD_ROUTES["latest-scan"] == {
        "category": "LIVE TRADING DESK",
        "channel": "scanner-feed",
        "mandatory": True,
        "owner_only": False,
    }
    assert CARD_ROUTES["daily-recap"]["category"] == "PERFORMANCE"
    assert CARD_ROUTES["system-health"]["category"] == "SYSTEM"
    assert CARD_ROUTES["strategy-control"]["category"] == "STRATEGY CONTROL"


def test_all_six_strategies_and_controls_remain_configured() -> None:
    config = AppConfig.load(ROOT)
    assert set(config.strategies) == EXPECTED_STRATEGIES
    assert all(config.strategies[strategy_id]["enabled"] for strategy_id in EXPECTED_STRATEGIES)
    assert float(config.defaults["risk"]["maximum_position_risk_dollars"]) == 100.0
    assert int(config.defaults["universe"]["maximum_active"]) == 25


def test_single_learning_center_has_27_original_destinations() -> None:
    config = AppConfig.load(ROOT)
    lessons = config.learning_center["lessons"]
    assert len(lessons) == 27
    assert len({lesson["lesson_id"] for lesson in lessons}) == 27
    assert all(
        LESSON_ROUTES[lesson["lesson_id"]] == lesson["channel_name"]
        for lesson in lessons
    )
    assert all(
        ("LEARNING CENTER", lesson["channel_name"]) in _schema_pairs()
        for lesson in lessons
    )


def test_owner_commands_cover_scanning_positions_reports_learning_and_strategies() -> None:
    required = {
        "status",
        "diagnostics",
        "universe",
        "universe-refresh",
        "scan",
        "scan-all",
        "scan-status",
        "candidate",
        "rejections",
        "shadow-results",
        "paper-open",
        "paper-close",
        "paper-position",
        "open-positions",
        "closed-positions",
        "strategies",
        "strategy-show",
        "strategy-enable",
        "strategy-disable",
        "strategy-preset",
        "strategy-setting",
        "strategy-version",
        "strategy-rollback",
        "strategy-recommendations",
        "strategy-approve",
        "strategy-reject",
        "daily-report",
        "weekly-report",
        "monthly-report",
        "ticker-report",
        "strategy-report",
        "learning-results",
        "learn",
        "learning-search",
        "why",
    }
    assert required <= set(REQUIRED_COMMANDS)


def test_scheduler_starts_scanning_and_position_work_immediately() -> None:
    service = object.__new__(SchedulerService)
    service.scheduler = FakeScheduler()
    service.startup_jobs_triggered = []
    definitions = {job_id for job_id, _, _ in JOB_DEFINITIONS}
    assert set(LIVE_STARTUP_JOBS) <= definitions
    assert {
        "full-strategy-scan",
        "open-position-monitoring",
        "shadow-candidate-monitoring",
        "market-intelligence-refresh",
    } <= set(LIVE_STARTUP_JOBS)

    service.register({job_id: (lambda: None) for job_id in definitions})
    service.start()

    assert service.running is True
    assert service.startup_jobs_triggered == list(LIVE_STARTUP_JOBS)
    assert all(
        service.scheduler.get_job(job_id).next_run_time is not None
        for job_id in LIVE_STARTUP_JOBS
    )


def test_closed_trade_cards_query_historical_outcomes_on_bootstrap(tmp_path: Path) -> None:
    config = AppConfig.load(ROOT)
    database = RecordingDatabase()
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        {
            "health": lambda: {"status": "PASS"},
            "version": lambda: "test",
            "open_positions": lambda: [],
            "report": lambda name, value="": {"report": name},
            "strategies": lambda: [],
        },
    )

    wins = publisher._card_value("wins")
    losses = publisher._card_value("losses")

    assert wins[0]["symbol"] == "SPY"
    assert losses[0]["symbol"] == "QQQ"
    assert sum("closed_outcomes" in query for query in database.queries) == 2


def test_performance_and_learning_cards_are_part_of_bootstrap() -> None:
    stable_ids = {
        stable_id
        for stable_id, _, _ in DiscordPublishingService.REQUIRED_BOOTSTRAP_CARDS
    }
    assert {
        "wins",
        "losses",
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
