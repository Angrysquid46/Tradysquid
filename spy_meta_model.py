"""Phase 6 - ML layer and meta-model over the Phase 2 feature store.

Deliberately pure Python: no numpy, scipy or scikit-learn. The live venv
runs a real paper-trading system, and adding a heavy numerical stack to it
to satisfy a research phase is a poor trade. Everything here - logistic
regression, calibration, Brier scoring, permutation importance, purged
cross-validation - is a few dozen lines each and is testable without a
dependency that could break a deployment.

What this phase is FOR, stated plainly: the earlier phases measured
strategies one at a time. This asks the questions that only make sense
across them.

- Can a model predict direction better than the base rate, and are its
  probabilities honest (calibration), not merely ranked correctly?
- **NO-TRADE as a first-class class.** Most bars are not opportunities.
  A model forced to choose up or down on every bar learns to guess; one
  allowed to abstain learns when it knows nothing, which is the more
  valuable output for a system that already has 14 entry rules.
- Which features actually carry the signal (permutation importance), and
  which have decayed (drift).
- Which strategies are the same bet in different clothing (the overlap
  work that removed three duplicates already lives in the ranking here).

The methodological trap this phase exists to avoid is leakage. Standard
k-fold cross-validation shuffles rows, which on a time series lets the
model train on the future. Purging and embargoing are not optional
refinements here; without them every number below would be inflated.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

# Labels
UP, DOWN, NO_TRADE = "UP", "DOWN", "NO_TRADE"


# ---------------------------------------------------------------------------
# Multi-target labelling
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    """Everything worth predicting about one bar's future, not just
    direction - the spec asks for magnitude, MFE, MAE and time-to-move,
    because a model that knows price rises but not by how much or how far
    it dips first cannot be sized or stopped."""
    direction: str
    magnitude_atr: float
    mfe_atr: float
    mae_atr: float
    minutes_to_move: int | None
    resolved: bool


def label_outcome(
    rows: Sequence[dict[str, Any]],
    index: int,
    *,
    horizon: int = 30,
    threshold_atr: float = 0.25,
) -> Outcome | None:
    """Triple-barrier labelling: an up barrier, a down barrier and a time
    limit, labelled by whichever is hit FIRST.

    This is deliberately not 'did price rise over the next N bars'. A bar
    that rises 0.3 ATR after first falling 0.8 ATR is a loss for anyone
    who had a stop, and fixed-horizon labelling calls it a win. The
    triple barrier matches how a trade is actually managed, which is the
    difference between a model predicting something tradeable and one
    predicting an artefact.

    NO_TRADE is returned when neither barrier is touched inside the
    horizon - and that is a real answer, not a failure."""
    if index >= len(rows) - 1:
        return None
    row = rows[index]
    atr = row.get("atr_14")
    entry = row.get("close")
    if not atr or entry is None or atr <= 0:
        return None

    up_barrier = entry + threshold_atr * atr
    down_barrier = entry - threshold_atr * atr
    mfe = mae = 0.0
    direction = NO_TRADE
    minutes_to_move: int | None = None
    final = entry

    for offset in range(index + 1, min(index + 1 + horizon, len(rows))):
        bar = rows[offset]
        high, low, close = bar.get("high"), bar.get("low"), bar.get("close")
        if high is None or low is None:
            continue
        mfe = max(mfe, (high - entry) / atr)
        mae = max(mae, (entry - low) / atr)
        final = close if close is not None else final

        hit_up = high >= up_barrier
        hit_down = low <= down_barrier
        if hit_up and hit_down:
            # Same bar touched both. One-minute OHLC cannot order them, so
            # the pessimistic read is used - the same rule the backtest
            # engine applies, for the same reason.
            direction = DOWN
            minutes_to_move = offset - index
            break
        if hit_up:
            direction, minutes_to_move = UP, offset - index
            break
        if hit_down:
            direction, minutes_to_move = DOWN, offset - index
            break

    return Outcome(
        direction=direction,
        magnitude_atr=(final - entry) / atr,
        mfe_atr=mfe,
        mae_atr=mae,
        minutes_to_move=minutes_to_move,
        resolved=direction != NO_TRADE,
    )


# ---------------------------------------------------------------------------
# Logistic regression
# ---------------------------------------------------------------------------

@dataclass
class LogisticModel:
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    feature_names: list[str] = field(default_factory=list)
    means: list[float] = field(default_factory=list)
    scales: list[float] = field(default_factory=list)

    def _standardise(self, features: Sequence[float]) -> list[float]:
        return [
            (value - mean) / scale if scale else 0.0
            for value, mean, scale in zip(features, self.means, self.scales)
        ]

    def probability(self, features: Sequence[float]) -> float:
        z = self.bias + sum(
            weight * value
            for weight, value in zip(self.weights, self._standardise(features))
        )
        # Guard the exponential; a large |z| overflows math.exp otherwise.
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-min(z, 60.0)))
        exp_z = math.exp(max(z, -60.0))
        return exp_z / (1.0 + exp_z)


def train_logistic(
    features: Sequence[Sequence[float]],
    labels: Sequence[int],
    feature_names: Sequence[str],
    *,
    epochs: int = 200,
    learning_rate: float = 0.1,
    l2: float = 0.01,
) -> LogisticModel:
    """Batch gradient descent with L2 regularisation and standardised
    inputs.

    Standardisation is not cosmetic: these features span ATR multiples
    near 1, percentages near 100 and volumes in the millions. Without it
    the largest-scaled feature dominates the gradient and the model
    effectively ignores the rest."""
    if not features or not labels:
        return LogisticModel(feature_names=list(feature_names))

    width = len(features[0])
    means = [statistics.fmean(row[i] for row in features) for i in range(width)]
    scales = []
    for i in range(width):
        column = [row[i] for row in features]
        spread = statistics.pstdev(column) if len(column) > 1 else 0.0
        scales.append(spread if spread > 1e-12 else 1.0)

    model = LogisticModel(
        weights=[0.0] * width, bias=0.0,
        feature_names=list(feature_names), means=means, scales=scales,
    )
    standardised = [model._standardise(row) for row in features]
    count = len(standardised)

    for _ in range(epochs):
        gradient = [0.0] * width
        bias_gradient = 0.0
        for row, label in zip(standardised, labels):
            z = model.bias + sum(w * v for w, v in zip(model.weights, row))
            if z >= 0:
                prediction = 1.0 / (1.0 + math.exp(-min(z, 60.0)))
            else:
                exp_z = math.exp(max(z, -60.0))
                prediction = exp_z / (1.0 + exp_z)
            error = prediction - label
            bias_gradient += error
            for i, value in enumerate(row):
                gradient[i] += error * value
        model.bias -= learning_rate * bias_gradient / count
        for i in range(width):
            model.weights[i] -= learning_rate * (
                gradient[i] / count + l2 * model.weights[i]
            )
    return model


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of probabilistic forecasts. Lower is better;
    always predicting the base rate gives the variance of the outcome.

    Accuracy alone cannot tell you whether a 70% forecast means 70%.
    Brier can, which is why it is the headline calibration number."""
    if not probabilities:
        return 0.0
    return statistics.fmean(
        (p - o) ** 2 for p, o in zip(probabilities, outcomes)
    )


