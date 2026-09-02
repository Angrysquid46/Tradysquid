"""GROK independent decision engine — DEGEN / TRADE MODE.

Goal: actually take SPY 0DTE paper trades when the shared tape exists.
Hard constraints stay with the referee ($1k, one position). Soft filters
that produced zero trades are gone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SetupCandidate:
    family: str
    side: str
    score: float
    confidence: float
    reason: str
    features_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    action: str
    side: str | None = None
    family: str | None = None
    confidence: float = 0.0
    reason: str = ""
    candidates_considered: list[SetupCandidate] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)


BOOTSTRAP_PARAMS = {
    "min_confidence_to_enter": 0.30,
    "min_score_to_consider": 0.12,
    "max_spread_pct": 0.50,
    "min_volume": 0,
    "min_open_interest": 0,
    "preferred_delta_range": (0.05, 0.85),
    "max_hold_minutes": 180,
    "eod_flatten_minutes_before_close": 8,
    "hard_stop_pct": -0.45,
    "soft_stop_pct": -0.28,
    "runner_arm_pct": 0.35,
    "runner_trail_giveback": 0.18,
    "moon_target_pct": 1.20,
    "quick_scalp_pct": 0.40,
}


def score_momentum(features: dict[str, Any]) -> SetupCandidate | None:
    ret_5 = features.get("ret_5m")
    ret_3 = features.get("ret_3m")
    rsi = features.get("rsi_14")
    adx = features.get("adx_14")
    r = ret_5 if ret_5 is not None else ret_3
    if r is None:
        return None

    # Any meaningful short-horizon drift
    if abs(r) < 0.00015:
        return None

    side = "CALL" if r > 0 else "PUT"
    score = min(0.70, 0.20 + abs(r) * 150)
    if rsi is not None:
        if side == "CALL" and rsi >= 50:
            score += 0.08
        if side == "PUT" and rsi <= 50:
            score += 0.08
    if adx is not None and adx > 12:
        score += 0.08

    confidence = min(0.97, 0.32 + score)
    return SetupCandidate(
        family="momentum",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"tape {r:+.5f}",
        features_snapshot={"ret": r, "rsi_14": rsi, "adx_14": adx},
    )


def score_compression_release(features: dict[str, Any]) -> SetupCandidate | None:
    bb_width = features.get("bb_width")
    ret_3 = features.get("ret_3m")
    if bb_width is None or ret_3 is None:
        return None
    if bb_width > 0.025 or abs(ret_3) < 0.0002:
        return None
    side = "CALL" if ret_3 > 0 else "PUT"
    score = 0.25 + min(abs(ret_3) * 100, 0.40)
    confidence = min(0.95, 0.35 + score * 0.6)
    return SetupCandidate(
        family="compression_release",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"squeeze {bb_width:.4f} blast {ret_3:+.5f}",
        features_snapshot={"bb_width": bb_width, "ret_3m": ret_3},
    )


def score_vwap_reclaim(features: dict[str, Any]) -> SetupCandidate | None:
    vwap_dist = features.get("vwap_distance_pct")
    if vwap_dist is None:
        return None
    if abs(vwap_dist) > 0.01:
        return None
    if abs(vwap_dist) < 0.0001:
        return None
    side = "CALL" if vwap_dist > 0 else "PUT"
    return SetupCandidate(
        family="vwap_reclaim",
        side=side,
        score=0.30,
        confidence=0.40,
        reason=f"vwap {vwap_dist:+.5f}",
        features_snapshot={"vwap_distance_pct": vwap_dist},
    )


def score_panic_chase(features: dict[str, Any]) -> SetupCandidate | None:
    ret_5 = features.get("ret_5m")
    if ret_5 is None or abs(ret_5) < 0.0010:
        return None
    side = "CALL" if ret_5 > 0 else "PUT"
    score = 0.40 + min(abs(ret_5) * 60, 0.40)
    confidence = min(0.98, 0.45 + score * 0.4)
    return SetupCandidate(
        family="panic_chase",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"violent {ret_5:+.5f}",
        features_snapshot={"ret_5m": ret_5},
    )


def score_last_print(features: dict[str, Any]) -> SetupCandidate | None:
    """Last-resort: 1-bar direction so we do not sit flat on a live session."""
    # Approximate 1-bar from ret_3 if available by residual; else use ret_3/ret_5 sign
    ret_3 = features.get("ret_3m")
    ret_5 = features.get("ret_5m")
    last = features.get("last_close")
    if ret_3 is None and ret_5 is None:
        return None
    r = ret_3 if ret_3 is not None else ret_5
    if r is None or abs(r) < 0.00005:
        return None
    side = "CALL" if r > 0 else "PUT"
    return SetupCandidate(
        family="last_print",
        side=side,
        score=0.18,
        confidence=0.34,
        reason=f"last_print bias {r:+.5f} last={last}",
        features_snapshot={"ret": r, "last_close": last},
    )


FAMILY_SCORERS = [
    score_momentum,
    score_compression_release,
    score_vwap_reclaim,
    score_panic_chase,
    score_last_print,
]


def evaluate_entry(
    features: dict[str, Any],
    chain: list[dict[str, Any]],
    bankroll: float,
    params: dict[str, Any] | None = None,
) -> Decision:
    p = {**BOOTSTRAP_PARAMS, **(params or {})}

    if not features:
        return Decision(action="NO_ACTION", reason="no features")
    if not chain:
        return Decision(action="NO_ACTION", reason="empty chain")

    candidates: list[SetupCandidate] = []
    rejected: list[dict[str, str]] = []

    for scorer in FAMILY_SCORERS:
        cand = scorer(features)
        if cand is None:
            continue
        if cand.score < p["min_score_to_consider"]:
            rejected.append({"family": cand.family, "reason": "score below threshold"})
            continue
        if cand.confidence < p["min_confidence_to_enter"]:
            rejected.append({"family": cand.family, "reason": "confidence below threshold"})
            continue
        candidates.append(cand)

    if not candidates:
        return Decision(
            action="NO_ACTION",
            reason="no setup cleared",
            rejected=rejected,
        )

    best = max(candidates, key=lambda c: (c.confidence, c.score))
    return Decision(
        action="ENTER",
        side=best.side,
        family=best.family,
        confidence=best.confidence,
        reason=best.reason,
        candidates_considered=candidates,
        rejected=rejected,
    )


def evaluate_exit(
    position: dict[str, Any],
    features: dict[str, Any],
    current_bid: float,
    minutes_held: float,
    minutes_to_close: float,
    params: dict[str, Any] | None = None,
    peak_pnl_pct: float | None = None,
) -> Decision:
    p = {**BOOTSTRAP_PARAMS, **(params or {})}

    if minutes_to_close <= p["eod_flatten_minutes_before_close"]:
        return Decision(action="EXIT", reason="eod flatten")

    if minutes_held >= p["max_hold_minutes"]:
        return Decision(action="EXIT", reason="time stop")

    entry_price = float(position.get("entry_price") or 0.0)
    if entry_price <= 0 or current_bid <= 0:
        return Decision(action="HOLD", reason="waiting on bid")

    pnl_pct = (current_bid - entry_price) / entry_price
    peak = peak_pnl_pct if peak_pnl_pct is not None else pnl_pct

    if pnl_pct <= p["hard_stop_pct"]:
        return Decision(action="EXIT", reason=f"hard stop {pnl_pct:.0%}")

    if pnl_pct <= p["soft_stop_pct"] and minutes_held >= 8:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < -0.001:
                return Decision(action="EXIT", reason=f"soft stop {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0.001:
                return Decision(action="EXIT", reason=f"soft stop {pnl_pct:.0%}")

    if pnl_pct >= p["moon_target_pct"]:
        return Decision(action="EXIT", reason=f"moon {pnl_pct:.0%}")

    if peak >= p["runner_arm_pct"] and (peak - pnl_pct) >= p["runner_trail_giveback"]:
        return Decision(action="EXIT", reason=f"trail {peak:.0%}→{pnl_pct:.0%}")

    if pnl_pct >= p["quick_scalp_pct"] and minutes_held <= 12:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < 0:
                return Decision(action="EXIT", reason=f"scalp {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0:
                return Decision(action="EXIT", reason=f"scalp {pnl_pct:.0%}")

    ret_5 = features.get("ret_5m")
    side = str(position.get("side") or "").upper()
    if ret_5 is not None:
        if side in ("CALL", "C") and ret_5 < -0.003:
            return Decision(action="EXIT", reason="thesis dead call")
        if side in ("PUT", "P") and ret_5 > 0.003:
            return Decision(action="EXIT", reason="thesis dead put")

    return Decision(action="HOLD", reason=f"ride {pnl_pct:+.0%}")
