from __future__ import annotations
import math

import features


def _row(**overrides) -> dict[str, str]:
    base = {
        "call_or_put": "call", "market_condition": "CHOPPY / LOW VOL", "regime": "BULLISH / CONTROLLED",
        "variant_label": "live_default_50_50", "price_source_at_entry": "synthetic",
        "delta_at_entry": "0.52", "iv_at_entry": "0.18", "spot_at_entry": "600.0",
        "vix_at_entry": "15.5", "sentiment_at_entry": "0.05", "put_call_ratio_at_entry": "",
        "stop_pct": "0.5", "target_pct": "0.5", "floor_pct": "-15.0", "floor_trigger_pct": "30.0",
        "outcome": "WIN",
    }
    base.update(overrides)
    return base


def test_row_label_is_one_for_a_win():
    assert features.row_label(_row(outcome="WIN")) == 1


def test_row_label_is_zero_for_a_loss():
    assert features.row_label(_row(outcome="LOSS")) == 0


def test_row_label_is_zero_for_a_scratch():
    assert features.row_label(_row(outcome="SCRATCH")) == 0


def test_build_vocabulary_is_sorted_and_deduplicated():
    rows = [_row(market_condition="B"), _row(market_condition="A"), _row(market_condition="B")]
    vocab = features.build_vocabulary(rows)
    assert vocab["market_condition"] == ["A", "B"]


def test_build_vocabulary_ignores_blank_values():
    rows = [_row(market_condition=""), _row(market_condition="A")]
    vocab = features.build_vocabulary(rows)
    assert vocab["market_condition"] == ["A"]


def test_row_to_feature_vector_parses_blank_numeric_as_nan():
    vocab = features.build_vocabulary([_row()])
    vector = features.row_to_feature_vector(_row(put_call_ratio_at_entry=""), vocab)
    put_call_index = features.NUMERIC_COLUMNS.index("put_call_ratio_at_entry")
    assert math.isnan(vector[put_call_index])


def test_row_to_feature_vector_parses_a_real_numeric_value():
    vocab = features.build_vocabulary([_row()])
    vector = features.row_to_feature_vector(_row(vix_at_entry="16.2"), vocab)
    vix_index = features.NUMERIC_COLUMNS.index("vix_at_entry")
    assert vector[vix_index] == 16.2


def test_row_to_feature_vector_encodes_a_known_category():
    rows = [_row(call_or_put="call"), _row(call_or_put="put")]
    vocab = features.build_vocabulary(rows)
    vector = features.row_to_feature_vector(_row(call_or_put="put"), vocab)
    call_or_put_index = len(features.NUMERIC_COLUMNS) + features.CATEGORICAL_COLUMNS.index("call_or_put")
    assert vector[call_or_put_index] == vocab["call_or_put"].index("put")


def test_row_to_feature_vector_maps_an_unseen_category_to_the_unknown_code():
    vocab = features.build_vocabulary([_row(market_condition="CHOPPY / LOW VOL")])
    vector = features.row_to_feature_vector(_row(market_condition="NEVER SEEN BEFORE"), vocab)
    market_condition_index = len(features.NUMERIC_COLUMNS) + features.CATEGORICAL_COLUMNS.index("market_condition")
    assert vector[market_condition_index] == features.UNKNOWN_CATEGORY_CODE


def test_build_dataset_reuses_a_provided_vocabulary_instead_of_building_a_new_one():
    train_rows = [_row(market_condition="A")]
    test_rows = [_row(market_condition="B")]  # never seen in train
    _, _, train_vocab = features.build_dataset(train_rows)
    X_test, y_test, vocab_used = features.build_dataset(test_rows, vocabulary=train_vocab)
    assert vocab_used == train_vocab
    market_condition_index = len(features.NUMERIC_COLUMNS) + features.CATEGORICAL_COLUMNS.index("market_condition")
    assert X_test[0][market_condition_index] == features.UNKNOWN_CATEGORY_CODE


def test_build_dataset_shapes_match_row_count_and_feature_count():
    rows = [_row(), _row(outcome="LOSS")]
    X, y, _ = features.build_dataset(rows)
    assert len(X) == 2
    assert len(y) == 2
    assert all(len(vector) == len(features.FEATURE_NAMES) for vector in X)
