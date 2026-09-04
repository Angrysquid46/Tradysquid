from datetime import datetime, timedelta

import pytest

import scoreboard
from bots.riptide.evolution import EvolutionLoop
from bots.riptide.engine import FAMILIES
from bots.riptide.runtime import RiptideRuntime


NOW = datetime(2026, 8, 28, 10, 0)


class View:
    bid = 1.0

    def market_as_of(self, timestamp):
        return {"tier": "A"}

    def bars_as_of(self, timestamp, lookback_minutes=90):
        rows = [{"close": 500 + i * .03, "high": 500.05 + i * .03, "low": 499.95 + i * .03, "volume": 1000} for i in range(32)]
        base = rows[-1]["close"]
        rows.extend({"close": close, "high": close + .05, "low": close - .05, "volume": 1500} for close in (base + .05, base + .25, base + .55))
        return rows

    def options_as_of(self, timestamp):
        return {"tier": "A", "contracts": [{"option_symbol": "SPY260828C00500000", "side": "call", "expiration": timestamp.date().isoformat(), "bid": self.bid, "ask": 1.05, "delta": .45, "gamma": .01, "theta": -.05, "iv": .2, "data_class": "VERIFIED_REAL", "volume": 100, "open_interest": 500}]}


def test_runtime_records_immutable_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(scoreboard, "BOTS", ("BLACKTIDE", "RIPTIDE"))
    connection, view = scoreboard.connect_db(), View()
    runtime = RiptideRuntime(market_view=view, evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"),
                             telemetry_path=tmp_path / "decision-telemetry.jsonl")
    assert runtime.evaluate(NOW, connection).action == "ENTER"
    assert scoreboard.current_position_status(connection, "RIPTIDE") is not None
    view.bid = 1.55
    assert runtime.evaluate(NOW + timedelta(minutes=1), connection).action == "EXIT"
    assert scoreboard.trade_count(connection, "RIPTIDE") == 1
    trade = connection.execute(
        "SELECT entry_price, contracts FROM official_trades WHERE bot='RIPTIDE'"
    ).fetchone()
    expected_pnl = (1.55 - float(trade["entry_price"])) * int(trade["contracts"]) * 100
    assert scoreboard.total_pnl(connection, "RIPTIDE") == pytest.approx(expected_pnl)
    outcome = EvolutionLoop(tmp_path / "outcomes.jsonl").load()[0]
    assert outcome.exit_reason == "aggressive profit capture"
    assert outcome.family in FAMILIES


def test_open_position_uses_direct_contract_quote_when_chain_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    connection, view = scoreboard.connect_db(), View()
    runtime = RiptideRuntime(market_view=view, evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"),
                             telemetry_path=tmp_path / "telemetry.jsonl",
                             quote_loader=lambda symbol, **kwargs: {"symbol": symbol, "bid": .70, "ask": .75})
    runtime.engine.position = __import__("bots.riptide.engine", fromlist=["Position"]).Position(
        "direct-quote", "SPY260828C00500000", "call", 1, 1.0, NOW - timedelta(minutes=11))
    scoreboard.record_trade_open(connection, trade_id="direct-quote", bot="RIPTIDE", generation=1,
                                 opened_at=(NOW - timedelta(minutes=11)).isoformat(), side="call",
                                 contract_symbol="SPY260828C00500000", entry_price=1.0, contracts=1,
                                 entry_bankroll=1000.0)
    view.options_as_of = lambda timestamp: {"tier": "C", "contracts": []}
    assert runtime.evaluate(NOW, connection).action == "EXIT"
    assert scoreboard.total_pnl(connection, "RIPTIDE") == pytest.approx(-30.0)


def test_expired_position_settles_from_verified_underlying_close(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    connection = scoreboard.connect_db()
    scoreboard.record_trade_open(connection, trade_id="expired", bot="RIPTIDE", generation=1,
                                 opened_at="2026-09-03T14:30:00-05:00", side="call",
                                 contract_symbol="SPY260903C00774000", entry_price=.14, contracts=3,
                                 entry_bankroll=1000.0)
    runtime = RiptideRuntime(market_view=View(), evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"),
                             telemetry_path=tmp_path / "telemetry.jsonl",
                             daily_history_loader=lambda *args, **kwargs: [{"date": "2026-09-03", "close": 773.17}])
    decision = runtime.evaluate(datetime(2026, 9, 4, 8, 0), connection)
    assert decision.action == "EXIT" and decision.price == 0
    assert "773.17" in decision.reason
    assert scoreboard.total_pnl(connection, "RIPTIDE") == pytest.approx(-42.0)
