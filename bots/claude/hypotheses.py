"""Phase 13 v2: AXIOM's three competing entry hypotheses. Each is a pure
function over (current_price, causal_features, params) -> EntryDecision,
independently reasoned, none of them a copy of v1's opening-range
breakout or of anything read from the other competitor's private
directory (never read).

Trending, choppy, and inflection regimes, covered by three genuinely
different mechanisms - not the same idea with different labels:

- trend_continuation: an ALREADY-ESTABLISHED, multi-method-confirmed
  trend keeps going.
- mean_reversion_extreme: an overextended move in a NON-trending tape
  reverts toward the mean.
- momentum_acceleration: a FRESH, short structural run is an inflection
  actively building, distinct from an established trend.

All inputs come from backtest_lab.compute_features(bars) (deterministic,
causal, shared) plus the current bar's close price (not part of that
feature dict) - no lookahead, no second data pipeline.
"""

from __future__ import annotations

from typing import Any

from bots.claude.decision import EntryDecision

_STRENGTH_LEVELS = {"UNKNOWN": -1, "NONE": 0, "EMERGING": 1, "STRONG": 2, "VERY_STRONG": 3}


def trend_continuation(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    signals: dict[str, Any] = {"features": features}
    level = _STRENGTH_LEVELS.get(features.get("trend_strength"), -1)
    signals["trend_strength_level"] = level
    if level < params["min_trend_strength_level"]:
        return EntryDecision(False, None, f"trend not strong enough (level={level})", signals)

    di = features.get("trend_direction_di")
    signals["trend_direction_di"] = di
    if di not in ("BULLISH", "BEARISH"):
        return EntryDecision(False, None, f"no clear DI direction ({di})", signals)
    side = "CALL" if di == "BULLISH" else "PUT"
    want = "UP" if side == "CALL" else "DOWN"

    stack = (features.get("short_term_trend"), features.get("medium_term_trend"), features.get("long_term_trend"))
    signals["ma_stack"] = stack
    agreement = sum(1 for t in stack if t == want)
    signals["ma_stack_agreement"] = agreement
    # Owner directive 2026-08-26: was unanimous (3-of-3) - blocked a real
    # VERY_STRONG/clear-DI setup for an entire session solely because the
    # long-term MA disagreed with short+medium. min_ma_stack_agreement is
    # itself a tunable (parameters.py), evolvable in either direction
    # (evolution.py's _tighten()/_loosen()) rather than a hardcoded 3.
    if agreement < params["min_ma_stack_agreement"]:
        return EntryDecision(False, None, f"MA stack not aligned enough {stack} ({agreement}/3)", signals)

    macd_hist = features.get("macd_histogram")
    signals["macd_histogram"] = macd_hist
    if macd_hist is None or (macd_hist > 0) != (side == "CALL"):
        return EntryDecision(False, None, f"MACD sign disagrees ({macd_hist})", signals)

    rv = features.get("relative_volume")
    signals["relative_volume"] = rv
    if rv is None or rv < params["relative_volume_min"]:
        return EntryDecision(False, None, f"volume not confirmed ({rv})", signals)

    return EntryDecision(
        True, side,
        "trend_continuation: strength+DI+MA-stack+MACD+volume all agree",
        signals,
    )


def mean_reversion_extreme(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    signals: dict[str, Any] = {"features": features, "current_price": current_price}
    level = _STRENGTH_LEVELS.get(features.get("trend_strength"), -1)
    signals["trend_strength_level"] = level
    if level < 0 or level > params["max_trend_strength_level"]:
        return EntryDecision(False, None, f"regime too trending for reversion (level={level})", signals)

    rsi = features.get("rsi_14")
    bb_upper = features.get("bb_upper")
    bb_lower = features.get("bb_lower")
    signals["rsi_14"] = rsi
    signals["bb_upper"] = bb_upper
    signals["bb_lower"] = bb_lower
    if rsi is None or bb_upper is None or bb_lower is None:
        return EntryDecision(False, None, "missing rsi/bollinger data", signals)

    if current_price >= bb_upper and rsi >= params["rsi_extreme_high"]:
        side = "PUT"
    elif current_price <= bb_lower and rsi <= params["rsi_extreme_low"]:
        side = "CALL"
    else:
        return EntryDecision(False, None, f"no bollinger+RSI extreme (price={current_price}, rsi={rsi})", signals)

    return EntryDecision(
        True, side,
        "mean_reversion_extreme: Bollinger+RSI extreme in a non-trending regime",
        signals,
    )


def momentum_acceleration(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    signals: dict[str, Any] = {"features": features}
    run = features.get("trend_run_length")
    signals["trend_run_length"] = run
    if run is None or run == 0:
        return EntryDecision(False, None, "no active directional run", signals)
    if abs(run) > params["max_run_length"]:
        return EntryDecision(False, None, f"run already extended ({run}), not a fresh inflection", signals)
    side = "CALL" if run > 0 else "PUT"

    rv = features.get("relative_volume")
    signals["relative_volume"] = rv
    if rv is None or rv < params["relative_volume_min"]:
        return EntryDecision(False, None, f"volume surge not confirmed ({rv})", signals)

    macd_hist = features.get("macd_histogram")
    signals["macd_histogram"] = macd_hist
    if macd_hist is None or (macd_hist > 0) != (side == "CALL"):
        return EntryDecision(False, None, f"MACD disagrees with run direction ({macd_hist})", signals)

    return EntryDecision(
        True, side,
        f"momentum_acceleration: fresh {run}-bar structural run + volume + MACD agreement",
        signals,
    )


EVALUATORS = {
    "trend_continuation": trend_continuation,
    "mean_reversion_extreme": mean_reversion_extreme,
    "momentum_acceleration": momentum_acceleration,
}
