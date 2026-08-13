from __future__ import annotations
import tempfile
from pathlib import Path
from unittest import mock

import model_scoring


def test_score_candidate_returns_none_when_no_model_exists():
    with tempfile.TemporaryDirectory() as temp:
        with (
            mock.patch.object(model_scoring.train, "MODEL_PATH", Path(temp) / "nope.txt"),
            mock.patch.object(model_scoring.train, "METADATA_PATH", Path(temp) / "nope.json"),
        ):
            score = model_scoring.score_candidate(
                {"delta": 0.5, "iv": 0.2, "call_or_put": "call"},
                {"regime": "BULLISH / CONTROLLED"}, "CHOPPY / LOW VOL", 15.0, 0.05, None,
            )
    assert score is None


def test_score_candidate_returns_a_real_probability_against_the_actual_trained_model():
    """Integration check against whatever model currently exists in
    models/ (produced by earlier phases' real training runs) - confirms
    the feature-building/vocabulary-lookup path actually works end to
    end, not just that missing-model returns None."""
    if not model_scoring.train.MODEL_PATH.exists():
        return  # nothing trained yet in this environment - not a failure
    score = model_scoring.score_candidate(
        {"delta": 0.5, "iv": 0.2, "call_or_put": "call"},
        {"regime": "BULLISH / CONTROLLED"}, "CHOPPY / LOW VOL", 15.0, 0.05, None,
    )
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_explain_score_returns_none_when_no_model_exists():
    with tempfile.TemporaryDirectory() as temp:
        with (
            mock.patch.object(model_scoring.train, "MODEL_PATH", Path(temp) / "nope.txt"),
            mock.patch.object(model_scoring.train, "METADATA_PATH", Path(temp) / "nope.json"),
        ):
            explanation = model_scoring.explain_score(
                {"delta": 0.5, "iv": 0.2, "call_or_put": "call"},
                {"regime": "BULLISH / CONTROLLED"}, "CHOPPY / LOW VOL", 15.0, 0.05, None,
            )
    assert explanation is None


def test_explain_score_matches_score_candidate_and_ranks_contributions_by_magnitude():
    """Integration check against the real trained model - confirms SHAP
    actually runs end to end and produces a real, non-empty breakdown."""
    if not model_scoring.train.MODEL_PATH.exists():
        return  # nothing trained yet in this environment - not a failure
    candidate = {"delta": 0.5, "iv": 0.2, "call_or_put": "call"}
    context = {"regime": "BULLISH / CONTROLLED"}
    explanation = model_scoring.explain_score(candidate, context, "CHOPPY / LOW VOL", 15.0, 0.05, None)
    score = model_scoring.score_candidate(candidate, context, "CHOPPY / LOW VOL", 15.0, 0.05, None)

    assert explanation is not None
    assert explanation["score"] == score
    assert explanation["contributions"]
    magnitudes = [abs(c["shap_value"]) for c in explanation["contributions"]]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert all("feature" in c and "shap_value" in c and "display_value" in c for c in explanation["contributions"])


def test_build_model_narrative_handles_a_missing_explanation():
    assert "No trained model" in model_scoring.build_model_narrative(None)


def test_build_model_narrative_handles_an_explanation_with_no_contributions():
    narrative = model_scoring.build_model_narrative({"score": 0.42, "contributions": []})
    assert "42.0%" in narrative
    assert "unavailable" in narrative


def test_build_model_narrative_describes_real_top_factors():
    explanation = {
        "score": 0.15,
        "contributions": [
            {"feature": "vix_at_entry", "shap_value": -0.8, "display_value": "22.5"},
            {"feature": "iv_at_entry", "shap_value": 0.3, "display_value": "0.18"},
            {"feature": "delta_at_entry", "shap_value": 0.1, "display_value": "0.5"},
        ],
    }
    narrative = model_scoring.build_model_narrative(explanation)
    assert "15.0%" in narrative
    assert "VIX=22.5" in narrative
    assert "favored a LOSS" in narrative
    assert "implied volatility=0.18" in narrative
    assert "favored a WIN" in narrative


def test_build_model_narrative_respects_top_n():
    explanation = {
        "score": 0.5,
        "contributions": [
            {"feature": "vix_at_entry", "shap_value": 0.5, "display_value": "15"},
            {"feature": "iv_at_entry", "shap_value": 0.4, "display_value": "0.2"},
            {"feature": "delta_at_entry", "shap_value": 0.3, "display_value": "0.5"},
        ],
    }
    narrative = model_scoring.build_model_narrative(explanation, top_n=1)
    assert "VIX" in narrative
    assert "implied volatility" not in narrative
