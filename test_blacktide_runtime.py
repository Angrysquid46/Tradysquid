from datetime import datetime, timedelta

import pytest

import scoreboard
from bots.blacktide.runtime import BlacktideRuntime


NOW = datetime(2026, 8, 25, 10, 0)


class View:
    bid = 1.0
    def market_as_of(self, timestamp): return {"tier": "A", "quote": {"last": 500}}
    def bars_as_of(self, timestamp, lookback_minutes=120):
        return [{"close": 500 + i * .2} for i in range(25)]
    def options_as_of(self, timestamp):
        return {"tier": "A", "contracts": [{
            "option_symbol": "SPY_TEST", "side": "call",
            "expiration": timestamp.date().isoformat(), "bid": self.bid, "ask": 1.05,
            "delta": .5, "volume": 100, "open_interest": 100,
        }]}


def test_runtime_records_one_immutable_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    db = scoreboard.connect_db()
    view = View()
    runtime = BlacktideRuntime(market_view=view)
    assert runtime.evaluate(NOW, db).action == "ENTER"
    assert scoreboard.current_position_status(db, "BLACKTIDE") is not None
    view.bid = 1.40
    assert runtime.evaluate(NOW + timedelta(minutes=1), db).action == "EXIT"
    assert scoreboard.trade_count(db, "BLACKTIDE") == 1
    assert scoreboard.total_pnl(db, "BLACKTIDE") == pytest.approx(70.0)
    assert scoreboard.current_position_status(db, "BLACKTIDE") is None
