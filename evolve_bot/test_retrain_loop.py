from __future__ import annotations
import json
import tempfile
from pathlib import Path
from unittest import mock

import retrain_loop


def test_should_retrain_is_true_with_no_prior_state():
    current = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    assert retrain_loop.should_retrain(current, None) is True


def test_should_retrain_is_false_when_nothing_changed():
    current = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    last_state = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    assert retrain_loop.should_retrain(current, last_state) is False


def test_should_retrain_is_true_when_row_count_changed():
    current = {"n_rows": 150, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    last_state = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    assert retrain_loop.should_retrain(current, last_state) is True


def test_should_retrain_is_true_when_a_new_day_appears():
    current = {"n_rows": 100, "n_days": 6, "days": ["2026-07-06", "2026-07-07", "2026-07-08"]}
    last_state = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"]}
    assert retrain_loop.should_retrain(current, last_state) is True


def test_should_retrain_is_true_when_row_content_changed_but_count_and_days_did_not():
    """Regression guard for the real bug found from live behavior: a
    real-price backfill (Robinhood data replacing a synthetic-priced row
    for a day/candidate already in the file) changes existing rows'
    pl_pct/outcome without changing row count or the day set - the old
    row-count/day-set-only check silently missed this, should_retrain
    returned False on genuinely changed data."""
    current = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"], "file_hash": "abc123"}
    last_state = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"], "file_hash": "def456"}
    assert retrain_loop.should_retrain(current, last_state) is True


def test_should_retrain_is_false_when_file_hash_is_identical():
    current = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"], "file_hash": "abc123"}
    last_state = {"n_rows": 100, "n_days": 5, "days": ["2026-07-06", "2026-07-07"], "file_hash": "abc123"}
    assert retrain_loop.should_retrain(current, last_state) is False


def test_current_data_signature_includes_a_real_file_hash():
    with tempfile.TemporaryDirectory() as temp:
        csv_path = Path(temp) / "backtest_trades.csv"
        csv_path.write_text("trade_id,trading_day\nBT1,2026-07-06\n", encoding="utf-8")
        with mock.patch.object(retrain_loop.backtest, "BACKTEST_TRADES_PATH", csv_path):
            signature = retrain_loop._current_data_signature()
    assert signature["file_hash"] is not None
    assert isinstance(signature["file_hash"], str)


def test_current_data_signature_file_hash_is_none_when_file_is_missing():
    with tempfile.TemporaryDirectory() as temp:
        missing_path = Path(temp) / "nope.csv"
        with mock.patch.object(retrain_loop.backtest, "BACKTEST_TRADES_PATH", missing_path):
            signature = retrain_loop._current_data_signature()
    assert signature["file_hash"] is None


def test_run_retrain_cycle_skips_when_data_is_unchanged():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        state_path = temp_path / "retrain_state.json"
        history_path = temp_path / "retrain_history.jsonl"
        signature = {"n_rows": 40, "n_days": 3, "days": ["2026-07-06", "2026-07-07", "2026-07-08"]}
        state_path.write_text(json.dumps({**signature, "last_retrain_at": "2026-08-12T00:00:00"}), encoding="utf-8")
        with (
            mock.patch.object(retrain_loop, "RETRAIN_STATE_PATH", state_path),
            mock.patch.object(retrain_loop, "RETRAIN_HISTORY_PATH", history_path),
            mock.patch.object(retrain_loop, "_current_data_signature", return_value=signature),
            mock.patch.object(retrain_loop.train, "run_training") as fake_train,
        ):
            result = retrain_loop.run_retrain_cycle()

    assert result["status"] == "skipped - no new data"
    fake_train.assert_not_called()
    assert not history_path.exists()


def test_run_retrain_cycle_retrains_and_records_history_when_data_changed():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        state_path = temp_path / "retrain_state.json"
        history_path = temp_path / "retrain_history.jsonl"
        signature = {"n_rows": 60, "n_days": 4, "days": ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]}
        fake_result = {"status": "ok", "n_train_rows": 50, "n_test_rows": 10, "metrics": {"accuracy": 0.7}}
        with (
            mock.patch.object(retrain_loop, "RETRAIN_STATE_PATH", state_path),
            mock.patch.object(retrain_loop, "RETRAIN_HISTORY_PATH", history_path),
            mock.patch.object(retrain_loop, "_current_data_signature", return_value=signature),
            mock.patch.object(retrain_loop.train, "run_training", return_value=fake_result) as fake_train,
        ):
            result = retrain_loop.run_retrain_cycle()

        assert result["status"] == "retrained"
        assert result["n_train_rows"] == 50
        fake_train.assert_called_once()

        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["n_rows"] == 60
        assert "last_retrain_at" in saved_state

        history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(history_lines) == 1
        history_entry = json.loads(history_lines[0])
        assert history_entry["n_rows"] == 60
        assert history_entry["result"] == fake_result


def test_run_retrain_cycle_appends_to_existing_history_rather_than_overwriting():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        state_path = temp_path / "retrain_state.json"
        history_path = temp_path / "retrain_history.jsonl"
        history_path.write_text(json.dumps({"retrained_at": "2026-08-01T00:00:00", "n_rows": 30}) + "\n", encoding="utf-8")
        signature = {"n_rows": 60, "n_days": 4, "days": ["2026-07-06"]}
        with (
            mock.patch.object(retrain_loop, "RETRAIN_STATE_PATH", state_path),
            mock.patch.object(retrain_loop, "RETRAIN_HISTORY_PATH", history_path),
            mock.patch.object(retrain_loop, "_current_data_signature", return_value=signature),
            mock.patch.object(retrain_loop.train, "run_training", return_value={"status": "ok"}),
        ):
            retrain_loop.run_retrain_cycle()

        history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(history_lines) == 2
