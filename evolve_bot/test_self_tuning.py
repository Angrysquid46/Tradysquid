from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import self_tuning


def _closed_row(trade_id: str, outcome: str) -> dict[str, str]:
    return {"trade_id": trade_id, "outcome": outcome}


def _rows(outcomes: list[str]) -> list[dict[str, str]]:
    return [_closed_row(f"T{i}", outcome) for i, outcome in enumerate(outcomes)]


def test_current_position_size_pct_falls_back_to_bankroll_default_with_no_state():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(self_tuning, "TUNING_STATE_PATH", Path(temp) / "nope.json"):
            assert self_tuning.current_position_size_pct() == self_tuning.bankroll.POSITION_SIZE_PCT


def test_current_position_size_pct_reads_last_tuned_value():
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "tuning_state.json"
        state_path.write_text(json.dumps({"position_size_pct": 0.19}), encoding="utf-8")
        with mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path):
            assert self_tuning.current_position_size_pct() == 0.19


def test_evaluate_tuning_refuses_to_act_below_minimum_closed_trades():
    """The core "don't tune on noise" gate - regression guard so this
    never silently drops to a lower threshold that would let a nudge fire
    off 2-3 closed trades."""
    closed = _rows(["WIN"] * 5)
    with tempfile.TemporaryDirectory() as temp:
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", Path(temp) / "state.json"),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", Path(temp) / "log.jsonl"),
        ):
            result = self_tuning.evaluate_tuning(closed)
        assert result["status"] == "not enough real closed trades yet"
        assert result["n_closed"] == 5


def test_evaluate_tuning_nudges_up_on_a_strong_trailing_win_rate():
    closed = _rows(["WIN"] * 7 + ["LOSS"] * 3)  # 70% trailing win rate
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        log_path = Path(temp) / "log.jsonl"
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", log_path),
        ):
            result = self_tuning.evaluate_tuning(closed)

        assert result["status"] == "tuned"
        expected = round(self_tuning.bankroll.POSITION_SIZE_PCT + self_tuning.STEP, 4)
        assert result["position_size_pct"] == expected

        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["position_size_pct"] == expected
        assert saved_state["last_considered_trade_id"] == "T9"

        log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(log_lines) == 1
        entry = json.loads(log_lines[0])
        assert "change" in entry and "reasoning" in entry


def test_evaluate_tuning_nudges_down_on_a_weak_trailing_win_rate():
    closed = _rows(["LOSS"] * 7 + ["WIN"] * 3)  # 30% trailing win rate
    with tempfile.TemporaryDirectory() as temp:
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", Path(temp) / "state.json"),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", Path(temp) / "log.jsonl"),
        ):
            result = self_tuning.evaluate_tuning(closed)

        assert result["status"] == "tuned"
        expected = round(self_tuning.bankroll.POSITION_SIZE_PCT - self_tuning.STEP, 4)
        assert result["position_size_pct"] == expected


def test_evaluate_tuning_makes_no_change_inside_the_dead_zone():
    closed = _rows(["WIN"] * 5 + ["LOSS"] * 5)  # exactly 50% - inside the dead zone
    with tempfile.TemporaryDirectory() as temp:
        log_path = Path(temp) / "log.jsonl"
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", Path(temp) / "state.json"),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", log_path),
        ):
            result = self_tuning.evaluate_tuning(closed)

        assert result["status"] == "evaluated, no change"
        assert result["position_size_pct"] == self_tuning.bankroll.POSITION_SIZE_PCT
        assert not log_path.exists()


def test_evaluate_tuning_never_nudges_past_the_hard_ceiling():
    closed = _rows(["WIN"] * 10)
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        state_path.write_text(
            json.dumps({"position_size_pct": self_tuning.MAX_POSITION_SIZE_PCT, "last_considered_trade_id": "T-1"}),
            encoding="utf-8",
        )
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", Path(temp) / "log.jsonl"),
        ):
            result = self_tuning.evaluate_tuning(closed)

        assert result["position_size_pct"] <= self_tuning.MAX_POSITION_SIZE_PCT


def test_evaluate_tuning_never_nudges_past_the_hard_floor():
    closed = _rows(["LOSS"] * 10)
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        state_path.write_text(
            json.dumps({"position_size_pct": self_tuning.MIN_POSITION_SIZE_PCT, "last_considered_trade_id": "T-1"}),
            encoding="utf-8",
        )
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", Path(temp) / "log.jsonl"),
        ):
            result = self_tuning.evaluate_tuning(closed)

        assert result["position_size_pct"] >= self_tuning.MIN_POSITION_SIZE_PCT


def test_evaluate_tuning_does_not_reevaluate_the_same_trade_history_twice():
    """Calling evaluate_tuning again with the exact same closed rows (no
    new trade since the last evaluation) must not fire a second nudge -
    same idempotency guarantee retrain_loop.should_retrain provides for
    the training data side."""
    closed = _rows(["WIN"] * 7 + ["LOSS"] * 3)
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        log_path = Path(temp) / "log.jsonl"
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", log_path),
        ):
            first = self_tuning.evaluate_tuning(closed)
            second = self_tuning.evaluate_tuning(closed)

        assert first["status"] == "tuned"
        assert second["status"] == "already evaluated this trade history"
        log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(log_lines) == 1


def test_evaluate_tuning_reevaluates_once_a_new_trade_closes():
    closed = _rows(["WIN"] * 7 + ["LOSS"] * 3)
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        log_path = Path(temp) / "log.jsonl"
        with (
            mock.patch.object(self_tuning, "TUNING_STATE_PATH", state_path),
            mock.patch.object(self_tuning, "SELF_TUNING_LOG_PATH", log_path),
        ):
            self_tuning.evaluate_tuning(closed)
            closed_plus_one = closed + [_closed_row("T10", "LOSS")]
            second = self_tuning.evaluate_tuning(closed_plus_one)

        assert second["status"] in ("tuned", "evaluated, no change")
        log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(log_lines) >= 1
