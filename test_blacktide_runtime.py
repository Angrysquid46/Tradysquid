from datetime import datetime, timedelta

import pytest

import scoreboard
from bots.blacktide import runtime as blacktide_runtime
from bots.blacktide.runtime import BlacktideRuntime
from bots.blacktide.engine import Decision
from bots.blacktide.evolution import EvolutionLoop


NOW = datetime(2026, 8, 25, 10, 0)


class View:
    bid = 1.0
    def market_as_of(self, timestamp): return {"tier": "A", "quote": {"last": 500}}
    def bars_as_of(self, timestamp, lookback_minutes=120):
        return [{"close": 500 + i * .35, "high": 500.2 + i * .35,
                 "low": 499.8 + i * .35, "volume": 1000 + i * 30}
                for i in range(60)]
    def options_as_of(self, timestamp):
        return {"tier": "A", "contracts": [{
            "option_symbol": "SPY_TEST", "side": "call",
            "expiration": timestamp.date().isoformat(), "bid": self.bid, "ask": 1.05,
            "delta": .5, "gamma": .01, "theta": -.05, "iv": .2,
            "data_class": "VERIFIED_REAL", "volume": 100, "open_interest": 100,
        }]}


def test_runtime_records_one_immutable_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    db = scoreboard.connect_db()
    view = View()
    runtime = BlacktideRuntime(market_view=view, evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"))
    assert runtime.evaluate(NOW, db).action == "ENTER"
    assert scoreboard.current_position_status(db, "BLACKTIDE") is not None
    view.bid = 1.40
    assert runtime.evaluate(NOW + timedelta(minutes=1), db).action == "EXIT"
    assert scoreboard.trade_count(db, "BLACKTIDE") == 1
    assert scoreboard.total_pnl(db, "BLACKTIDE") == pytest.approx(70.0)
    assert scoreboard.current_position_status(db, "BLACKTIDE") is None
    outcome = EvolutionLoop(tmp_path / "outcomes.jsonl").load()[0]
    assert outcome.family != "RECOVERED_OR_PRIVATE"
    assert outcome.exit_reason == "take-profit reached"
    assert outcome.held_minutes == 1.0


def test_restart_recovers_open_position_and_cannot_double_open(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    db = scoreboard.connect_db()
    view = View()
    evolution = EvolutionLoop(tmp_path / "outcomes.jsonl")
    first = BlacktideRuntime(market_view=view, evolution=evolution)
    assert first.evaluate(NOW, db).action == "ENTER"
    restarted = BlacktideRuntime(market_view=view, evolution=evolution)
    result = restarted.evaluate(NOW + timedelta(minutes=1), db)
    assert result.action == "NO_ACTION"
    assert restarted.engine.position is not None
    assert db.execute("SELECT COUNT(*) FROM official_trades").fetchone()[0] == 1


def test_restart_recovers_later_generation_after_bust(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    db = scoreboard.connect_db()
    scoreboard.record_generation_event(
        db, bot="BLACKTIDE", generation=1, event="BUSTED", minimum_qualifying_cost=1001,
    )
    scoreboard.record_generation_event(db, bot="BLACKTIDE", generation=2, event="STARTED")
    restarted = BlacktideRuntime(market_view=View(), evolution=EvolutionLoop(tmp_path / "outcomes.jsonl"))
    restarted.recover(db)
    assert restarted.engine.generation == 2
    assert restarted.engine.position is None


def test_runtime_records_and_coalesces_no_action_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(blacktide_runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(blacktide_runtime, "DECISION_LOG_PATH", tmp_path / "decision-audit.jsonl")
    monkeypatch.setattr(blacktide_runtime, "DECISION_STATE_PATH", tmp_path / "decision-audit-state.json")
    decision = Decision("NO_ACTION", "no approved transition in FAILED_EXPANSION")
    BlacktideRuntime._record_decision(decision, NOW)
    BlacktideRuntime._record_decision(decision, NOW + timedelta(minutes=1))
    lines = (tmp_path / "decision-audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert '"action": "NO_ACTION"' in lines[0]
