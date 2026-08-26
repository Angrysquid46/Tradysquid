"""AXIOM's competing entry hypotheses. Each is a pure function over
(current_price, causal_features, params) -> EntryDecision, independently
reasoned, none of them a copy of v1's opening-range breakout or of
anything read from the other competitor's private directory (never read).

Owner directive 2026-08-26 ("you don't need to anchor on all the traders
we've made in the past, you can literally build anything with its own
signals and aggression"): expanded from 3 to 6 genuinely distinct
mechanisms, each keyed to a different piece of backtest_lab.compute_features'
real, causal feature set - not the same idea relabeled six times:

- trend_continuation: an ALREADY-ESTABLISHED, multi-method-confirmed
  trend keeps going (MA stack + DI + MACD + volume).
- mean_reversion_extreme: an overextended move in a NON-trending tape
  reverts toward the mean (Bollinger + RSI).
- momentum_acceleration: a FRESH, short structural run is an inflection
  actively building (trend_run_length + volume + MACD).
- vwap_momentum: price has pushed a real distance off session VWAP with
  DI/MACD agreeing - riding the session's volume-weighted anchor, a
  different reference point than any MA stack or band.
- volatility_breakout: a compressed range (tight Bollinger width) breaks
  cleanly in one direction on a volume surge - the coiled-spring setup,
  a regime-detection mechanism none of the other five use.
- gap_and_go: a real opening gap trades WITH the gap (not faded),
  confirmed by DI and volume - the classic aggressive opening-drive play.

Each evaluator also scores its own entry confidence (0.0-1.0): how far
the firing signal sits past its own minimum qualifying bar, not just
whether it cleared it. contract_selection.select_contract uses that score
to bias which contract gets bought within the hypothesis's delta band -
higher conviction reaches further OTM (cheaper, more leveraged), a
barely-qualifying signal stays toward the band's safer end. This is the
aggression lever: sizing.position_size already commits the full
available bankroll to every trade (owner directive: "it's got a cap of
1k what's so hard to understand" - there is no fractional-risk throttle),
so conviction expresses itself through WHICH contract gets bought, not
through withholding bankroll.

All inputs come from backtest_lab.compute_features(bars) (deterministic,
causal, shared) plus the current bar's close price (not part of that
feature dict) - no lookahead, no second data pipeline.
"""

from __future__ import annotations

from typing import Any

from bots.claude.decision import EntryDecision

_STRENGTH_LEVELS = {"UNKNOWN": -1, "NONE": 0, "EMERGING": 1, "STRONG": 2, "VERY_STRONG": 3}


def _confidence(*ratios: float) -> float:
    """Mean of clamped 0..1 ratios, each "how far past its own minimum
    qualifying threshold" a contributing signal sits (0=barely qualifies,
    1=at or beyond a reasoned "clearly strong" ceiling). Pure and
    deterministic, matching evolution.py's own no-randomness rule."""
    clamped = [max(0.0, min(1.0, r)) for r in ratios]
    return sum(clamped) / len(clamped) if clamped else 0.5


def _ratio_above(value: float, minimum: float, span: float) -> float:
    """0 at `minimum`, 1 at `minimum + span` or beyond. `span<=0` (no
    meaningful ceiling to scale against) returns a flat 0.5 - qualifies,
    but not scored as either weak or strong."""
    if span <= 0:
        return 0.5
    return (value - minimum) / span


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

    signals["confidence"] = _confidence(
        _ratio_above(level, params["min_trend_strength_level"], 3 - params["min_trend_strength_level"]),
        _ratio_above(agreement, params["min_ma_stack_agreement"], 3 - params["min_ma_stack_agreement"]),
        _ratio_above(rv, params["relative_volume_min"], params["relative_volume_min"]),
    )
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
        extremity = _ratio_above(rsi, params["rsi_extreme_high"], 100 - params["rsi_extreme_high"])
    elif current_price <= bb_lower and rsi <= params["rsi_extreme_low"]:
        side = "CALL"
        extremity = _ratio_above(params["rsi_extreme_low"] - rsi, 0, params["rsi_extreme_low"])
    else:
        return EntryDecision(False, None, f"no bollinger+RSI extreme (price={current_price}, rsi={rsi})", signals)

    signals["confidence"] = _confidence(extremity)
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

    # Freshness itself is part of conviction: a 1-bar-old run is a purer
    # inflection bet than one already 3 bars into max_run_length.
    freshness = 1.0 - (abs(run) - 1) / max(1, params["max_run_length"] - 1)
    signals["confidence"] = _confidence(
        freshness,
        _ratio_above(rv, params["relative_volume_min"], params["relative_volume_min"]),
    )
    return EntryDecision(
        True, side,
        f"momentum_acceleration: fresh {run}-bar structural run + volume + MACD agreement",
        signals,
    )


