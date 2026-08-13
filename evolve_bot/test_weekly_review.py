from __future__ import annotations
import csv
import json
import tempfile
from pathlib import Path
from unittest import mock

import backtest
import bankroll
import engine
import retrain_loop
import shadow
import weekly_review


def _write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_closed_trade_stats_on_empty_rows_returns_none_rates():
    stats = weekly_review._closed_trade_stats([])
    assert stats["n_closed"] == 0
    assert stats["win_rate"] is None
    assert stats["avg_pl_pct"] is None


def test_closed_trade_stats_computes_real_win_rate_and_average():
    rows = [
        {"outcome": "WIN", "pl_pct": "20"},
        {"outcome": "WIN", "pl_pct": "10"},
        {"outcome": "LOSS", "pl_pct": "-50"},
        {"outcome": "OPEN", "pl_pct": ""},  # excluded - not closed
    ]
    stats = weekly_review._closed_trade_stats(rows)
    assert stats["n_closed"] == 3
    assert stats["n_wins"] == 2
    assert stats["n_losses"] == 1
    assert stats["win_rate"] == round(2 / 3, 4)
    assert stats["avg_pl_pct"] == round((20 + 10 - 50) / 3, 2)


def test_shadow_score_calibration_returns_none_averages_without_enough_data():
    # only wins, no losses - not a real comparison
    rows = [{"outcome": "WIN", "model_score": "0.8"}, {"outcome": "WIN", "model_score": "0.9"}]
    calibration = weekly_review._shadow_score_calibration(rows)
    assert calibration["enough_data_to_compare"] is False
    assert calibration["avg_score_on_losses"] is None


def test_shadow_score_calibration_computes_real_averages_on_both_sides():
    rows = [
        {"outcome": "WIN", "model_score": "0.8"},
        {"outcome": "WIN", "model_score": "0.6"},
        {"outcome": "LOSS", "model_score": "0.2"},
        {"outcome": "OPEN", "model_score": "0.5"},  # excluded - not closed
    ]
    calibration = weekly_review._shadow_score_calibration(rows)
    assert calibration["enough_data_to_compare"] is True
    assert calibration["avg_score_on_wins"] == 0.7
    assert calibration["avg_score_on_losses"] == 0.2


def test_gather_review_data_end_to_end_with_isolated_fixture_files():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        trade_path = temp_path / "trades.csv"
        shadow_path = temp_path / "shadow_trades.csv"
        backtest_path = temp_path / "backtest_trades.csv"
        history_path = temp_path / "retrain_history.jsonl"
        bank_path = temp_path / "bankroll.json"

        live_row = {key: "" for key in engine.tradelog.HEADER}
        live_row.update({"trade_id": "T1", "outcome": "WIN", "pl_pct": "15"})
        _write_csv(trade_path, engine.tradelog.HEADER, [live_row])

        shadow_row = {key: "" for key in shadow.HEADER}
        shadow_row.update({"shadow_id": "S1", "outcome": "WIN", "pl_pct": "10", "model_score": "0.7"})
        _write_csv(shadow_path, shadow.HEADER, [shadow_row])

        backtest_row = {key: "" for key in backtest.HEADER}
        backtest_row.update({"trade_id": "BT1", "trading_day": "2026-07-06", "price_source_at_entry": "real"})
        _write_csv(backtest_path, backtest.HEADER, [backtest_row])

        history_path.write_text(json.dumps({"retrained_at": "2026-08-01T00:00:00", "n_rows": 100}) + "\n", encoding="utf-8")

        bankroll.save_state(bank_path, bankroll.default_state())

        with (
            mock.patch.object(engine, "TRADELOG_PATH", trade_path),
            mock.patch.object(shadow, "SHADOW_LOG_PATH", shadow_path),
            mock.patch.object(backtest, "BACKTEST_TRADES_PATH", backtest_path),
            mock.patch.object(retrain_loop, "RETRAIN_HISTORY_PATH", history_path),
            mock.patch.object(engine, "BANKROLL_PATH", bank_path),
        ):
            data = weekly_review.gather_review_data()

        assert data["live_trading"]["n_closed"] == 1
        assert data["live_trading"]["win_rate"] == 1.0
        assert data["live_trading"]["bankroll"]["balance"] == bankroll.STARTING_BALANCE
        assert data["shadow_mode"]["n_total_logged"] == 1
        assert data["backtest_training_data"]["n_rows"] == 1
        assert data["backtest_training_data"]["n_trading_days"] == 1
        assert data["backtest_training_data"]["n_real_priced_rows"] == 1
        assert data["retraining"]["n_retrains_recorded"] == 1
        assert data["retraining"]["most_recent"]["n_rows"] == 100


def test_gather_review_data_handles_completely_missing_files_gracefully():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        with (
            mock.patch.object(engine, "TRADELOG_PATH", temp_path / "nope1.csv"),
            mock.patch.object(shadow, "SHADOW_LOG_PATH", temp_path / "nope2.csv"),
            mock.patch.object(backtest, "BACKTEST_TRADES_PATH", temp_path / "nope3.csv"),
            mock.patch.object(retrain_loop, "RETRAIN_HISTORY_PATH", temp_path / "nope4.jsonl"),
            mock.patch.object(engine, "BANKROLL_PATH", temp_path / "nope5.json"),
        ):
            data = weekly_review.gather_review_data()

    assert data["live_trading"]["n_closed"] == 0
    assert data["shadow_mode"]["n_total_logged"] == 0
    assert data["backtest_training_data"]["n_rows"] == 0
    assert data["retraining"]["n_retrains_recorded"] == 0
    assert data["retraining"]["most_recent"] is None
    # bankroll.load_state fails open to default_state on a missing file
    assert data["live_trading"]["bankroll"]["balance"] == bankroll.STARTING_BALANCE
