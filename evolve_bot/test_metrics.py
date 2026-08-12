from __future__ import annotations
import math

import metrics


def test_accuracy_score_all_correct():
    assert metrics.accuracy_score([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0


def test_accuracy_score_half_correct():
    assert metrics.accuracy_score([1, 0, 1, 0], [1, 1, 0, 0]) == 0.5


def test_accuracy_score_empty_input():
    assert metrics.accuracy_score([], []) == 0.0


def test_precision_score_no_predicted_positives_returns_zero():
    assert metrics.precision_score([1, 0], [0, 0]) == 0.0


def test_precision_score_perfect_precision():
    assert metrics.precision_score([1, 0, 1], [1, 0, 1]) == 1.0


def test_precision_score_with_a_false_positive():
    # predicted positive at index 1 but true label is 0 -> 1 of 2 predicted positives correct
    assert metrics.precision_score([1, 0], [1, 1]) == 0.5


def test_recall_score_no_actual_positives_returns_zero():
    assert metrics.recall_score([0, 0], [1, 0]) == 0.0


def test_recall_score_perfect_recall():
    assert metrics.recall_score([1, 1, 0], [1, 1, 0]) == 1.0


def test_recall_score_missed_one_positive():
    assert metrics.recall_score([1, 1], [1, 0]) == 0.5


def test_log_loss_is_zero_for_perfect_confident_predictions():
    loss = metrics.log_loss([1, 0], [1.0, 0.0])
    assert loss < 1e-10


def test_log_loss_is_high_for_confidently_wrong_predictions():
    loss = metrics.log_loss([1, 0], [0.0, 1.0])
    assert loss > 10  # clipped at eps, not infinite, but very large


def test_log_loss_empty_input_returns_zero():
    assert metrics.log_loss([], []) == 0.0


def test_roc_auc_returns_none_for_single_class_y_true():
    assert metrics.roc_auc([1, 1, 1], [0.9, 0.5, 0.1]) is None


def test_roc_auc_is_one_for_perfect_ranking():
    # all positives score higher than all negatives
    assert metrics.roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0


def test_roc_auc_is_zero_for_perfectly_inverted_ranking():
    assert metrics.roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0


def test_roc_auc_is_half_for_random_ranking():
    # each positive beats exactly one of the two negatives and loses to
    # the other -> 2 of 4 pairwise comparisons favor the positive -> 0.5
    assert metrics.roc_auc([1, 0, 1, 0], [0.6, 0.7, 0.4, 0.3]) == 0.5


def test_roc_auc_handles_tied_scores_with_average_rank():
    # both classes share the same score - should not crash, AUC should be 0.5
    auc = metrics.roc_auc([0, 1], [0.5, 0.5])
    assert auc == 0.5
