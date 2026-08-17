"""Tests for the Phase 6 ML layer.

An ML backtest fails silently and flatteringly: leakage, a miscalibrated
probability or a shuffled fold all produce BETTER numbers, never an error.
So these tests target the specific ways this code could lie -
cross-validation that lets the model see the future, labels that ignore
the path price took, and probabilities that rank correctly while meaning
nothing.
"""

from __future__ import annotations

import math
import random

import pytest

import spy_meta_model as mm


def _bar(minute: int, close: float, high: float | None = None,
         low: float | None = None, session: str = "2026-08-17"):
    hh, mm_ = divmod(9 * 60 + 30 + minute, 60)
    return {
        "bar_time": f"{session}T{hh:02d}:{mm_:02d}:00",
        "session_date": session, "minutes_since_open": minute,
        "close": close, "high": high if high is not None else close + 0.1,
        "low": low if low is not None else close - 0.1, "atr_14": 1.0,
    }


# ---------------------------------------------------------------------------
# Triple-barrier labelling
# ---------------------------------------------------------------------------

def test_label_reports_up_when_the_up_barrier_is_hit_first():
    rows = [_bar(0, 100.0)] + [_bar(i, 100.0) for i in range(1, 5)]
    rows[3] = _bar(3, 100.3, high=100.4)
    outcome = mm.label_outcome(rows, 0, horizon=10, threshold_atr=0.25)
    assert outcome.direction == mm.UP
    assert outcome.minutes_to_move == 3
    assert outcome.resolved is True


def test_label_reports_no_trade_when_neither_barrier_is_touched():
    """Most bars are not opportunities. A model forced to pick a side on
    every bar learns to guess; NO_TRADE is a real answer."""
    rows = [_bar(i, 100.0) for i in range(10)]
    outcome = mm.label_outcome(rows, 0, horizon=5, threshold_atr=0.5)
    assert outcome.direction == mm.NO_TRADE
    assert outcome.resolved is False
    assert outcome.minutes_to_move is None


def test_a_bar_touching_both_barriers_is_labelled_pessimistically():
    """One-minute OHLC cannot say which came first. Assuming the
    favourable one would inflate every label, exactly as it would inflate
    a backtest - so the same pessimistic rule is applied."""
    rows = [_bar(0, 100.0)] + [_bar(i, 100.0) for i in range(1, 4)]
    rows[1] = _bar(1, 100.0, high=100.5, low=99.5)
    outcome = mm.label_outcome(rows, 0, horizon=5, threshold_atr=0.25)
    assert outcome.direction == mm.DOWN


def test_labels_capture_the_path_not_just_the_endpoint():
    """The entire reason for triple-barrier labelling: a bar that ends
    higher after a deep dip is not a win for anyone who had a stop, and
    fixed-horizon labelling calls it one."""
    rows = [_bar(0, 100.0)]
    rows.append(_bar(1, 99.0, high=99.1, low=98.5))   # deep dip first
    rows.append(_bar(2, 100.4, high=100.5, low=99.0))  # then recovery
    outcome = mm.label_outcome(rows, 0, horizon=5, threshold_atr=0.25)
    assert outcome.direction == mm.DOWN, "endpoint-only labelling would say UP"
    assert outcome.mae_atr > 1.0


def test_label_returns_none_without_usable_atr():
    rows = [dict(_bar(i, 100.0), atr_14=None) for i in range(5)]
    assert mm.label_outcome(rows, 0) is None


# ---------------------------------------------------------------------------
# Logistic regression
# ---------------------------------------------------------------------------

def test_model_learns_a_separable_relationship():
    features = [[value] for value in range(-40, 40)]
    labels = [1 if row[0] > 0 else 0 for row in features]
    model = mm.train_logistic(features, labels, ["x"], epochs=400, learning_rate=0.5)
    assert model.probability([30]) > 0.8
    assert model.probability([-30]) < 0.2


def test_model_standardises_features_of_wildly_different_scale():
    """Features here span ATR multiples near 1 and volumes in the
    millions. Without standardisation the large-scale feature dominates
    the gradient and the model effectively ignores the other."""
    rng = random.Random(3)
    features, labels = [], []
    for _ in range(300):
        signal = rng.choice([-1.0, 1.0])
        noise_big = rng.uniform(1e6, 5e6)
        features.append([signal * 0.5, noise_big])
        labels.append(1 if signal > 0 else 0)
    model = mm.train_logistic(features, labels, ["signal", "volume"], epochs=300)
    assert model.probability([0.5, 3e6]) > 0.7
    assert model.probability([-0.5, 3e6]) < 0.3


def test_probability_never_overflows_on_extreme_inputs():
    model = mm.train_logistic([[0.0], [1.0]], [0, 1], ["x"], epochs=10)
    model.weights = [500.0]
    assert 0.0 <= model.probability([1e6]) <= 1.0
    assert 0.0 <= model.probability([-1e6]) <= 1.0


def test_training_on_nothing_returns_an_unfitted_model():
    model = mm.train_logistic([], [], ["x"])
    assert model.weights == []


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def test_brier_rewards_honest_probabilities_over_confident_wrong_ones():
    outcomes = [1, 1, 0, 0]
    honest = mm.brier_score([0.5, 0.5, 0.5, 0.5], outcomes)
    confident_right = mm.brier_score([0.9, 0.9, 0.1, 0.1], outcomes)
    confident_wrong = mm.brier_score([0.1, 0.1, 0.9, 0.9], outcomes)
    assert confident_right < honest < confident_wrong


