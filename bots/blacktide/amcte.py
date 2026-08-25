"""Adaptive Market-Control Transition Engine (private BLACKTIDE intelligence)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt
from statistics import fmean, pstdev
from typing import Any


class MarketState(str, Enum):
    DISORDER = "DISORDER"
    BALANCE = "BALANCE"
    PRESSURE_BUILD = "PRESSURE_BUILD"
    IGNITION = "IGNITION"
    EXPANSION = "EXPANSION"
    MATURE_EXPANSION = "MATURE_EXPANSION"
    EXHAUSTION = "EXHAUSTION"
    FAILED_EXPANSION = "FAILED_EXPANSION"
    REVERSAL_CONTROL = "REVERSAL_CONTROL"


@dataclass(frozen=True)
class MarketVector:
    price: float
    structure: float
    efficiency: float
    velocity: float
    acceleration: float
    persistence: float
    participation: float
    volatility: float
    location: float
    options_quality: float
    bull_control: float
    bear_control: float
    control_delta: float
    control_acceleration: float
    conflict: float
    state: MarketState


@dataclass(frozen=True)
class Opportunity:
    family: str
    side: str
    score: float
    vector: MarketVector


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _aggregate(closes: list[float], width: int) -> list[float]:
    # Only completed groups; an unfinished higher-timeframe candle is inaccessible.
    return [closes[i + width - 1] for i in range(0, len(closes) - width + 1, width)]


def build_vector(bars: list[dict[str, Any]], *, options_quality: float) -> MarketVector | None:
    if len(bars) < 45:
        return None
    closes = [float(b["close"]) for b in bars]
    highs = [float(b.get("high", b["close"])) for b in bars]
    lows = [float(b.get("low", b["close"])) for b in bars]
    volumes = [float(b.get("volume") or 0) for b in bars]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(returns) < 30:
        return None
    r3, r5, r15 = (_aggregate(closes, n) for n in (3, 5, 15))
    if min(len(r3), len(r5), len(r15)) < 2:
        return None
    velocity = returns[-1]
    acceleration = returns[-1] - fmean(returns[-4:-1])
    direction = 1.0 if velocity >= 0 else -1.0
    persistence = sum((r >= 0) == (velocity >= 0) for r in returns[-10:]) / 10
    path = sum(abs(r) for r in returns[-15:]) or 1e-12
    efficiency = abs(closes[-1] / closes[-16] - 1) / path
    volatility = pstdev(returns[-20:]) * sqrt(390)
    recent_range = max(highs[-20:]) - min(lows[-20:])
    location = 0.5 if recent_range <= 0 else (closes[-1] - min(lows[-20:])) / recent_range
    base_volume = fmean(volumes[-30:-10]) if any(volumes[-30:-10]) else 0
    participation = _clamp(fmean(volumes[-5:]) / base_volume / 2) if base_volume else 0
    alignment = sum((series[-1] > series[-2]) for series in (r3, r5, r15)) / 3
    bull = _clamp(.28 * alignment + .22 * efficiency + .18 * persistence * (direction > 0)
                  + .16 * participation + .16 * location)
    bear = _clamp(.28 * (1 - alignment) + .22 * efficiency + .18 * persistence * (direction < 0)
                  + .16 * participation + .16 * (1 - location))
    delta = bull - bear
    prior_direction = 1 if fmean(returns[-6:-1]) >= 0 else -1
    control_acceleration = delta - prior_direction * min(abs(delta), .25)
    conflict = _clamp(1 - abs(delta) + min(bull, bear) / 2)
    structure = _clamp(abs(r15[-1] / r15[-2] - 1) / max(volatility / sqrt(390), 1e-6) / 3)
    state = classify_state(delta, control_acceleration, efficiency, volatility, conflict, participation)
    return MarketVector(closes[-1], structure, efficiency, velocity, acceleration,
                        persistence, participation, volatility, location, options_quality,
                        bull, bear, delta, control_acceleration, conflict, state)


def classify_state(delta: float, accel: float, efficiency: float, volatility: float,
                   conflict: float, participation: float) -> MarketState:
    dominance = abs(delta)
    if conflict > .82 and volatility > .018:
        return MarketState.DISORDER
    if dominance < .12 and volatility < .012:
        return MarketState.BALANCE
    if dominance < .22 and abs(accel) > .08:
        return MarketState.PRESSURE_BUILD
    if dominance >= .22 and abs(accel) >= .08 and participation >= .35:
        return MarketState.IGNITION
    if dominance >= .38 and efficiency >= .45:
        return MarketState.EXPANSION if abs(accel) >= .02 else MarketState.MATURE_EXPANSION
    if dominance >= .30 and accel * delta < 0:
        return MarketState.EXHAUSTION
    if efficiency < .25 and dominance >= .20:
        return MarketState.FAILED_EXPANSION
    if dominance >= .25 and abs(accel) >= .10 and accel * delta > 0:
        return MarketState.REVERSAL_CONTROL
    return MarketState.BALANCE


def opportunity(vector: MarketVector, *, threshold: float) -> Opportunity | None:
    if vector.state in (MarketState.DISORDER, MarketState.BALANCE) or vector.options_quality < .65:
        return None
    side = "call" if vector.control_delta > 0 else "put"
    family = {
        MarketState.IGNITION: "IGNITION_TRANSITION",
        MarketState.EXPANSION: "CONTROLLED_CONTINUATION",
        MarketState.MATURE_EXPANSION: "CONTROLLED_CONTINUATION",
        MarketState.FAILED_EXPANSION: "FAILED_CONTROL_REVERSAL",
        MarketState.REVERSAL_CONTROL: "FAILED_CONTROL_REVERSAL",
        MarketState.PRESSURE_BUILD: "PRESSURE_COMPRESSION_RELEASE",
    }.get(vector.state)
    if family is None:
        return None
    score = (0.16 * vector.structure + 0.16 * abs(vector.control_delta)
             + 0.14 * _clamp(abs(vector.control_acceleration) * 3)
             + 0.14 * vector.efficiency + 0.12 * vector.participation
             + 0.10 * (1 - vector.conflict) + 0.08 * vector.options_quality
             + 0.10 * _clamp(1 - abs(vector.volatility - .015) / .03))
    return Opportunity(family, side, score, vector) if score >= threshold else None
