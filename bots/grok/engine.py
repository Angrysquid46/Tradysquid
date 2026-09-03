"""GROK independent decision engine — DEGEN / ACTUALLY TRADE MODE.

Hard constraints stay in the scoreboard ($1k, one position). Entry thresholds
are intentionally low: if the shared 1m tape has a direction, take a side.
Sitting flat all day with live data is failure, not discipline.
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


def _primary_return(features: dict[str, Any]) -> float | None:
    for key in ("ret_3m", "ret_5m"):
        v = features.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def score_momentum(features: dict[str, Any]) -> SetupCandidate | None:
    r = _primary_return(features)
    rsi = features.get("rsi_14")
    adx = features.get("adx_14")
    if r is None:
        return None
    if abs(r) < 0.00015:  # ~1.5 cents on SPY ~$500 — still a lean
        return None
    side = "CALL" if r > 0 else "PUT"
    score = 0.20 + min(abs(r) * 150, 0.55)
    parts = [f"tape {r:+.5f}"]
    if rsi is not None:
        if side == "CALL" and rsi >= 50:
            score += 0.10
            parts.append(f"RSI {rsi:.0f}")
        if side == "PUT" and rsi <= 50:
            score += 0.10
            parts.append(f"RSI {rsi:.0f}")
    if adx is not None and adx > 12:
        score += 0.08
        parts.append(f"ADX {adx:.0f}")
    confidence = min(0.97, 0.32 + score)
    return SetupCandidate(
        family="momentum",
        side=side,
        score=score,
        confidence=confidence,
        reason="; ".join(parts),
        features_snapshot={"ret": r, "rsi_14": rsi, "adx_14": adx},
    )


def score_compression_release(features: dict[str, Any]) -> SetupCandidate | None:
    bb_width = features.get("bb_width")
    ret_3 = features.get("ret_3m")
    if bb_width is None or ret_3 is None:
        return None
    if bb_width > 0.025:
        return None
    if abs(ret_3) < 0.0002:
        return None
    side = "CALL" if ret_3 > 0 else "PUT"
    score = 0.28 + min(abs(ret_3) * 100, 0.40)
    confidence = min(0.95, 0.35 + score * 0.7)
    return SetupCandidate(
        family="compression_release",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"squeeze {bb_width:.4f} + blast {ret_3:.4f}",
        features_snapshot={"bb_width": bb_width, "ret_3m": ret_3},
    )


def score_vwap_reclaim(features: dict[str, Any]) -> SetupCandidate | None:
    vwap_dist = features.get("vwap_distance_pct")
    rel_vol = features.get("relative_volume")
    if vwap_dist is None:
        return None
    if abs(vwap_dist) > 0.012:
        return None
    vol_ok = rel_vol is None or rel_vol >= 0.5
    if abs(vwap_dist) < 0.00005:
        return None
    if not vol_ok:
        return None
    side = "CALL" if vwap_dist > 0 else "PUT"
    return SetupCandidate(
        family="vwap_reclaim",
        side=side,
        score=0.32,
        confidence=0.45,
        reason=f"VWAP side {vwap_dist:+.5f}",
        features_snapshot={"vwap_distance_pct": vwap_dist, "relative_volume": rel_vol},
    )


def score_panic_chase(features: dict[str, Any]) -> SetupCandidate | None:
    ret_5 = features.get("ret_5m")
    rel_vol = features.get("relative_volume")
    if ret_5 is None or abs(ret_5) < 0.0012:
        return None
    side = "CALL" if ret_5 > 0 else "PUT"
    score = 0.40 + min(abs(ret_5) * 60, 0.40)
    if rel_vol is not None and rel_vol > 1.1:
        score += 0.10
    confidence = min(0.98, 0.45 + score * 0.5)
    return SetupCandidate(
        family="panic_chase",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"violent move {ret_5:.4f}",
        features_snapshot={"ret_5m": ret_5, "relative_volume": rel_vol},
    )


def score_tape_bias(features: dict[str, Any]) -> SetupCandidate | None:
    """Last-resort directional lean so sessions are not zero-trade by default."""
    r = _primary_return(features)
    vwap_dist = features.get("vwap_distance_pct")
    last = features.get("last_close")
    if r is None and vwap_dist is None:
        return None
    if r is not None and abs(r) >= 0.00008:
        side = "CALL" if r > 0 else "PUT"
        return SetupCandidate(
            family="tape_bias",
            side=side,
            score=0.18,
            confidence=0.36,
            reason=f"session lean {r:+.5f}",
            features_snapshot={"ret": r, "last_close": last},
        )
    if vwap_dist is not None and abs(vwap_dist) >= 0.00008:
        side = "CALL" if vwap_dist > 0 else "PUT"
        return SetupCandidate(
            family="tape_bias",
            side=side,
            score=0.16,
            confidence=0.34,
            reason=f"vwap lean {vwap_dist:+.5f}",
            features_snapshot={"vwap_distance_pct": vwap_dist, "last_close": last},
        )
    return None


FAMILY_SCORERS = [
    score_momentum,
    score_compression_release,
    score_vwap_reclaim,
    score_panic_chase,
    score_tape_bias,
]


def evaluate_entry(
    features: dict[str, Any],
    chain: list[dict[str, Any]],
    bankroll: float,
    params: dict[str, Any] | None = None,
) -> Decision:
    p = {**BOOTSTRAP_PARAMS, **(params or {})}
    if not features:
        return Decision(action="NO_ACTION", reason="no features — tape missing")
    if not chain:
        return Decision(action="NO_ACTION", reason="no chain — cannot select contract")

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
            reason=f"no setup cleared (features keys={list(features.keys())})",
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
        return Decision(action="HOLD", reason="waiting on a real bid")

    pnl_pct = (current_bid - entry_price) / entry_price
    peak = peak_pnl_pct if peak_pnl_pct is not None else pnl_pct

    if pnl_pct <= p["hard_stop_pct"]:
        return Decision(action="EXIT", reason=f"hard stop {pnl_pct:.0%}")

    if pnl_pct <= p["soft_stop_pct"] and minutes_held >= 8:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < -0.001:
                return Decision(action="EXIT", reason=f"soft stop + thesis dead {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0.001:
                return Decision(action="EXIT", reason=f"soft stop + thesis dead {pnl_pct:.0%}")

    if pnl_pct >= p["moon_target_pct"]:
        return Decision(action="EXIT", reason=f"moon bag {pnl_pct:.0%}")

    if peak >= p["runner_arm_pct"]:
        giveback = peak - pnl_pct
        if giveback >= p["runner_trail_giveback"]:
            return Decision(action="EXIT", reason=f"trail off peak {peak:.0%} → {pnl_pct:.0%}")

    if pnl_pct >= p["quick_scalp_pct"] and minutes_held <= 12:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < 0:
                return Decision(action="EXIT", reason=f"scalp lock {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0:
                return Decision(action="EXIT", reason=f"scalp lock {pnl_pct:.0%}")

    ret_5 = features.get("ret_5m")
    side = str(position.get("side") or "").upper()
    if ret_5 is not None and side:
        if side in ("CALL", "C") and ret_5 < -0.003:
            return Decision(action="EXIT", reason="momentum flipped against call")
        if side in ("PUT", "P") and ret_5 > 0.003:
            return Decision(action="EXIT", reason="momentum flipped against put")

    return Decision(action="HOLD", reason=f"ride {pnl_pct:+.0%} (peak {peak:+.0%})")
