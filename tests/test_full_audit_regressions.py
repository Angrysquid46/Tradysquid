from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from tradysquid.app import Application
from tradysquid.core.config import AppConfig, validate_strategy_config
from tradysquid.core.enums import CandidateStatus, Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.data.legacy_import import import_legacy_closed_trades
from tradysquid.discord.layout import CARD_ROUTES
from tradysquid.discord.publishing import DiscordPublishingService
from tradysquid.learning.center import LearningCenter
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker


ROOT = Path(__file__).resolve().parents[1]


class Publisher:
    def __init__(self):
        self.events = []

    def notify(self, event):
        self.events.append(event)


class Diagnostics:
    def __init__(self):
        self.events = []

    def observe(self, *args, **kwargs):
        self.events.append((args, kwargs))


def _eligible_call(config):
    contract = OptionContract(
        "CALL",
        "X",
        (date.today() + timedelta(days=14)).isoformat(),
        100,
        "call",
        0.70,
        0.80,
        100,
        500,
        0.40,
    )
    strategy = StrategyRegistry(config.strategies).get("regular-call")
    decision = strategy.evaluate(
        "scan", "X", 100, Regime.BULLISH_CONTROLLED, [contract], 80
    )
    decision.status = CandidateStatus.SELECTED
    decision.configuration_snapshot["entry"]["selection_mode"] = (
        "automatically open qualified paper trades"
    )
    return decision


def test_shadow_is_not_an_active_runtime_status_or_route():
    assert not hasattr(CandidateStatus, "SHADOW")
    assert "shadow-candidates" not in CARD_ROUTES
    publishing = (ROOT / "tradysquid/discord/publishing.py").read_text(
        encoding="utf-8"
    )
    assert 'stable_id == "shadow-candidates"' not in publishing
    assert '"shadow-candidates",' not in publishing


def test_shadow_selection_mode_is_rejected():
    config = AppConfig.load(ROOT).strategies["regular-call"]
    changed = json.loads(json.dumps(config))
    changed["entry"]["selection_mode"] = "shadow-only"
    try:
        validate_strategy_config(changed)
    except ValueError as exc:
        assert "selection_mode" in str(exc)
    else:
        raise AssertionError("shadow-only selection mode was accepted")


def test_selected_candidate_auto_opens_paper_position(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "auto-open.db")
    database.initialize()
    database.register_strategies(config.strategies)
    decision = _eligible_call(config)

    app = object.__new__(Application)
    app.scanner = SimpleNamespace(scan_symbol=lambda symbol, trigger: [decision])
    app.paper = PaperBroker(database)
    app.db = database
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()

    result = Application.scan_symbol(app, "X", "test")

    assert len(result) == 1
    assert database.query("SELECT COUNT(*) AS n FROM paper_positions")[0]["n"] == 1
    assert "scan" in app.publisher.events
    assert "paper" in app.publisher.events


def test_target_hit_closes_position_in_monitor(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "auto-close.db")
    database.initialize()
    database.register_strategies(config.strategies)
    decision = _eligible_call(config)
    broker = PaperBroker(database)
    position = broker.open(decision)

    app = object.__new__(Application)
    app.db = database
    app.paper = broker
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app.market_is_open = lambda: True
    app._position_quote_map = lambda rows: {
        position.position_id: {"CALL": (1.20, 1.25)}
    }

    results = Application.monitor_positions(app)

    assert results[0]["state"] == "CLOSED_WIN"
    assert database.query(
        "SELECT outcome FROM closed_outcomes WHERE position_id=?",
        (position.position_id,),
    )[0]["outcome"] == "CLOSED_WIN"
    assert "paper" in app.publisher.events


def test_legacy_closed_trade_import_is_idempotent(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "legacy.db")
    database.initialize()
    database.register_strategies(config.strategies)
    source = tmp_path / "ford-plays-log.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trade_id",
                "timestamp",
                "play_type",
                "ticker",
                "call_or_put",
                "entry_contract_value",
                "max_risk",
                "outcome",
                "pct_gain_loss",
                "realized_pl_dollars",
                "closed_at",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "trade_id": "old-1",
                "timestamp": "2026-07-01T14:00:00+00:00",
                "play_type": "REGULAR",
                "ticker": "F",
                "call_or_put": "CALL",
                "entry_contract_value": "80",
                "max_risk": "80",
                "outcome": "WIN",
                "pct_gain_loss": "25",
                "realized_pl_dollars": "20",
                "closed_at": "2026-07-01T15:00:00+00:00",
            }
        )

    first = import_legacy_closed_trades(database, source, config.strategies)
    second = import_legacy_closed_trades(database, source, config.strategies)

    assert first["imported"] == 1
    assert second["already_present"] == 1
    assert database.query("SELECT COUNT(*) AS n FROM closed_outcomes")[0]["n"] == 1


def test_wins_and_losses_use_pnl_sign_not_old_labels(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "cards.db")
    database.initialize()
    database.register_strategies(config.strategies)
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        {
            "health": lambda: {},
            "version": lambda: "test",
            "open_positions": lambda: [],
            "report": lambda *args: {},
            "strategies": lambda: [],
        },
    )
    now = "2026-08-03T15:00:00+00:00"
    for suffix, pnl, outcome in (
        ("win", 10.0, "CLOSED_WIN"),
        ("loss", -5.0, "CLOSED_LOSS"),
        ("flat", 0.0, "CLOSED_BREAKEVEN"),
    ):
        database.execute(
            "INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,status) "
            "VALUES (?,?,?,?,?)",
            (f"cycle-{suffix}", f"candidate-{suffix}", "regular-call", now, "CLOSED"),
        )
        database.execute(
            "INSERT INTO paper_positions("
            "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,"
            "symbol,direction,structure,state,opened_at,closed_at,entry_value,current_value,"
            "maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"position-{suffix}",
                f"cycle-{suffix}",
                f"candidate-{suffix}",
                "regular-call",
                "1",
                "hash",
                suffix.upper(),
                "call",
                "long-option",
                outcome,
                now,
                now,
                50,
                50 + pnl,
                50,
                pnl,
                pnl / 50,
                max(pnl / 50, 0),
                min(pnl / 50, 0),
                "{}",
            ),
        )
        database.execute(
            "INSERT INTO closed_outcomes("
            "position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at"
            ") VALUES (?,?,?,?,?,?)",
            (f"position-{suffix}", outcome, "test", pnl, pnl / 50, now),
        )

    assert [row["symbol"] for row in publisher._card_value("wins")] == ["WIN"]
    assert [row["symbol"] for row in publisher._card_value("losses")] == ["LOSS"]


def test_core_bootstrap_is_bounded_and_extended_backfill_is_separate():
    source = (ROOT / "tradysquid/discord/publishing.py").read_text(encoding="utf-8")
    assert "CORE_BOOTSTRAP_IDS" in source
    assert "async def complete_backfill" in source
    assert "discord-extended-backfill.json" in source
    assert "ORDER BY opened_at DESC LIMIT 250" not in source


def test_rollback_restores_scheduled_tasks():
    source = (ROOT / "scripts/auto_install_clean_rebuild.ps1").read_text(
        encoding="utf-8"
    )
    assert "Export-TradysquidScheduledTasks" in source
    assert "Restore-TradysquidScheduledTasks" in source
    assert "Export-ScheduledTask" in source
    assert "Register-ScheduledTask" in source


def test_cleanup_does_not_select_channels_by_name_alone():
    source = (ROOT / "tradysquid/discord/structure.py").read_text(encoding="utf-8")
    assert "history(limit=None" in source
    assert "category_is_invented or name_is_migration" not in source