def reliability_curve(
    probabilities: Sequence[float], outcomes: Sequence[int], *, bins: int = 10
) -> list[dict[str, Any]]:
    """Predicted probability against observed frequency, bucketed.

    A calibrated model's buckets sit on the diagonal: bars it calls 70%
    happen about 70% of the time. A model can rank perfectly and still be
    badly calibrated, and a miscalibrated probability cannot be used for
    position sizing even when its ordering is useful."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes):
        index = min(int(probability * bins), bins - 1)
        buckets[index].append((probability, outcome))

    curve = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        predicted = statistics.fmean(p for p, _ in bucket)
        observed = statistics.fmean(o for _, o in bucket)
        curve.append({
            "bin": f"{index / bins:.1f}-{(index + 1) / bins:.1f}",
            "n": len(bucket),
            "predicted": predicted,
            "observed": observed,
            "gap": observed - predicted,
        })
    return curve


def calibration_error(curve: Sequence[dict[str, Any]]) -> float:
    """Expected calibration error - mean |predicted - observed|, weighted
    by bucket size."""
    total = sum(entry["n"] for entry in curve)
    if not total:
        return 0.0
    return sum(abs(entry["gap"]) * entry["n"] for entry in curve) / total


# ---------------------------------------------------------------------------
# Purged, embargoed walk-forward validation
# ---------------------------------------------------------------------------

def purged_splits(
    session_dates: Sequence[str], *, folds: int = 4, embargo: int = 1
) -> list[tuple[list[int], list[int]]]:
    """Contiguous time-ordered folds with a gap around each test block.

    Ordinary k-fold shuffles rows, which lets a model train on bars that
    come after the ones it is tested on - the single most common way an
    ML backtest reports an edge it does not have. Splits are by SESSION,
    not by row, because two bars from the same day are not independent
    observations.

    `embargo` drops whole sessions either side of the test block, so a
    label whose forward horizon overlaps the test period cannot leak into
    training."""
    unique = sorted(set(session_dates))
    if len(unique) < folds:
        return []
    size = len(unique) // folds
    index_by_session: dict[str, list[int]] = {}
    for position, session in enumerate(session_dates):
        index_by_session.setdefault(session, []).append(position)

    splits = []
    for fold in range(folds):
        start = fold * size
        stop = len(unique) if fold == folds - 1 else (fold + 1) * size
        test_sessions = set(unique[start:stop])
        embargoed = set(unique[max(0, start - embargo):start])
        embargoed |= set(unique[stop:stop + embargo])

        train_idx, test_idx = [], []
        for session, positions in index_by_session.items():
            if session in test_sessions:
                test_idx.extend(positions)
            elif session not in embargoed:
                train_idx.extend(positions)
        if train_idx and test_idx:
            splits.append((sorted(train_idx), sorted(test_idx)))
    return splits


# ---------------------------------------------------------------------------
# Permutation importance
# ---------------------------------------------------------------------------

def permutation_importance(
    model: LogisticModel,
    features: Sequence[Sequence[float]],
    outcomes: Sequence[int],
    *,
    repeats: int = 3,
    seed: int = 20260817,
) -> list[dict[str, Any]]:
    """Shuffle one feature, measure how much Brier score worsens.

    More trustworthy than reading model coefficients: a large weight on a
    feature the model rarely relies on says little, while this measures
    actual dependence. A feature whose shuffling changes nothing is
    decoration, and a feature whose importance falls over time has
    decayed - which is the drift signal that matters."""
    if not features:
        return []
    baseline = brier_score([model.probability(row) for row in features], outcomes)
    rng = random.Random(seed)
    results = []
    for position, name in enumerate(model.feature_names):
        deltas = []
        for _ in range(repeats):
            shuffled = [list(row) for row in features]
            column = [row[position] for row in shuffled]
            rng.shuffle(column)
            for row, value in zip(shuffled, column):
                row[position] = value
            score = brier_score([model.probability(r) for r in shuffled], outcomes)
            deltas.append(score - baseline)
        results.append({
            "feature": name,
            "importance": statistics.fmean(deltas),
            "baseline_brier": baseline,
        })
    results.sort(key=lambda item: -item["importance"])
    return results


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def population_stability_index(
    reference: Sequence[float], current: Sequence[float], *, bins: int = 10
) -> float:
    """PSI between two distributions of one feature.

    Convention: under 0.10 is stable, 0.10-0.25 is moderate shift, above
    0.25 means the feature no longer looks like what the model was
    trained on and its predictions should not be trusted."""
    if not reference or not current:
        return 0.0
    ordered = sorted(reference)
    edges = [
        ordered[min(int(len(ordered) * (i + 1) / bins), len(ordered) - 1)]
        for i in range(bins - 1)
    ]

    def bucket(values: Sequence[float]) -> list[float]:
        counts = [0] * bins
        for value in values:
            index = 0
            while index < len(edges) and value > edges[index]:
                index += 1
            counts[index] += 1
        total = len(values) or 1
        # Floor at a small epsilon so an empty bucket does not produce a
        # division by zero or an infinite log.
        return [max(count / total, 1e-6) for count in counts]

    reference_share = bucket(reference)
    current_share = bucket(current)
    return sum(
        (c - r) * math.log(c / r)
        for r, c in zip(reference_share, current_share)
    )


def drift_report(
    reference_rows: Sequence[dict[str, Any]],
    current_rows: Sequence[dict[str, Any]],
    feature_names: Sequence[str],
) -> list[dict[str, Any]]:
    out = []
    for name in feature_names:
        reference = [r[name] for r in reference_rows
                     if isinstance(r.get(name), (int, float))]
        current = [r[name] for r in current_rows
                   if isinstance(r.get(name), (int, float))]
        if len(reference) < 20 or len(current) < 20:
            continue
        psi = population_stability_index(reference, current)
        out.append({
            "feature": name,
            "psi": psi,
            "verdict": ("stable" if psi < 0.10
                        else "moderate shift" if psi < 0.25 else "DRIFTED"),
        })
    out.sort(key=lambda item: -item["psi"])
    return out
