"""Real tests for bots/claude/hypotheses.py's three competing entry
theses - each predicate independently gates; breaking any one alone
blocks entry. Pure functions over synthetic feature dicts, no dependency
on real captured data."""

from __future__ import annotations

from bots.claude.hypotheses import mean_reversion_extreme, momentum_acceleration, trend_continuation
from bots.claude.parameters import HYPOTHESIS_DEFAULTS

TC_PARAMS = dict(HYPOTHESIS_DEFAULTS["trend_continuation"])
MR_PARAMS = dict(HYPOTHESIS_DEFAULTS["mean_reversion_extreme"])
MA_PARAMS = dict(HYPOTHESIS_DEFAULTS["momentum_acceleration"])


# --- trend_continuation ---

def _bullish_features(**overrides):
    base = {
        "trend_strength": "STRONG",
        "trend_direction_di": "BULLISH",
        "short_term_trend": "UP",
        "medium_term_trend": "UP",
        "long_term_trend": "UP",
        "macd_histogram": 0.5,
        "relative_volume": 1.5,
    }
    base.update(overrides)
    return base


def test_trend_continuation_enters_when_everything_agrees_bullish():
    decision = trend_continuation(100.0, _bullish_features(), TC_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_trend_continuation_enters_when_everything_agrees_bearish():
    features = {
        "trend_strength": "VERY_STRONG",
        "trend_direction_di": "BEARISH",
        "short_term_trend": "DOWN",
        "medium_term_trend": "DOWN",
        "long_term_trend": "DOWN",
        "macd_histogram": -0.5,
        "relative_volume": 1.5,
    }
    decision = trend_continuation(100.0, features, TC_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_trend_continuation_blocked_when_strength_too_weak():
    decision = trend_continuation(100.0, _bullish_features(trend_strength="EMERGING"), TC_PARAMS)
    assert decision.should_enter is False
    assert "strong enough" in decision.rationale


def test_trend_continuation_blocked_when_di_unclear():
    decision = trend_continuation(100.0, _bullish_features(trend_direction_di="NEUTRAL"), TC_PARAMS)
    assert decision.should_enter is False
    assert "DI direction" in decision.rationale


def test_trend_continuation_blocked_when_ma_stack_not_aligned():
    decision = trend_continuation(100.0, _bullish_features(long_term_trend="DOWN"), TC_PARAMS)
    assert decision.should_enter is False
    assert "MA stack" in decision.rationale


def test_trend_continuation_blocked_when_macd_disagrees():
    decision = trend_continuation(100.0, _bullish_features(macd_histogram=-0.1), TC_PARAMS)
    assert decision.should_enter is False
    assert "MACD" in decision.rationale


def test_trend_continuation_blocked_when_volume_not_confirmed():
    decision = trend_continuation(100.0, _bullish_features(relative_volume=0.8), TC_PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


# --- mean_reversion_extreme ---

def test_mean_reversion_enters_call_on_oversold_extreme():
    features = {"trend_strength": "NONE", "rsi_14": 25.0, "bb_upper": 110.0, "bb_lower": 95.0}
    decision = mean_reversion_extreme(94.0, features, MR_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_mean_reversion_enters_put_on_overbought_extreme():
    features = {"trend_strength": "EMERGING", "rsi_14": 75.0, "bb_upper": 110.0, "bb_lower": 95.0}
    decision = mean_reversion_extreme(111.0, features, MR_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_mean_reversion_blocked_when_regime_too_trending():
    features = {"trend_strength": "STRONG", "rsi_14": 25.0, "bb_upper": 110.0, "bb_lower": 95.0}
    decision = mean_reversion_extreme(94.0, features, MR_PARAMS)
    assert decision.should_enter is False
    assert "too trending" in decision.rationale


def test_mean_reversion_blocked_without_a_real_extreme():
    features = {"trend_strength": "NONE", "rsi_14": 50.0, "bb_upper": 110.0, "bb_lower": 95.0}
    decision = mean_reversion_extreme(100.0, features, MR_PARAMS)
    assert decision.should_enter is False
    assert "extreme" in decision.rationale


def test_mean_reversion_blocked_on_missing_data():
    features = {"trend_strength": "NONE", "rsi_14": None, "bb_upper": None, "bb_lower": None}
    decision = mean_reversion_extreme(100.0, features, MR_PARAMS)
    assert decision.should_enter is False


# --- momentum_acceleration ---

def test_momentum_acceleration_enters_call_on_fresh_bullish_run():
    features = {"trend_run_length": 2, "relative_volume": 1.6, "macd_histogram": 0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_momentum_acceleration_enters_put_on_fresh_bearish_run():
    features = {"trend_run_length": -1, "relative_volume": 1.6, "macd_histogram": -0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_momentum_acceleration_blocked_when_no_active_run():
    features = {"trend_run_length": 0, "relative_volume": 1.6, "macd_histogram": 0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is False
    assert "no active" in decision.rationale


def test_momentum_acceleration_blocked_when_run_already_extended():
    features = {"trend_run_length": 6, "relative_volume": 1.6, "macd_histogram": 0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is False
    assert "extended" in decision.rationale


def test_momentum_acceleration_blocked_when_volume_not_confirmed():
    features = {"trend_run_length": 2, "relative_volume": 0.9, "macd_histogram": 0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


def test_momentum_acceleration_blocked_when_macd_disagrees():
    features = {"trend_run_length": 2, "relative_volume": 1.6, "macd_histogram": -0.3}
    decision = momentum_acceleration(100.0, features, MA_PARAMS)
    assert decision.should_enter is False
    assert "MACD" in decision.rationale
