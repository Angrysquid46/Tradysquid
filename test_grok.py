"""GROK competitor tests — isolation, rules, and basic decision behavior."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bots.grok.contract_selection import select_contract
from bots.grok.engine import evaluate_entry, evaluate_exit
from bots.grok.preflight import run_preflight
from bots.grok.sizing import decide_contracts
from bots.grok.evolution import derive_policy


def test_grok_package_exists():
    root = Path(__file__).resolve().parent / "bots" / "grok"
    assert (root / "AGENTS.md").exists()
    assert (root / "engine.py").exists()
    assert (root / "runtime.py").exists()


def test_no_private_competitor_imports():
    """Static check: GROK must not import blacktide/riptide/surge private modules."""
    root = Path(__file__).resolve().parent / "bots" / "grok"
    forbidden = ("bots.blacktide", "bots.riptide", "bots.surge", "blacktide.", "riptide.", "surge.")
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for f in forbidden:
                        assert f not in alias.name, f"{path} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for f in forbidden:
                    assert f not in mod, f"{path} imports from {mod}"


def test_sizing_respects_bankroll():
    assert decide_contracts(2.50, 1000.0, 0.7, 0.05) >= 1
    assert decide_contracts(15.0, 1000.0, 0.9, 0.05) == 0  # $1500 > $1000
    assert decide_contracts(0.50, 40.0, 0.5, 0.12) == 0  # $50 > $40


def test_contract_selection_filters_bad_spreads():
    chain = [
        {"symbol": "SPY250830C00500000", "option_type": "CALL", "strike": 500,
         "bid": 1.0, "ask": 1.8, "volume": 200, "open_interest": 500, "delta": 0.4},
        {"symbol": "SPY250830C00505000", "option_type": "CALL", "strike": 505,
         "bid": 0.90, "ask": 0.95, "volume": 300, "open_interest": 800, "delta": 0.35},
    ]
    selected = select_contract("CALL", chain, 1000.0, 0.7)
    assert selected is not None
    assert selected.symbol == "SPY250830C00505000"  # tighter spread wins


def test_entry_no_action_without_features():
    decision = evaluate_entry({}, [], 1000.0)
    assert decision.action == "NO_ACTION"


def test_exit_eod_flatten():
    decision = evaluate_exit(
        {"entry_price": 1.0, "side": "CALL"},
        {},
        current_bid=1.1,
        minutes_held=10,
        minutes_to_close=5,
    )
    assert decision.action == "EXIT"
    assert "eod" in decision.reason.lower() or "end-of-day" in decision.reason.lower()


def test_exit_never_claims_fill_without_real_bid():
    decision = evaluate_exit(
        {"entry_price": 1.0, "side": "CALL"}, {}, current_bid=0,
        minutes_held=200, minutes_to_close=0,
    )
    assert decision.action == "HOLD"
    assert "real bid" in decision.reason


def test_preflight_fails_closed():
    result = run_preflight(
        scoreboard_available=False,
        market_data_available=True,
        today_0dte_available=True,
        provider_reachable=True,
        no_open_position=True,
        session_open=True,
    )
    assert result.ok is False
    assert any("scoreboard" in f for f in result.failures)


def test_scoreboard_knows_grok():
    import scoreboard as sb
    assert "GROK" in sb.BOTS


def test_runtime_starts_idle_when_session_is_closed(monkeypatch):
    import scoreboard as sb
    import bots.grok.runtime as runtime_module

    captured = {}
    original_preflight = runtime_module.run_preflight
    monkeypatch.setattr(sb, "current_position_status", lambda *_: None)

    def fake_preflight(**kwargs):
        captured.update(kwargs)
        return original_preflight(**kwargs)

    monkeypatch.setattr(runtime_module, "run_preflight", fake_preflight)
    runtime = runtime_module.GrokRuntime.__new__(runtime_module.GrokRuntime)
    runtime.sb = object()
    runtime.provider_ok = lambda: True
    runtime.is_session_open = lambda: False

    assert runtime.preflight() is True
    assert captured["session_open"] is True


def test_runtime_manages_open_position_after_close_with_direct_quote(monkeypatch):
    import scoreboard as sb
    import bots.grok.runtime as runtime_module
    from datetime import datetime, timezone

    position={"trade_id":"g1","contract_symbol":"SPY260904C00770000","entry_price":1.0,
              "contracts":1,"side":"CALL","opened_at":datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(sb,"current_position_status",lambda *_:position)
    monkeypatch.setattr(sb,"current_bankroll",lambda *_:1000.0)
    monkeypatch.setattr(sb,"current_generation",lambda *_:1)
    runtime=runtime_module.GrokRuntime.__new__(runtime_module.GrokRuntime)
    runtime.sb=object(); runtime.is_session_open=lambda:False; runtime.get_features=lambda:{}
    runtime.get_chain=lambda:[]; runtime.get_contract_quote=lambda symbol:{"bid":1.10}
    runtime.minutes_to_close=lambda:0; runtime._parameters=lambda:{}
    closed=[]; runtime._close_trade=lambda pos,bid,reason:closed.append((bid,reason))
    runtime._record_cycle=lambda decision,**kwargs:decision
    decision=runtime.cycle()
    assert decision.action=="EXIT"
    assert closed==[(1.10,"eod flatten")]


def test_scheduler_runtime_uses_cross_thread_scoreboard_connection(monkeypatch):
    import bots.grok.scheduler as scheduler_module

    captured = {}

    class FakeAdapter:
        features = chain = underlying = contract_quote = is_session_open = minutes_to_close = provider_ok = staticmethod(lambda *args: None)

    class FakeRuntime:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    def fake_connect_db(**kwargs):
        captured["connect_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(scheduler_module, "GrokMarketAdapter", FakeAdapter)
    monkeypatch.setattr(scheduler_module, "GrokRuntime", FakeRuntime)
    monkeypatch.setattr(scheduler_module.scoreboard, "connect_db", fake_connect_db)

    scheduler_module.build_runtime()
    assert captured["connect_kwargs"] == {"check_same_thread": False}


def test_scheduler_records_strategy_neutral_cycle_health(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    import bots.grok.scheduler as scheduler_module

    class Connection:
        def close(self):
            pass

    class Runtime:
        def cycle(self):
            return SimpleNamespace(action="NO_ACTION", private_detail="must not leak")

    health_path = tmp_path / "cycle-health.json"
    monkeypatch.setattr(scheduler_module, "CYCLE_HEALTH_PATH", health_path)
    monkeypatch.setattr(scheduler_module.scoreboard, "connect_db", lambda: Connection())
    monkeypatch.setattr(scheduler_module.scoreboard, "current_position_status", lambda *_: None)
    monkeypatch.setattr(scheduler_module, "cycle_allowed", lambda *_: True)

    scheduler = scheduler_module.build_scheduler(Runtime())
    scheduler.get_jobs()[0].func()
    payload = json.loads(health_path.read_text(encoding="utf-8"))

    assert payload["status"] == "COMPLETED"
    assert payload["action"] == "NO_ACTION"
    assert set(payload) == {"observed_at", "status", "action"}


def test_grok_learning_penalizes_stable_loser_and_cuts_risk():
    trades=[{"family":"tape_bias","return_pct":-.10} for _ in range(12)]
    params,evidence=derive_policy(trades,{})
    assert params["family_bias"]["tape_bias"]<0
    assert params["risk_multiplier"]==pytest.approx(.35)
    assert params["min_confidence_to_enter"]>.30
    assert evidence["families"]["tape_bias"]["status"]=="PROMOTED"


def test_grok_family_bias_changes_live_candidate_selection():
    features={"ret_3m":.001,"ret_5m":.001,"rsi_14":55,"adx_14":20,
              "bb_width":.01,"vwap_distance_pct":.0002,"relative_volume":1.0}
    chain=[{"symbol":"SPY260904C00770000"}]
    baseline=evaluate_entry(features,chain,1000)
    learned=evaluate_entry(features,chain,1000,{"family_bias":{baseline.family:-.22}})
    assert learned.family!=baseline.family or learned.confidence<baseline.confidence


def test_grok_learned_risk_multiplier_controls_live_sizing():
    normal=decide_contracts(.50,1000,.8,.05,{"risk_multiplier":1.0})
    defensive=decide_contracts(.50,1000,.8,.05,{"risk_multiplier":.35})
    assert 1<=defensive<normal
