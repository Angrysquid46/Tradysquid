"""GROK competitor tests — isolation, rules, and basic decision behavior."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bots.grok.contract_selection import select_contract
from bots.grok.engine import evaluate_entry, evaluate_exit
from bots.grok.preflight import run_preflight
from bots.grok.sizing import decide_contracts


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
    assert "end-of-day" in decision.reason


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
