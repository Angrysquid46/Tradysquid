from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import logic_state


def test_current_exit_signal_matches_the_live_default_with_no_override():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", Path(temp) / "nope.json"):
            got = logic_state.current_exit_signal(1.0, 1.6, 100.0, 60.0)

        expected = logic_state.s.spy_0dte_exit_signal(1.0, 1.6, 100.0, 60.0)
        assert got == expected


def test_current_exit_signal_uses_the_applied_override_when_one_exists():
    with tempfile.TemporaryDirectory() as temp:
        override_path = Path(temp) / "active_exit_override.json"
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path):
            logic_state.save_active_override(
                {"stop_pct": 0.20, "target_pct": 0.50, "floor_pct": -10.0, "floor_trigger_pct": 30.0}
            )
            got = logic_state.current_exit_signal(1.0, 0.79, 100.0, 5.0)  # -21%, past a 20% stop

    assert got[0] == "STOP OUT"


def test_current_stop_pct_matches_the_live_default_with_no_override():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", Path(temp) / "nope.json"):
            assert logic_state.current_stop_pct() == logic_state.s.SPY_0DTE_STOP_PCT


def test_current_stop_pct_uses_the_applied_override_when_one_exists():
    with tempfile.TemporaryDirectory() as temp:
        override_path = Path(temp) / "active_exit_override.json"
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path):
            logic_state.save_active_override(
                {"stop_pct": 0.20, "target_pct": 0.50, "floor_pct": -10.0, "floor_trigger_pct": 30.0}
            )
            assert logic_state.current_stop_pct() == 0.20


def test_save_load_clear_round_trip():
    with tempfile.TemporaryDirectory() as temp:
        override_path = Path(temp) / "active_exit_override.json"
        with mock.patch.object(logic_state, "ACTIVE_OVERRIDE_PATH", override_path):
            assert logic_state.load_active_override() is None

            logic_state.save_active_override({"stop_pct": 0.2, "target_pct": 0.3, "floor_pct": -5.0, "floor_trigger_pct": 15.0})
            loaded = logic_state.load_active_override()
            assert loaded["stop_pct"] == 0.2

            logic_state.clear_active_override()
            assert logic_state.load_active_override() is None
