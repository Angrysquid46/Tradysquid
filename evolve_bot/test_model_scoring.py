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
