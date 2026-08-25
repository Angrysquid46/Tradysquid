"""Real tests for signal.py's three independent entry predicates - each
must independently gate; breaking any one alone must block entry."""

from __future__ import annotations

from bots.claude.parameters import Parameters
from bots.claude.signal import compute_regime_features, entry_decision

PARAMS = Parameters()


def _bar(ts: int, time_str: str, o: float, h: float, l: float, c: float, v: int = 1000) -> dict:
    return {
        "bar_timestamp": ts, "bar_time": time_str,
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def _session_bars(day: str, closes_after_or: list[float]) -> list[dict]:
    """First two bars (20-min cadence) build a 30-40 range opening range
    (high=101, low=99), then one bar per requested post-OR close."""
    base_ts = 1_800_000_000
    bars = [
        _bar(base_ts, f"{day}T09:30:00", 100, 101, 99, 100.5),
        _bar(base_ts + 1200, f"{day}T09:50:00", 100.5, 100.8, 99.5, 100.2),
    ]
    for i, close in enumerate(closes_after_or):
        ts = base_ts + 2400 + i * 1200
        bars.append(_bar(ts, f"{day}T{10 + i:02d}:10:00", close, close + 0.3, close - 0.3, close))
    return bars


def test_compute_regime_features_identifies_first_breakout_bar():
    bars = _session_bars("2026-08-24", [103.0])  # breaks above OR high of 101
    features = compute_regime_features(bars)
    assert features["opening_range_high"] == 101
    assert features["opening_range_low"] == 99
    assert features["is_first_breakout_bar"] is True
    assert features["breakout_side"] == "CALL"


def test_compute_regime_features_does_not_refire_on_later_bars():
    # First bar breaks out, second bar also stays outside - only the
    # FIRST breach should ever count as "first breakout bar".
    bars = _session_bars("2026-08-24", [103.0, 104.0])
    features = compute_regime_features(bars)
    assert features["is_first_breakout_bar"] is False


def test_entry_blocked_when_not_compressed():
    regime = compute_regime_features(_session_bars("2026-08-24", [103.0]))
    causal = {"atr_percentile": 90.0, "relative_volume": 2.0, "vwap": 100.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is False
    assert "compressed" in decision.rationale


def test_entry_blocked_when_volume_not_confirmed():
    regime = compute_regime_features(_session_bars("2026-08-24", [103.0]))
    causal = {"atr_percentile": 10.0, "relative_volume": 0.5, "vwap": 100.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is False
    assert "volume" in decision.rationale


def test_entry_blocked_when_breakout_disagrees_with_vwap():
    # Breaks up (CALL side) but price is below VWAP - no confluence.
    regime = compute_regime_features(_session_bars("2026-08-24", [103.0]))
    causal = {"atr_percentile": 10.0, "relative_volume": 2.0, "vwap": 110.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is False
    assert "VWAP" in decision.rationale


def test_entry_fires_when_all_three_conditions_hold():
    regime = compute_regime_features(_session_bars("2026-08-24", [103.0]))
    causal = {"atr_percentile": 10.0, "relative_volume": 2.0, "vwap": 100.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is True
    assert decision.side == "CALL"


def test_entry_blocked_when_no_breakout_yet():
    regime = compute_regime_features(_session_bars("2026-08-24", [100.4]))  # stays inside range
    causal = {"atr_percentile": 10.0, "relative_volume": 2.0, "vwap": 100.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is False


def test_put_side_breakout_requires_price_below_vwap():
    regime = compute_regime_features(_session_bars("2026-08-24", [97.0]))  # breaks below OR low of 99
    assert regime["breakout_side"] == "PUT"
    causal = {"atr_percentile": 10.0, "relative_volume": 2.0, "vwap": 100.0}
    decision = entry_decision(regime, causal, PARAMS)
    assert decision.should_enter is True
    assert decision.side == "PUT"


def test_compute_regime_features_returns_none_for_empty_bars():
    assert compute_regime_features([]) is None
