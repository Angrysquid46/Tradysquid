"""Phase 4: LightGBM training with walk-forward validation.

"Walk-forward" here means the test split is always the CHRONOLOGICALLY
LATEST trading days, never a random sample - a random split would let the
model train on a day and get tested on an earlier day, which isn't
something that could ever happen live (a live model never sees the
future). Splitting happens by whole trading_day, not by row, because rows
from the same day share the same real price path and are highly
correlated - splitting mid-day would leak that day's outcome across the
train/test boundary.

Binary classification target: outcome == "WIN" (1) vs. LOSS/SCRATCH (0).
A probability-of-win score is what Phase 7 (live scoring) actually needs
to filter/rank candidates with.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

import backtest
import features
import metrics

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
MODEL_PATH = MODELS_DIR / "latest_model.txt"
METADATA_PATH = MODELS_DIR / "latest_metadata.json"

# Deliberately conservative for a small dataset (515 rows across 27
# trading days as of 2026-08-12, and the 27 days are the real unit of
# independent information here, not the 515 rows - see run_training's
# docstring). Shallow trees and a high min_child_samples resist
# memorizing individual days; revisit once real data volume grows.
LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": ["binary_logloss", "auc"],
    "num_leaves": 7,
    "min_child_samples": 15,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "verbose": -1,
    "seed": 42,
}
NUM_BOOST_ROUND = 50


def load_training_rows() -> list[dict[str, str]]:
    """Backtest rows only for now - tradelog.py's closed live rows will
    fold into this once the bot has real closed trades (zero as of
    2026-08-12, not wired to Discord yet). No premature merging logic for
    a data source that doesn't have any rows yet."""
    if not backtest.BACKTEST_TRADES_PATH.exists():
        return []
    with backtest.BACKTEST_TRADES_PATH.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def walk_forward_split(
    rows: list[dict[str, str]], test_fraction: float = 0.2
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Splits by whole trading_day, chronologically - the last
    test_fraction of DAYS (not rows) become the test set. At least one
    day on each side, so a tiny dataset never produces an empty split."""
    days = sorted({row["trading_day"] for row in rows})
    if len(days) < 2:
        return rows, []
    split_index = max(1, min(len(days) - 1, round(len(days) * (1 - test_fraction))))
    train_days = set(days[:split_index])
    test_days = set(days[split_index:])
    train_rows = [row for row in rows if row["trading_day"] in train_days]
    test_rows = [row for row in rows if row["trading_day"] in test_days]
    return train_rows, test_rows


def train_model(X_train: list[list[float]], y_train: list[int]) -> lgb.Booster:
    train_set = lgb.Dataset(
        np.array(X_train, dtype=float),
        label=np.array(y_train, dtype=int),
        feature_name=features.FEATURE_NAMES,
        categorical_feature=features.CATEGORICAL_COLUMNS,
    )
    return lgb.train(LGBM_PARAMS, train_set, num_boost_round=NUM_BOOST_ROUND)


def evaluate(model: lgb.Booster, X_test: list[list[float]], y_test: list[int]) -> dict[str, Any]:
    if not X_test:
        return {"n_test": 0}
    y_prob = list(model.predict(np.array(X_test, dtype=float)))
    y_pred = [1 if p >= 0.5 else 0 for p in y_prob]
    return {
        "n_test": len(y_test),
        "baseline_win_rate": round(sum(y_test) / len(y_test), 4),
        "accuracy": round(metrics.accuracy_score(y_test, y_pred), 4),
        "precision": round(metrics.precision_score(y_test, y_pred), 4),
        "recall": round(metrics.recall_score(y_test, y_pred), 4),
        "log_loss": round(metrics.log_loss(y_test, y_prob), 4),
        "auc": (lambda a: round(a, 4) if a is not None else None)(metrics.roc_auc(y_test, y_prob)),
    }


def run_training(test_fraction: float = 0.2) -> dict[str, Any]:
    """Loads rows, walk-forward splits, trains, evaluates, and saves the
    model + metadata to evolve_bot/models/ (gitignored - a trained model
    is a build artifact, not source).

    A note on statistical power, deliberately surfaced here rather than
    left implicit: 515 rows is NOT 515 independent observations. Every
    row shares one of only 27 real trading days with several other rows
    (same day's price path replayed under different candidates/exit
    variants), so the real sample size for "did the model learn something
    that generalizes to a new day" is closer to 27 than 515. Report these
    metrics as an early, noisy read - not a validated edge - until real
    data volume (more real days pulled, plus real live trades once the
    bot goes live) grows well past this."""
    rows = load_training_rows()
    if len(rows) < 10:
        return {"status": "not enough rows to train", "n_rows": len(rows)}

    train_rows, test_rows = walk_forward_split(rows, test_fraction)
    X_train, y_train, vocabulary = features.build_dataset(train_rows)
    X_test, y_test, _ = features.build_dataset(test_rows, vocabulary=vocabulary)

    model = train_model(X_train, y_train)
    eval_metrics = evaluate(model, X_test, y_test)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_PATH))
    metadata = {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "feature_names": features.FEATURE_NAMES,
        "categorical_columns": features.CATEGORICAL_COLUMNS,
        "vocabulary": vocabulary,
        "n_train_rows": len(train_rows),
        "n_test_rows": len(test_rows),
        "train_days": sorted({row["trading_day"] for row in train_rows}),
        "test_days": sorted({row["trading_day"] for row in test_rows}),
        "lgbm_params": LGBM_PARAMS,
        "num_boost_round": NUM_BOOST_ROUND,
        "metrics": eval_metrics,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "n_train_rows": len(train_rows),
        "n_test_rows": len(test_rows),
        "n_train_days": len(metadata["train_days"]),
        "n_test_days": len(metadata["test_days"]),
        "metrics": eval_metrics,
        "model_path": str(MODEL_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(run_training(), indent=2))
