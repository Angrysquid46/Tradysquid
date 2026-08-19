"""Shared model-scoring logic for a real candidate - used by both
shadow.py (logs the score, never acts on it) and engine.py's dormant
Phase 7 filter (see engine.py's MODEL_FILTER_ENABLED). Split into its own
module rather than living in shadow.py, because shadow.py imports
engine.py (to reuse find_candidate/evaluate_exit_for_row) - engine.py
importing score_candidate back from shadow.py would be a circular
import.

Phase 8 adds explain_score()/build_model_narrative() - a real per-trade
explanation grounded in SHAP values (which features actually drove THIS
prediction, and by how much), not a fixed-wording template that ignores
what the model actually did. Confirmed live against the real trained
model that shap.TreeExplainer on a LightGBM Booster with a binary
objective returns values in log-odds space, not probability points - the
narrative below describes direction and relative influence, never claims
an exact probability-point contribution per feature, since that would
overstate what a SHAP value actually measures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import shap

import features
import train

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

FEATURE_DISPLAY_NAMES = {
    "delta_at_entry": "delta",
    "iv_at_entry": "implied volatility",
    "vix_at_entry": "VIX",
    "sentiment_at_entry": "news sentiment",
    "put_call_ratio_at_entry": "put/call ratio",
    "stop_pct": "stop-loss %",
    "target_pct": "profit-target %",
    "floor_pct": "ratchet-floor %",
    "floor_trigger_pct": "floor-trigger %",
    "call_or_put": "option type",
    "market_condition": "market condition",
    "regime": "breakout direction",
    "variant_label": "backtest variant",
    "price_source_at_entry": "price source",
}


def _load_model_and_metadata() -> tuple[lgb.Booster, dict[str, Any]] | None:
    """Loads the current trained model fresh every call - Phase 5's
    retrain loop may have produced a newer one since the last score, and
    a LightGBM text-format model is cheap enough to reload that caching
    isn't worth the staleness risk. Returns None when no model has been
    trained yet, or the files are corrupt/unreadable."""
    if not train.MODEL_PATH.exists() or not train.METADATA_PATH.exists():
        return None
    try:
        metadata = json.loads(train.METADATA_PATH.read_text(encoding="utf-8"))
        model = lgb.Booster(model_file=str(train.MODEL_PATH))
    except (OSError, ValueError, lgb.basic.LightGBMError):
        return None
    return model, metadata


def _build_feature_row(
    candidate: dict[str, Any], context: dict[str, Any], market_condition: str,
    vix: float | None, sentiment: float | None, put_call_ratio: float | None,
) -> dict[str, str]:
    """variant_label/price_source_at_entry are backtest-only concepts a
    real candidate genuinely doesn't have a value for - left as
    placeholders the model's own training-time vocabulary maps to its
    UNKNOWN category code, which is the honest outcome, not a workaround.
    stop_pct/target_pct/floor_pct/floor_trigger_pct use the live SPY_0DTE
    constants directly, since a real (or shadow) candidate's hypothetical
    exit is evaluated with the exact same real exit signal the live bot
    uses."""
    return {
        "delta_at_entry": str(candidate.get("delta", "")),
        "iv_at_entry": str(candidate.get("iv", "")),
        "vix_at_entry": "" if vix is None else str(vix),
        "sentiment_at_entry": "" if sentiment is None else str(sentiment),
        "put_call_ratio_at_entry": "" if put_call_ratio is None else str(put_call_ratio),
        "stop_pct": str(s.SPY_STOP_PCT),
        "target_pct": str(s.SPY_TARGET_PCT),
        "floor_pct": str(s.SPY_FLOOR_PCT),
        "floor_trigger_pct": str(s.SPY_FLOOR_TRIGGER_PCT),
        "call_or_put": candidate.get("call_or_put", ""),
        "market_condition": market_condition or "",
        "regime": context.get("regime", ""),
        "variant_label": "live",
        "price_source_at_entry": "real",
    }


def score_candidate(
    candidate: dict[str, Any], context: dict[str, Any], market_condition: str,
    vix: float | None, sentiment: float | None, put_call_ratio: float | None,
) -> float | None:
    """Just the number - returns None (never a fabricated score) when no
    model has been trained yet. Use explain_score() when a narrative is
    also needed, to avoid loading the model twice."""
    loaded = _load_model_and_metadata()
    if loaded is None:
        return None
    model, metadata = loaded
    row = _build_feature_row(candidate, context, market_condition, vix, sentiment, put_call_ratio)
    vector = features.row_to_feature_vector(row, metadata.get("vocabulary", {}))
    prediction = model.predict(np.array([vector], dtype=float))
    return round(float(prediction[0]), 4)


def explain_score(
    candidate: dict[str, Any], context: dict[str, Any], market_condition: str,
    vix: float | None, sentiment: float | None, put_call_ratio: float | None,
) -> dict[str, Any] | None:
    """Score plus a real per-feature SHAP breakdown for THIS specific
    prediction, sorted by |influence| descending. Returns None (never a
    fabricated explanation) under the same conditions score_candidate
    returns None. If SHAP itself fails for some reason, still returns the
    real score with an empty contributions list rather than losing the
    score too - a missing explanation is a smaller problem than a missing
    number the caller may already be logging."""
    loaded = _load_model_and_metadata()
    if loaded is None:
        return None
    model, metadata = loaded
    row = _build_feature_row(candidate, context, market_condition, vix, sentiment, put_call_ratio)
    vector = features.row_to_feature_vector(row, metadata.get("vocabulary", {}))
    X = np.array([vector], dtype=float)
    score = round(float(model.predict(X)[0]), 4)

    try:
        explainer = shap.TreeExplainer(model)
        shap_row = np.array(explainer.shap_values(X))[0]
    except Exception:
        return {"score": score, "contributions": []}

    feature_names = metadata.get("feature_names") or features.FEATURE_NAMES
    contributions = [
        {
            "feature": name,
            "shap_value": round(float(shap_value), 4),
            "display_value": row.get(name, ""),
        }
        for name, shap_value in zip(feature_names, shap_row)
    ]
    contributions.sort(key=lambda c: abs(c["shap_value"]), reverse=True)
    return {"score": score, "contributions": contributions}


def build_model_narrative(explanation: dict[str, Any] | None, top_n: int = 3) -> str:
    """Turns a real SHAP breakdown into readable English - grounded in
    what actually drove THIS prediction, not a fixed template. SHAP
    values here are in log-odds space (confirmed against the real model,
    see module docstring), so this describes direction and relative
    influence, never an exact probability-point contribution - claiming
    the latter would overstate what the number actually measures."""
    if explanation is None:
        return "No trained model available yet to explain this trade."
    score = explanation["score"]
    contributions = explanation["contributions"]
    if not contributions:
        return f"Model rated this a {score * 100:.1f}% win probability (feature breakdown unavailable)."
    parts = []
    for c in contributions[:top_n]:
        display_name = FEATURE_DISPLAY_NAMES.get(c["feature"], c["feature"])
        value = c["display_value"] or "unknown"
        direction = "favored a WIN" if c["shap_value"] > 0 else "favored a LOSS"
        parts.append(f"{display_name}={value} {direction} (influence {c['shap_value']:+.3f})")
    return f"Model rated this a {score * 100:.1f}% win probability. Top factors: " + "; ".join(parts) + "."
