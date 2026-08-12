"""Shared model-scoring logic for a real candidate - used by both
shadow.py (logs the score, never acts on it) and engine.py's dormant
Phase 7 filter (see engine.py's MODEL_FILTER_ENABLED). Split into its own
module rather than living in shadow.py, because shadow.py imports
engine.py (to reuse find_candidate/evaluate_exit_for_row) - engine.py
importing score_candidate back from shadow.py would be a circular
import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

import features
import train

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first


def score_candidate(
    candidate: dict[str, Any], context: dict[str, Any], market_condition: str,
    vix: float | None, sentiment: float | None, put_call_ratio: float | None,
) -> float | None:
    """Loads the current trained model fresh every call - Phase 5's
    retrain loop may have produced a newer one since the last score, and
    a LightGBM text-format model is cheap enough to reload that caching
    isn't worth the staleness risk. Returns None (never a fabricated
    score) when no model has been trained yet.

    variant_label/price_source_at_entry are backtest-only concepts a real
    candidate genuinely doesn't have a value for - left as placeholders
    the model's own training-time vocabulary maps to its UNKNOWN category
    code, which is the honest outcome, not a workaround. stop_pct/
    target_pct/floor_pct/floor_trigger_pct use the live SPY_0DTE
    constants directly, since a real (or shadow) candidate's hypothetical
    exit is evaluated with the exact same real exit signal the live bot
    uses."""
    if not train.MODEL_PATH.exists() or not train.METADATA_PATH.exists():
        return None
    try:
        metadata = json.loads(train.METADATA_PATH.read_text(encoding="utf-8"))
        model = lgb.Booster(model_file=str(train.MODEL_PATH))
    except (OSError, ValueError, lgb.basic.LightGBMError):
        return None
    vocabulary = metadata.get("vocabulary", {})
    row = {
        "delta_at_entry": str(candidate.get("delta", "")),
        "iv_at_entry": str(candidate.get("iv", "")),
        "vix_at_entry": "" if vix is None else str(vix),
        "sentiment_at_entry": "" if sentiment is None else str(sentiment),
        "put_call_ratio_at_entry": "" if put_call_ratio is None else str(put_call_ratio),
        "stop_pct": str(s.SPY_0DTE_STOP_PCT),
        "target_pct": str(s.SPY_0DTE_TARGET_PCT),
        "floor_pct": str(s.SPY_0DTE_FLOOR_PCT),
        "floor_trigger_pct": str(s.SPY_0DTE_FLOOR_TRIGGER_PCT),
        "call_or_put": candidate.get("call_or_put", ""),
        "market_condition": market_condition or "",
        "regime": context.get("regime", ""),
        "variant_label": "live",
        "price_source_at_entry": "real",
    }
    vector = features.row_to_feature_vector(row, vocabulary)
    prediction = model.predict(np.array([vector], dtype=float))
    return round(float(prediction[0]), 4)
