from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tradysquid.app import Application
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import CandidateStatus, Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker


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


def _app(tmp_path):
    app = object.__new__(Application)
    app.db = Database(tmp_path / "ops.db")
    app.db.initialize()
    app.manager = SimpleNamespace(available=125)
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app._market_clock_cache = {
        "observed_monotonic": 10**12,
        "open": True,
        "state": "open",
        "raw": {},
    }
    return app


def _eligible_call(root, ask=0.80):
    config = AppConfig.load(root)
    contract = OptionContract(
        "CALL",
        "X",
        (date.today() + timedelta(days=14)).isoformat(),
        100,
        "call",
        max(ask - 0.10, 0.01),
        ask,
        100,
        500,
        0.40,
    )
    strategy = StrategyRegistry(config.strategies).get("regular-call")
    decision = strategy.evaluate(
        "scan", "X", 100, Regime.BULLISH_CONTROLLED, [contract], 80
    )
    decision.status = CandidateStatus.SELECTED
    return config, decision


def test_market_closed_scan_does_not_touch_scanner(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: False
    app.universe = SimpleNamespace(active=lambda: ["A", "B"])
    app.scan_symbol = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("scanner ran while market was closed")
    )

    result = Application.scan_all(app)

    assert result["status"] == "SKIPPED_MARKET_CLOSED"
    assert result["scanned_symbols"] == []


def test_scan_batches_rotate_without_exceeding_eight_symbols(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: True
    symbols = [f"T{index:02d}" for index in range(25)]
    app.universe = SimpleNamespace(active=lambda: symbols)
    scanned = []
    app.scan_symbol = lambda symbol, trigger, publish=False: scanned.append(symbol) or []

    first = Application.scan_all(app)
    second = Application.scan_all(app)

    assert len(first["scanned_symbols"]) == 8
    assert len(second["scanned_symbols"]) == 8
    assert set(first["scanned_symbols"]).isdisjoint(second["scanned_symbols"])
    assert scanned == first["scanned_symbols"] + second["scanned_symbols"]


def test_scan_skips_when_provider_reserve_would_be_consumed(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: True
    app.manager.available = 25
    app.universe = SimpleNamespace(active=lambda: ["A", "B"])
    app.scan_symbol = lambda *args, **kwargs: []

    result = Application.scan_all(app)

    assert result["status"] == "SKIPPED_PROVIDER_BUDGET"


def test_position_quotes_batch_same_underlying_expiration(tmp_path):
    app = _app(tmp_path)
    expiration = (date.today() + timedelta(days=7)).isoformat()
    now = "2026-08-03T15:00:00+00:00"
    for index in (1, 2):
        app.db.execute(
            "INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,status) "
            "VALUES (?,?,?,?,?)",
            (f"c{index}", f"candidate{index}", "regular-call", now, "OPEN"),
        )
        app.db.execute(
            "INSERT INTO paper_positions("
            "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,"
            "symbol,direction,structure,state,opened_at,entry_value,current_value,"
            "maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"p{index}", f"c{index}", f"candidate{index}", "regular-call",
                "1", "hash", "X", "call", "long-option", "OPEN", now,
                50, 50, 50, 0, 0, 0, 0, "{}",
            ),
        )
        app.db.execute(
            "INSERT INTO paper_legs("
            "position_id,contract_symbol,side,quantity,option_type,strike,expiration,"
            "multiplier,entry_bid,entry_ask,entry_fill,current_bid,current_ask,current_mark"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"p{index}", f"CALL{index}", "buy", 1, "call", 100 + index,
                expiration, 100, .4, .5, .51, 0, 0, 0,
            ),
        )

    calls = []
    contracts = [
        OptionContract("CALL1", "X", expiration, 101, "call", .6, .7, 1, 1, .4),
        OptionContract("CALL2", "X", expiration, 102, "call", .8, .9, 1, 1, .4),
    ]
    app.provider = SimpleNamespace(
        option_chain=lambda symbol, expiry: calls.append((symbol, expiry)) or contracts
    )

    result = Application._position_quote_map(
        app,
        [{"id": "p1", "symbol": "X"}, {"id": "p2", "symbol": "X"}],
    )

    assert calls == [("X", expiration)]
    assert result["p1"]["CALL1"] == (.6, .7)
    assert result["p2"]["CALL2"] == (.8, .9)


def test_paper_entry_uses_conservative_fill_value(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    config, decision = _eligible_call(root, ask=.80)
    database = Database(tmp_path / "fill.db")
    database.initialize()
    database.register_strategies(config.strategies)

    position = PaperBroker(database).open(decision)

    assert position.entry_value == pytest.approx(81.0)
    assert position.maximum_risk == pytest.approx(81.0)


def test_paper_entry_rejects_slippage_above_risk_limit(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    config, decision = _eligible_call(root, ask=1.00)
    decision.status = CandidateStatus.SELECTED
    database = Database(tmp_path / "risk.db")
    database.initialize()
    database.register_strategies(config.strategies)

    with pytest.raises(ValueError, match="exceeds the configured maximum risk"):
        PaperBroker(database).open(decision)


def test_nested_tradier_clock_response_is_recognized(tmp_path):
    app = _app(tmp_path)
    app.provider = SimpleNamespace(
        market_clock=lambda: {"clock": {"state": "open", "description": "Market is open"}}
    )

    result = Application.refresh_market_session(app)

    assert result["open"] is True
    assert result["state"] == "open"
