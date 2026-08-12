"""Hand-rolled classification metrics - accuracy/precision/recall/AUC/
log-loss are simple enough formulas that pulling in scikit-learn (a large
dependency) just for these four would be adding weight for no real
benefit; LightGBM is already the only ML library this project committed
to using.
"""

from __future__ import annotations

import math


def accuracy_score(y_true: list[int], y_pred: list[int]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def precision_score(y_true: list[int], y_pred: list[int]) -> float:
    true_positives = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    predicted_positives = sum(1 for p in y_pred if p == 1)
    if predicted_positives == 0:
        return 0.0
    return true_positives / predicted_positives


def recall_score(y_true: list[int], y_pred: list[int]) -> float:
    true_positives = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    actual_positives = sum(1 for t in y_true if t == 1)
    if actual_positives == 0:
        return 0.0
    return true_positives / actual_positives


def log_loss(y_true: list[int], y_prob: list[float], eps: float = 1e-15) -> float:
    clipped = [min(max(p, eps), 1 - eps) for p in y_prob]
    losses = [
        -(t * math.log(p) + (1 - t) * math.log(1 - p)) for t, p in zip(y_true, clipped)
    ]
    return sum(losses) / len(losses) if losses else 0.0


def roc_auc(y_true: list[int], y_prob: list[float]) -> float | None:
    """Rank-based (Mann-Whitney U) AUC - equivalent to the area under the
    ROC curve without needing to sweep thresholds explicitly. Ties in
    score get the average rank, the standard correction (otherwise
    identical scores would arbitrarily favor whichever happens to sort
    first). Returns None when y_true is single-class - AUC measures
    ranking one class above the other, which is undefined with only one
    class present (a real, not-uncommon case on a small walk-forward test
    slice)."""
    n_pos = sum(1 for t in y_true if t == 1)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(y_prob)), key=lambda i: y_prob[i])
    ranks = [0.0] * len(y_prob)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and y_prob[order[j + 1]] == y_prob[order[i]]:
            j += 1
        average_rank = (i + j) / 2 + 1  # ranks are 1-indexed
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1
    sum_ranks_pos = sum(ranks[i] for i in range(len(y_true)) if y_true[i] == 1)
    return (sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