def test_reliability_curve_detects_an_overconfident_model():
    """A model can rank perfectly and still be badly calibrated. A
    probability that does not mean what it says cannot be used to size a
    position, however good its ordering."""
    probabilities = [0.9] * 100
    outcomes = [1] * 50 + [0] * 50           # actually 50%, claimed 90%
    curve = mm.reliability_curve(probabilities, outcomes)
    assert curve
    entry = curve[-1]
    assert entry["predicted"] == pytest.approx(0.9)
    assert entry["observed"] == pytest.approx(0.5)
    assert mm.calibration_error(curve) == pytest.approx(0.4, abs=0.01)


def test_a_calibrated_model_has_near_zero_calibration_error():
    rng = random.Random(11)
    probabilities, outcomes = [], []
    for _ in range(4000):
        p = rng.uniform(0.05, 0.95)
        probabilities.append(p)
        outcomes.append(1 if rng.random() < p else 0)
    error = mm.calibration_error(mm.reliability_curve(probabilities, outcomes))
    assert error < 0.05


# ---------------------------------------------------------------------------
# Purged cross-validation - the leakage guard
# ---------------------------------------------------------------------------

def test_splits_never_put_the_same_session_in_train_and_test():
    """Two bars from one session are not independent observations. Row-level
    splitting would place 09:31 in training and 09:32 in test, which is
    leakage dressed as validation."""
    sessions = [f"2026-08-{day:02d}" for day in range(1, 21) for _ in range(5)]
    for train_idx, test_idx in mm.purged_splits(sessions, folds=4):
        train_sessions = {sessions[i] for i in train_idx}
        test_sessions = {sessions[i] for i in test_idx}
        assert not (train_sessions & test_sessions)


def test_embargo_removes_sessions_adjacent_to_the_test_block():
    """A label's forward horizon spans bars after its own. Without an
    embargo, the session immediately before a test block contains labels
    that peek into it."""
    sessions = [f"2026-08-{day:02d}" for day in range(1, 21) for _ in range(3)]
    splits = mm.purged_splits(sessions, folds=4, embargo=1)
    unique = sorted(set(sessions))
    for train_idx, test_idx in splits:
        train_sessions = {sessions[i] for i in train_idx}
        test_sessions = {sessions[i] for i in test_idx}
        first, last = min(test_sessions), max(test_sessions)
        before = unique[unique.index(first) - 1] if unique.index(first) > 0 else None
        after_pos = unique.index(last) + 1
        after = unique[after_pos] if after_pos < len(unique) else None
        assert before not in train_sessions
        assert after not in train_sessions


def test_splits_are_time_ordered_not_shuffled():
    sessions = [f"2026-08-{day:02d}" for day in range(1, 13) for _ in range(2)]
    splits = mm.purged_splits(sessions, folds=3, embargo=0)
    assert len(splits) == 3
    firsts = [min(sessions[i] for i in test) for _train, test in splits]
    assert firsts == sorted(firsts), "test blocks must advance through time"


def test_too_few_sessions_yields_no_splits_rather_than_a_bad_one():
    assert mm.purged_splits(["2026-08-01"] * 10, folds=4) == []


# ---------------------------------------------------------------------------
# Permutation importance
# ---------------------------------------------------------------------------

def test_permutation_finds_the_feature_that_carries_the_signal():
    rng = random.Random(5)
    features, labels = [], []
    for _ in range(400):
        signal = rng.uniform(-1, 1)
        noise = rng.uniform(-1, 1)
        features.append([signal, noise])
        labels.append(1 if signal > 0 else 0)
    model = mm.train_logistic(features, labels, ["signal", "noise"], epochs=300)
    ranked = mm.permutation_importance(model, features, labels, repeats=3)
    assert ranked[0]["feature"] == "signal"
    assert ranked[0]["importance"] > ranked[-1]["importance"]


def test_a_decorative_feature_scores_near_zero_importance():
    rng = random.Random(9)
    features = [[rng.uniform(-1, 1), 1.0] for _ in range(200)]
    labels = [1 if row[0] > 0 else 0 for row in features]
    model = mm.train_logistic(features, labels, ["signal", "constant"], epochs=200)
    ranked = {r["feature"]: r["importance"]
              for r in mm.permutation_importance(model, features, labels)}
    assert abs(ranked["constant"]) < 0.01


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def test_psi_is_near_zero_for_the_same_distribution():
    rng = random.Random(2)
    a = [rng.gauss(0, 1) for _ in range(2000)]
    b = [rng.gauss(0, 1) for _ in range(2000)]
    assert mm.population_stability_index(a, b) < 0.10


def test_psi_flags_a_shifted_distribution():
    rng = random.Random(2)
    a = [rng.gauss(0, 1) for _ in range(2000)]
    b = [rng.gauss(3, 1) for _ in range(2000)]
    assert mm.population_stability_index(a, b) > 0.25


def test_drift_report_labels_and_ranks_features():
    rng = random.Random(4)
    reference = [{"stable": rng.gauss(0, 1), "shifting": rng.gauss(0, 1)}
                 for _ in range(500)]
    current = [{"stable": rng.gauss(0, 1), "shifting": rng.gauss(4, 1)}
               for _ in range(500)]
    report = mm.drift_report(reference, current, ["stable", "shifting"])
    assert report[0]["feature"] == "shifting"
    assert report[0]["verdict"] == "DRIFTED"
    assert report[-1]["verdict"] == "stable"


def test_psi_handles_an_empty_bucket_without_dividing_by_zero():
    assert math.isfinite(
        mm.population_stability_index([0.0] * 100, [5.0] * 100)
    )