def vwap_momentum(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    """Price sitting a real distance off session VWAP, with DI and MACD
    both agreeing with that side - riding the session's volume-weighted
    anchor. A genuinely different reference point than trend_continuation's
    MA stack or mean_reversion_extreme's Bollinger bands: VWAP is
    volume-weighted and resets every session, so this reads where the
    market's actual traded-volume center of gravity sits, not just price
    geometry."""
    signals: dict[str, Any] = {"features": features, "current_price": current_price}
    vwap = features.get("vwap")
    signals["vwap"] = vwap
    if vwap is None or vwap == 0:
        return EntryDecision(False, None, "no vwap available", signals)

    distance_pct = (current_price - vwap) / vwap * 100
    signals["vwap_distance_pct"] = distance_pct
    if abs(distance_pct) < params["min_vwap_distance_pct"]:
        return EntryDecision(False, None, f"too close to vwap ({distance_pct:+.3f}%)", signals)
    side = "CALL" if distance_pct > 0 else "PUT"

    di = features.get("trend_direction_di")
    signals["trend_direction_di"] = di
    want_di = "BULLISH" if side == "CALL" else "BEARISH"
    if di != want_di:
        return EntryDecision(False, None, f"DI disagrees with vwap side ({di})", signals)

    macd_hist = features.get("macd_histogram")
    signals["macd_histogram"] = macd_hist
    if macd_hist is None or (macd_hist > 0) != (side == "CALL"):
        return EntryDecision(False, None, f"MACD disagrees with vwap side ({macd_hist})", signals)

    rv = features.get("relative_volume")
    signals["relative_volume"] = rv
    if rv is None or rv < params["relative_volume_min"]:
        return EntryDecision(False, None, f"volume not confirmed ({rv})", signals)

    signals["confidence"] = _confidence(
        _ratio_above(abs(distance_pct), params["min_vwap_distance_pct"], params["min_vwap_distance_pct"]),
        _ratio_above(rv, params["relative_volume_min"], params["relative_volume_min"]),
    )
    return EntryDecision(
        True, side,
        f"vwap_momentum: price {distance_pct:+.3f}% off vwap with DI+MACD+volume agreement",
        signals,
    )


def volatility_breakout(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    """A compressed range (tight Bollinger width - the coiled spring)
    breaks cleanly in one direction on a volume surge. Regime detection
    first (is the tape compressed at all), direction second - a
    mechanism none of the other five hypotheses use, since they all
    presuppose a direction already exists rather than detecting the
    setup where one is about to."""
    signals: dict[str, Any] = {"features": features}
    bb_width = features.get("bb_width_pct")
    signals["bb_width_pct"] = bb_width
    if bb_width is None:
        return EntryDecision(False, None, "no bollinger width available", signals)
    if bb_width > params["max_squeeze_bb_width_pct"]:
        return EntryDecision(False, None, f"not compressed enough (width={bb_width:.3f}%)", signals)

    higher_high = features.get("higher_high")
    higher_low = features.get("higher_low")
    lower_high = features.get("lower_high")
    lower_low = features.get("lower_low")
    signals["break_shape"] = (higher_high, higher_low, lower_high, lower_low)
    if higher_high and higher_low:
        side = "CALL"
    elif lower_high and lower_low:
        side = "PUT"
    else:
        return EntryDecision(False, None, "no clean directional break out of the squeeze", signals)

    rv = features.get("relative_volume")
    signals["relative_volume"] = rv
    if rv is None or rv < params["relative_volume_min"]:
        return EntryDecision(False, None, f"breakout volume not confirmed ({rv})", signals)

    tightness = _ratio_above(
        params["max_squeeze_bb_width_pct"] - bb_width, 0, params["max_squeeze_bb_width_pct"]
    )
    signals["confidence"] = _confidence(
        tightness,
        _ratio_above(rv, params["relative_volume_min"], params["relative_volume_min"]),
    )
    return EntryDecision(
        True, side,
        f"volatility_breakout: squeeze (width={bb_width:.3f}%) breaks {side} on volume",
        signals,
    )


def gap_and_go(current_price: float, features: dict[str, Any], params: dict[str, float]) -> EntryDecision:
    """A real opening gap trades WITH the gap, confirmed by DI and
    volume - not faded. The classic aggressive opening-drive play: most
    likely to fire early in the session (gap_pct is only ever non-trivial
    right after the open), which is exactly when a confident, aggressive
    bot should be willing to lean in rather than wait and watch."""
    signals: dict[str, Any] = {"features": features}
    gap = features.get("gap_pct")
    signals["gap_pct"] = gap
    if gap is None:
        return EntryDecision(False, None, "no gap data available", signals)
    if abs(gap) < params["min_gap_pct"]:
        return EntryDecision(False, None, f"gap too small ({gap:+.3f}%)", signals)
    side = "CALL" if gap > 0 else "PUT"

    di = features.get("trend_direction_di")
    signals["trend_direction_di"] = di
    want_di = "BULLISH" if side == "CALL" else "BEARISH"
    if di != want_di:
        return EntryDecision(False, None, f"DI disagrees with gap side ({di})", signals)

    rv = features.get("relative_volume")
    signals["relative_volume"] = rv
    if rv is None or rv < params["relative_volume_min"]:
        return EntryDecision(False, None, f"volume not confirmed ({rv})", signals)

    signals["confidence"] = _confidence(
        _ratio_above(abs(gap), params["min_gap_pct"], params["min_gap_pct"]),
        _ratio_above(rv, params["relative_volume_min"], params["relative_volume_min"]),
    )
    return EntryDecision(
        True, side,
        f"gap_and_go: {gap:+.3f}% opening gap with DI+volume agreement",
        signals,
    )


EVALUATORS = {
    "trend_continuation": trend_continuation,
    "mean_reversion_extreme": mean_reversion_extreme,
    "momentum_acceleration": momentum_acceleration,
    "vwap_momentum": vwap_momentum,
    "volatility_breakout": volatility_breakout,
    "gap_and_go": gap_and_go,
}
