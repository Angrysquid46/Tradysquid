from __future__ import annotations
import csv
import json
import tempfile
from pathlib import Path
from unittest import mock

import backtest
import features
import train


def _row(trading_day: str, index: int, outcome: str) -> dict[str, str]:
    row = {key: "" for key in backtest.HEADER}
    row.update({
        "trade_id": f"BT-{trading_day}-{index}",
        "trading_day": trading_day,
        "variant_label": ["tight_30_40", "live_default_50_50"][index % 2],
        "call_or_put": ["call", "put"][index % 2],
        "strike": "600",
        "option_symbol": f"SPY{trading_day.replace('-', '')}C00600000",
        "entry_price": "0.5",
        "price_source_at_entry": "synthetic",
        "delta_at_entry": str(0.45 + 0.01 * index),
        "iv_at_entry": "0.18",
        "spot_at_entry": "600.0",
        "market_condition": "CHOPPY / LOW VOL",
        "regime": "BULLISH / CONTROLLED",
        "vix_at_entry": str(15.0 + index),
        "sentiment_at_entry": str(0.01 * index),
        "put_call_ratio_at_entry": "",
        "thesis": "test thesis",
        "stop_pct": "0.5", "target_pct": "0.5", "floor_pct": "-15.0", "floor_trigger_pct": "30.0",
        "outcome": outcome,
        "exit_price": "0.6", "last_signal": "TAKE PROFIT" if outcome == "WIN" else "STOP OUT",
        "pl_pct": "10" if outcome == "WIN" else "-10",
        "max_favorable_pct": "10", "max_adverse_pct": "-5",
    })
    return row


def _synthetic_rows(n_days: int = 6, rows_per_day: int = 10) -> list[dict[str, str]]:
    rows = []
    for day_index in range(n_days):
        day = f"2026-07-{6 + day_index:02d}"
        for i in range(rows_per_day):
            outcome = "WIN" if (day_index + i) % 3 != 0 else "LOSS"
            rows.append(_row(day, i, outcome))
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=backtest.HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_walk_forward_split_never_splits_a_day_across_train_and_test():
    rows = _synthetic_rows(n_days=6, rows_per_day=5)
    train_rows, test_rows = train.walk_forward_split(rows, test_fraction=0.2)
    train_days = {r["trading_day"] for r in train_rows}
    test_days = {r["trading_day"] for r in test_rows}
    assert train_days.isdisjoint(test_days)


def test_walk_forward_split_test_days_are_the_chronologically_latest():
    rows = _synthetic_rows(n_days=6, rows_per_day=5)
    train_rows, test_rows = train.walk_forward_split(rows, test_fraction=0.2)
    train_days = {r["trading_day"] for r in train_rows}
    test_days = {r["trading_day"] for r in test_rows}
    assert max(train_days) < min(test_days)


def test_walk_forward_split_handles_a_single_day_by_putting_everything_in_train():
    rows = _synthetic_rows(n_days=1, rows_per_day=5)
    train_rows, test_rows = train.walk_forward_split(rows, test_fraction=0.2)
    assert len(train_rows) == 5
    assert test_rows == []


def test_train_model_and_evaluate_produce_a_usable_probability_score():
    rows = _synthetic_rows(n_days=8, rows_per_day=10)
    train_rows, test_rows = train.walk_forward_split(rows, test_fraction=0.25)
    X_train, y_train, vocab = features.build_dataset(train_rows)
    X_test, y_test, _ = features.build_dataset(test_rows, vocabulary=vocab)

    model = train.train_model(X_train, y_train)
    result = train.evaluate(model, X_test, y_test)

    assert result["n_test"] == len(test_rows)
    assert 0.0 <= result["accuracy"] <= 1.0
    assert result["log_loss"] >= 0.0


def test_evaluate_handles_an_empty_test_set():
    model = train.train_model(*features.build_dataset(_synthetic_rows(n_days=3, rows_per_day=10))[:2])
    result = train.evaluate(model, [], [])
    assert result == {"n_test": 0}


def test_load_training_rows_returns_empty_list_when_the_file_does_not_exist():
    with tempfile.TemporaryDirectory() as temp:
        missing_path = Path(temp) / "nope.csv"
        with mock.patch.object(backtest, "BACKTEST_TRADES_PATH", missing_path):
            assert train.load_training_rows() == []


def test_run_training_end_to_end_saves_a_model_and_metadata():
    rows = _synthetic_rows(n_days=10, rows_per_day=8)
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        csv_path = temp_path / "backtest_trades.csv"
        _write_csv(csv_path, rows)
        models_dir = temp_path / "models"
        with (
            mock.patch.object(backtest, "BACKTEST_TRADES_PATH", csv_path),
            mock.patch.object(train, "MODELS_DIR", models_dir),
            mock.patch.object(train, "MODEL_PATH", models_dir / "latest_model.txt"),
            mock.patch.object(train, "METADATA_PATH", models_dir / "latest_metadata.json"),
        ):
            result = train.run_training(test_fraction=0.2)

        assert result["status"] == "ok"
        assert (models_dir / "latest_model.txt").exists()
        metadata = json.loads((models_dir / "latest_metadata.json").read_text(encoding="utf-8"))
        assert metadata["n_train_rows"] == result["n_train_rows"]
        assert set(metadata["train_days"]).isdisjoint(set(metadata["test_days"]))
        assert metadata["metrics"]["n_test"] == result["n_test_rows"]


def test_run_training_reports_not_enough_rows_on_a_tiny_dataset():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        csv_path = temp_path / "backtest_trades.csv"
        _write_csv(csv_path, _synthetic_rows(n_days=1, rows_per_day=3))
        with mock.patch.object(backtest, "BACKTEST_TRADES_PATH", csv_path):
            result = train.run_training()
    assert result["status"] == "not enough rows to train"
