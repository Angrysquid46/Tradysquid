from datetime import datetime, timedelta

import pytest

import scoreboard
from bots.riptide.evolution import EvolutionLoop
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
    runtime = RiptideRuntime(market_view=view, evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"))
    assert runtime.evaluate(NOW, connection).action == "ENTER"
    assert scoreboard.current_position_status(connection, "RIPTIDE") is not None
    view.bid = 1.55
    assert runtime.evaluate(NOW + timedelta(minutes=1), connection).action == "EXIT"
    assert scoreboard.trade_count(connection, "RIPTIDE") == 1
    assert scoreboard.total_pnl(connection, "RIPTIDE") == pytest.approx(150.0)
    assert EvolutionLoop(tmp_path / "outcomes.jsonl").load()[0].exit_reason == "take-profit reached"
