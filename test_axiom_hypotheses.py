"""Real tests for bots/claude/hypotheses.py's six competing entry theses -
each predicate independently gates; breaking any one alone blocks entry.
Pure functions over synthetic feature dicts, no dependency on real
captured data."""

from __future__ import annotations

from bots.claude.hypotheses import (
    gap_and_go,
    mean_reversion_extreme,
    momentum_acceleration,
    trend_continuation,
    volatility_breakout,
    vwap_momentum,
)
from bots.claude.parameters import HYPOTHESIS_DEFAULTS

TC_PARAMS = dict(HYPOTHESIS_DEFAULTS["trend_continuation"])
MR_PARAMS = dict(HYPOTHESIS_DEFAULTS["mean_reversion_extreme"])
MA_PARAMS = dict(HYPOTHESIS_DEFAULTS["momentum_acceleration"])
VWAP_PARAMS = dict(HYPOTHESIS_DEFAULTS["vwap_momentum"])
VB_PARAMS = dict(HYPOTHESIS_DEFAULTS["volatility_breakout"])
GAP_PARAMS = dict(HYPOTHESIS_DEFAULTS["gap_and_go"])


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


def test_trend_continuation_enters_on_majority_ma_stack_agreement():
    """Owner directive 2026-08-26: min_ma_stack_agreement defaults to 2
    (majority), not the old hardcoded unanimous 3-of-3 - a real
    VERY_STRONG/clear-DI setup should not be blocked just because one of
    three timeframes disagrees, which happened live and cost a full
    session of zero trades."""
    decision = trend_continuation(100.0, _bullish_features(long_term_trend="DOWN"), TC_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_trend_continuation_blocked_when_ma_stack_agreement_below_minority():
    """Only short-term agrees (1-of-3) - even majority-rule must still
    block a stack that's mostly disagreeing."""
    decision = trend_continuation(
        100.0, _bullish_features(medium_term_trend="DOWN", long_term_trend="DOWN"), TC_PARAMS
    )
    assert decision.should_enter is False
    assert "MA stack" in decision.rationale


def test_trend_continuation_respects_a_stricter_ma_stack_agreement_param():
    """A hypothesis evolution.py has tightened min_ma_stack_agreement back
    to 3 (unanimous) must still block on a 2-of-3 stack - the param is a
    real lever, not just a default that's ignored."""
    strict_params = dict(TC_PARAMS, min_ma_stack_agreement=3)
    decision = trend_continuation(100.0, _bullish_features(long_term_trend="DOWN"), strict_params)
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


# --- confidence scoring (owner directive 2026-08-26: aggression should
# scale with conviction, not just gate on/off) ---

def test_trend_continuation_confidence_is_higher_for_a_stronger_setup():
    """VERY_STRONG + unanimous MA stack + heavy volume should score
    higher confidence than a setup that only just clears every bar."""
    weak = trend_continuation(100.0, _bullish_features(relative_volume=1.21), TC_PARAMS)
    strong = trend_continuation(
        100.0,
        _bullish_features(trend_strength="VERY_STRONG", relative_volume=3.0),
        TC_PARAMS,
    )
    assert weak.should_enter is True and strong.should_enter is True
    assert strong.contributing_signals["confidence"] > weak.contributing_signals["confidence"]


def test_entry_confidence_is_always_between_zero_and_one():
    decision = trend_continuation(100.0, _bullish_features(relative_volume=50.0), TC_PARAMS)
    assert decision.should_enter is True
    assert 0.0 <= decision.contributing_signals["confidence"] <= 1.0


# --- vwap_momentum ---

def _vwap_bullish(**overrides):
    base = {
        "vwap": 100.0,
        "trend_direction_di": "BULLISH",
        "macd_histogram": 0.5,
        "relative_volume": 1.5,
    }
    base.update(overrides)
    return base


def test_vwap_momentum_enters_call_when_price_pushed_above_vwap():
    decision = vwap_momentum(100.20, _vwap_bullish(), VWAP_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_vwap_momentum_enters_put_when_price_pushed_below_vwap():
    features = {
        "vwap": 100.0,
        "trend_direction_di": "BEARISH",
        "macd_histogram": -0.5,
        "relative_volume": 1.5,
    }
    decision = vwap_momentum(99.80, features, VWAP_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_vwap_momentum_blocked_when_too_close_to_vwap():
    decision = vwap_momentum(100.01, _vwap_bullish(), VWAP_PARAMS)
    assert decision.should_enter is False
    assert "too close" in decision.rationale


def test_vwap_momentum_blocked_when_di_disagrees():
    decision = vwap_momentum(100.20, _vwap_bullish(trend_direction_di="BEARISH"), VWAP_PARAMS)
    assert decision.should_enter is False
    assert "DI disagrees" in decision.rationale


def test_vwap_momentum_blocked_when_macd_disagrees():
    decision = vwap_momentum(100.20, _vwap_bullish(macd_histogram=-0.1), VWAP_PARAMS)
    assert decision.should_enter is False
    assert "MACD disagrees" in decision.rationale


def test_vwap_momentum_blocked_when_volume_not_confirmed():
    decision = vwap_momentum(100.20, _vwap_bullish(relative_volume=0.5), VWAP_PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


def test_vwap_momentum_blocked_on_missing_vwap():
    decision = vwap_momentum(100.20, _vwap_bullish(vwap=None), VWAP_PARAMS)
    assert decision.should_enter is False


# --- volatility_breakout ---

def _squeeze_break_up(**overrides):
    base = {
        "bb_width_pct": 0.8,
        "higher_high": 1,
        "higher_low": 1,
        "lower_high": 0,
        "lower_low": 0,
        "relative_volume": 1.6,
    }
    base.update(overrides)
    return base


def test_volatility_breakout_enters_call_on_clean_upward_break():
    decision = volatility_breakout(100.0, _squeeze_break_up(), VB_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_volatility_breakout_enters_put_on_clean_downward_break():
    features = {
        "bb_width_pct": 0.8,
        "higher_high": 0,
        "higher_low": 0,
        "lower_high": 1,
        "lower_low": 1,
        "relative_volume": 1.6,
    }
    decision = volatility_breakout(100.0, features, VB_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_volatility_breakout_blocked_when_not_compressed_enough():
    decision = volatility_breakout(100.0, _squeeze_break_up(bb_width_pct=5.0), VB_PARAMS)
    assert decision.should_enter is False
    assert "not compressed" in decision.rationale


def test_volatility_breakout_blocked_when_break_is_not_clean():
    features = _squeeze_break_up(higher_low=0)  # higher_high but not higher_low - not a clean break
    decision = volatility_breakout(100.0, features, VB_PARAMS)
    assert decision.should_enter is False
    assert "no clean directional break" in decision.rationale


def test_volatility_breakout_blocked_when_volume_not_confirmed():
    decision = volatility_breakout(100.0, _squeeze_break_up(relative_volume=0.5), VB_PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


# --- gap_and_go ---

def _gap_up(**overrides):
    base = {"gap_pct": 0.30, "trend_direction_di": "BULLISH", "relative_volume": 1.6}
    base.update(overrides)
    return base


def test_gap_and_go_enters_call_on_upward_gap():
    decision = gap_and_go(100.0, _gap_up(), GAP_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_gap_and_go_enters_put_on_downward_gap():
    features = {"gap_pct": -0.30, "trend_direction_di": "BEARISH", "relative_volume": 1.6}
    decision = gap_and_go(100.0, features, GAP_PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_gap_and_go_blocked_when_gap_too_small():
    decision = gap_and_go(100.0, _gap_up(gap_pct=0.02), GAP_PARAMS)
    assert decision.should_enter is False
    assert "too small" in decision.rationale


def test_gap_and_go_blocked_when_di_disagrees():
    decision = gap_and_go(100.0, _gap_up(trend_direction_di="BEARISH"), GAP_PARAMS)
    assert decision.should_enter is False
    assert "DI disagrees" in decision.rationale


def test_gap_and_go_blocked_when_volume_not_confirmed():
    decision = gap_and_go(100.0, _gap_up(relative_volume=0.5), GAP_PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


def test_gap_and_go_blocked_on_missing_gap_data():
    decision = gap_and_go(100.0, _gap_up(gap_pct=None), GAP_PARAMS)
    assert decision.should_enter is False
