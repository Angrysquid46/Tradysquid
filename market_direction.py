"""Deterministic, causal market direction and regime facts.

This module is strategy-neutral.  It converts completed SPY bars available at
an ``as_of`` time into one shared description that every private trader can
use.  It never selects a setup, contract, entry, or exit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import fmean, pstdev
from typing import Any, Literal


Side = Literal["call", "put"]


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class MarketDirection:
    direction: Literal["UP", "DOWN", "MIXED", "FLAT", "INSUFFICIENT"]
    score: float
    confidence: float
    alignment: float
    trend_strength: float
    chop: float
    volatility: float
    acceleration: float
    vwap_bias: float
    structure: float
    returns: dict[str, float]
    votes: dict[str, int]
    up_reversal_confirmed: bool
    down_reversal_confirmed: bool
    bar_count: int
    regime: str = "UNKNOWN"
    persistence: float = 0.0
    relative_volume: float = 1.0
    range_position: float = 0.5
    range_expansion: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DirectionPermission:
    allowed: bool
    size_multiplier: float
    relationship: Literal["ALIGNED", "COUNTERTREND", "MIXED", "UNKNOWN"]
    reason: str


def assess_market_direction(bars: list[dict[str, Any]]) -> MarketDirection:
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    volumes: list[float] = []
    for row in bars[-120:]:
        try:
            close = float(row["close"])
            high = float(row.get("high", close))
            low = float(row.get("low", close))
            volume = max(0.0, float(row.get("volume") or 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if close <= 0 or high < low:
            continue
        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)

    empty = MarketDirection(
        "INSUFFICIENT", 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, {}, {}, False, False, len(closes),
    )
    if len(closes) < 20:
        return empty

    one_minute = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    noise = max(pstdev(one_minute[-40:]) if len(one_minute) > 1 else 0.0, 0.00005)
    windows = ((3, .08), (5, .12), (10, .18), (20, .24), (40, .18), (60, .20))
    returns: dict[str, float] = {}
    votes: dict[str, int] = {}
    weighted_score = 0.0
    available_weight = 0.0
    directional_weight = 0.0
    positive_weight = 0.0
    negative_weight = 0.0

    for window, weight in windows:
        if len(closes) <= window:
            continue
        value = closes[-1] / closes[-window - 1] - 1.0
        key = f"{window}m"
        returns[key] = value
        threshold = max(0.00008, noise * sqrt(window) * .35)
        vote = 1 if value > threshold else -1 if value < -threshold else 0
        votes[key] = vote
        strength = _clamp(value / max(threshold * 2.5, 0.0002))
        weighted_score += weight * strength
        available_weight += weight
        if vote:
            directional_weight += weight
            if vote > 0:
                positive_weight += weight
            else:
                negative_weight += weight

    if available_weight <= 0:
        return empty
    score = _clamp(weighted_score / available_weight)
    alignment = max(positive_weight, negative_weight) / max(directional_weight, .0001)

    strength_window = min(20, len(closes) - 1)
    path = sum(abs(value) for value in one_minute[-strength_window:])
    displacement = abs(closes[-1] / closes[-strength_window - 1] - 1.0)
    trend_strength = _clamp(displacement / max(path, .00001), 0.0, 1.0)
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in one_minute[-20:]]
    flips = sum(a and b and a != b for a, b in zip(signs, signs[1:]))
    chop = _clamp(flips / max(len(signs) - 1, 1), 0.0, 1.0)
    positive = sum(value > 0 for value in one_minute[-20:])
    negative = sum(value < 0 for value in one_minute[-20:])
    persistence = max(positive, negative) / max(len(signs), 1)
    volatility = _clamp(noise / .0015, 0.0, 1.0)

    recent = returns.get("3m", 0.0)
    prior = closes[-4] / closes[-7] - 1.0 if len(closes) >= 7 else 0.0
    acceleration = _clamp((recent - prior) / max(noise * sqrt(3) * 2.0, .00015))

    total_volume = sum(volumes)
    vwap = (
        sum(price * volume for price, volume in zip(closes, volumes)) / total_volume
        if total_volume > 0 else fmean(closes)
    )
    vwap_bias = _clamp((closes[-1] / vwap - 1.0) / max(noise * 3.0, .0002))

    prior_high = max(highs[-10:-5]); recent_high = max(highs[-5:])
    prior_low = min(lows[-10:-5]); recent_low = min(lows[-5:])
    structure = 1.0 if recent_high > prior_high and recent_low > prior_low else (
        -1.0 if recent_high < prior_high and recent_low < prior_low else 0.0
    )
    prior_volume = volumes[-21:-1]
    relative_volume = volumes[-1] / max(fmean(prior_volume), 1.0) if prior_volume else 1.0
    twenty_high, twenty_low = max(highs[-20:]), min(lows[-20:])
    range_position = (closes[-1] - twenty_low) / max(twenty_high - twenty_low, .0001)
    recent_range = max(highs[-8:]) - min(lows[-8:])
    prior_range = max(highs[-20:-8]) - min(lows[-20:-8])
    range_expansion = recent_range / max(prior_range, .0001)

    confidence = _clamp(
        .40 * abs(score) + .22 * alignment + .18 * trend_strength
        + .10 * persistence + .10 * (1.0 - chop),
        0.0, 1.0,
    )
    if abs(score) < .10 or directional_weight < .25:
        direction = "FLAT"
    elif score >= .22 and alignment >= .58:
        direction = "UP"
    elif score <= -.22 and alignment >= .58:
        direction = "DOWN"
    else:
        direction = "MIXED"

    if direction in {"UP", "DOWN"} and trend_strength >= .45 and alignment >= .70:
        regime = f"TREND_{direction}"
    elif range_expansion >= 1.35 and volatility >= .35:
        regime = "EXPANSION"
    elif range_expansion <= .70 and volatility <= .45:
        regime = "COMPRESSION"
    elif chop >= .55 or direction == "MIXED":
        regime = "CHOP"
    elif direction == "FLAT":
        regime = "BALANCE"
    else:
        regime = "TRANSITION"

    short_up = returns.get("3m", 0.0) > 0 and returns.get("5m", 0.0) > 0
    short_down = returns.get("3m", 0.0) < 0 and returns.get("5m", 0.0) < 0
    reversal_threshold = max(noise * sqrt(5) * .75, .00020)
    up_reversal = bool(
        direction == "DOWN" and short_up and returns.get("5m", 0.0) >= reversal_threshold
        and acceleration >= .35 and structure >= 0 and vwap_bias >= -.10
    )
    down_reversal = bool(
        direction == "UP" and short_down and returns.get("5m", 0.0) <= -reversal_threshold
        and acceleration <= -.35 and structure <= 0 and vwap_bias <= .10
    )
    return MarketDirection(
        direction, score, confidence, alignment, trend_strength, chop,
        volatility, acceleration, vwap_bias, structure, returns, votes,
        up_reversal, down_reversal, len(closes), regime, persistence,
        relative_volume, range_position, range_expansion,
    )


def trade_direction_permission(
    context: MarketDirection,
    side: str,
    *,
    countertrend_setup: bool = False,
) -> DirectionPermission:
    normalized = str(side).lower()
    if normalized not in {"call", "put"} or context.direction == "INSUFFICIENT":
        return DirectionPermission(False, 0.0, "UNKNOWN", "verified multi-timeframe direction unavailable")
    if context.direction in {"FLAT", "MIXED"}:
        multiplier = .35 if context.direction == "MIXED" else .25
        return DirectionPermission(True, multiplier, "MIXED", "timeframes do not agree; reduced directional size")
    aligned = (normalized == "call" and context.direction == "UP") or (
        normalized == "put" and context.direction == "DOWN"
    )
    if aligned:
        multiplier = _clamp(.55 + .45 * context.confidence, .55, 1.0)
        return DirectionPermission(True, multiplier, "ALIGNED", "setup agrees with verified multi-timeframe direction")
    confirmed = context.up_reversal_confirmed if normalized == "call" else context.down_reversal_confirmed
    if countertrend_setup and confirmed:
        multiplier = _clamp(.20 + .25 * context.confidence, .20, .45)
        return DirectionPermission(True, multiplier, "COUNTERTREND", "countertrend reversal has multi-factor confirmation")
    return DirectionPermission(False, 0.0, "COUNTERTREND", "setup conflicts with verified direction without confirmed reversal")
