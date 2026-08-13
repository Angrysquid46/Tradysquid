"""Turns a labeled training row (from backtest_trades.csv, and eventually
tradelog.py's closed live rows too) into the numeric feature vector
LightGBM trains on.

Numeric columns are parsed as float, with a blank string mapped to NaN
rather than 0.0 - LightGBM handles missing values natively (routes them
down a learned default branch), and put_call_ratio_at_entry is blank for
every current backtest row (documented live-only limitation, see
market_features.py), so treating blank as 0.0 would teach the model a
fake "always zero" put/call ratio instead of "unknown."

Categorical columns are integer-coded against a deterministic (sorted)
vocabulary built from the training data itself. The vocabulary is
returned alongside the features specifically so it can be reused later
for live scoring (Phase 7) - a category never seen in training (e.g. a
brand-new market_condition label) maps to a reserved -1 "unknown" code
rather than crashing or silently colliding with an existing category.
"""

from __future__ import annotations

from typing import Any

NUMERIC_COLUMNS = [
    "delta_at_entry",
    "iv_at_entry",
    "vix_at_entry",
    "sentiment_at_entry",
    "put_call_ratio_at_entry",
    "stop_pct",
    "target_pct",
    "floor_pct",
    "floor_trigger_pct",
]
# spot_at_entry (SPY's raw dollar price) is deliberately NOT a feature -
# confirmed via a real trained model's feature_importance that it was the
# single most-used split, which is a red flag rather than a good sign:
# every candidate on the same trading_day shares an identical price path,
# so a slowly-trending SPY's absolute price level is close to a day-ID in
# disguise, not a generalizable signal. A model that leans on it is
# learning "which of these specific days was this" rather than anything
# that would transfer to a day it hasn't seen.

CATEGORICAL_COLUMNS = [
    "call_or_put",
    "market_condition",
    "regime",
    "variant_label",
    "price_source_at_entry",
]

FEATURE_NAMES = NUMERIC_COLUMNS + CATEGORICAL_COLUMNS
LABEL_COLUMN = "outcome"
UNKNOWN_CATEGORY_CODE = -1


def _parse_numeric(value: Any) -> float:
    text = str(value).strip() if value is not None else ""
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def build_vocabulary(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """One sorted, deduplicated list of observed values per categorical
    column - sorted so the same input rows always produce the same
    vocabulary (and therefore the same integer codes) regardless of row
    order, which matters once a saved vocabulary needs to line up with a
    model trained on an earlier run."""
    vocabulary: dict[str, list[str]] = {}
    for column in CATEGORICAL_COLUMNS:
        values = {str(row.get(column, "")).strip() for row in rows}
        values.discard("")
        vocabulary[column] = sorted(values)
    return vocabulary


def _encode_category(column: str, value: Any, vocabulary: dict[str, list[str]]) -> int:
    text = str(value).strip() if value is not None else ""
    try:
        return vocabulary[column].index(text)
    except ValueError:
        return UNKNOWN_CATEGORY_CODE


def row_label(row: dict[str, str]) -> int:
    return 1 if row.get(LABEL_COLUMN) == "WIN" else 0


def row_to_feature_vector(row: dict[str, str], vocabulary: dict[str, list[str]]) -> list[float]:
    numeric = [_parse_numeric(row.get(column)) for column in NUMERIC_COLUMNS]
    categorical = [float(_encode_category(column, row.get(column), vocabulary)) for column in CATEGORICAL_COLUMNS]
    return numeric + categorical


def build_dataset(
    rows: list[dict[str, str]], vocabulary: dict[str, list[str]] | None = None
) -> tuple[list[list[float]], list[int], dict[str, list[str]]]:
    """vocabulary is optional so a TEST split can be encoded against the
    TRAIN split's vocabulary (never build a fresh vocabulary from test
    data - that would leak information about categories that only appear
    later in time)."""
    vocab = vocabulary if vocabulary is not None else build_vocabulary(rows)
    X = [row_to_feature_vector(row, vocab) for row in rows]
    y = [row_label(row) for row in rows]
    return X, y, vocab
