"""GROK independent decision engine.

Designed from first principles. Does not import or derive from any other
competitor's private strategy modules.

Core idea:
- Observe causal market state (shared features + 0DTE chain).
- Score multiple independent setup families.
- Require agreement / confidence threshold before acting.
- Explicit contract selection and position sizing layers.
- Thesis-aware exits managed separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SetupCandidate:
    family: str
    side: str  # "CALL" or "PUT"
    score: float
    confidence: float
    reason: str
    features_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    action: str  # "NO_ACTION" | "ENTER" | "EXIT" | "HOLD"
    side: str | None = None
    family: str | None = None
    confidence: float = 0.0
    reason: str = ""
    candidates_considered: list[SetupCandidate] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)


# Bootstrap parameters — will be evolved by learning.py / evolution.py
# These are deliberately simple starting points, not magic numbers copied
# from anyone else.
BOOTSTRAP_PARAMS = {
    "min_confidence_to_enter": 0.62,
    "min_score_to_consider": 0.45,
    "max_spread_pct": 0.18,
    "min_volume": 50,
    "min_open_interest": 100,
    "preferred_delta_range": (0.25, 0.55),
    "max_hold_minutes": 90,
    "eod_flatten_minutes_before_close": 15,
}


def score_momentum(features: dict[str, Any]) -> SetupCandidate | None:
    """Simple causal momentum family — price location + short-term persistence."""
    # Expect shared features such as short-horizon returns, RSI, ADX, etc.
    ret_5 = features.get("ret_5m")
    rsi = features.get("rsi_14")
    adx = features.get("adx_14")
    if ret_5 is None or rsi is None:
        return None

    score = 0.0
    side = None
    reason_parts = []

    if ret_5 > 0.0015 and rsi > 55:
        side = "CALL"
        score += min(ret_5 * 80, 0.45)
        reason_parts.append(f"positive 5m momentum {ret_5:.4f}")
        if adx and adx > 22:
            score += 0.15
            reason_parts.append(f"ADX {adx:.1f}")
    elif ret_5 < -0.0015 and rsi < 45:
        side = "PUT"
        score += min(abs(ret_5) * 80, 0.45)
        reason_parts.append(f"negative 5m momentum {ret_5:.4f}")
        if adx and adx > 22:
            score += 0.15
            reason_parts.append(f"ADX {adx:.1f}")

    if side is None or score < 0.3:
        return None

    confidence = min(0.95, 0.4 + score)
    return SetupCandidate(
        family="momentum",
        side=side,
        score=score,
        confidence=confidence,
        reason="; ".join(reason_parts),
        features_snapshot={"ret_5m": ret_5, "rsi_14": rsi, "adx_14": adx},
    )


def score_compression_release(features: dict[str, Any]) -> SetupCandidate | None:
    """Volatility compression followed by directional expansion."""
    bb_width = features.get("bb_width")
    ret_3 = features.get("ret_3m")
    if bb_width is None or ret_3 is None:
        return None

    # Very rough bootstrap: narrow bands + recent expansion
    if bb_width > 0.012:  # not compressed
        return None

    if abs(ret_3) < 0.0008:
        return None

    side = "CALL" if ret_3 > 0 else "PUT"
    score = 0.35 + min(abs(ret_3) * 60, 0.3)
    confidence = min(0.9, 0.45 + score * 0.6)
    return SetupCandidate(
        family="compression_release",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"narrow BB width {bb_width:.4f} + expansion {ret_3:.4f}",
        features_snapshot={"bb_width": bb_width, "ret_3m": ret_3},
    )


def score_vwap_reclaim(features: dict[str, Any]) -> SetupCandidate | None:
    """Price reclaiming or rejecting VWAP with volume confirmation."""
    vwap_dist = features.get("vwap_distance_pct")
    rel_vol = features.get("relative_volume")
    if vwap_dist is None:
        return None

    if abs(vwap_dist) > 0.004:  # already extended
        return None

    if vwap_dist > 0.0005 and (rel_vol is None or rel_vol > 1.1):
        return SetupCandidate(
            family="vwap_reclaim",
            side="CALL",
            score=0.4,
            confidence=0.55,
            reason=f"VWAP reclaim {vwap_dist:.4f}",
            features_snapshot={"vwap_distance_pct": vwap_dist, "relative_volume": rel_vol},
        )
    if vwap_dist < -0.0005 and (rel_vol is None or rel_vol > 1.1):
        return SetupCandidate(
            family="vwap_reclaim",
            side="PUT",
            score=0.4,
            confidence=0.55,
            reason=f"VWAP rejection {vwap_dist:.4f}",
            features_snapshot={"vwap_distance_pct": vwap_dist, "relative_volume": rel_vol},
        )
    return None


FAMILY_SCORERS = [
    score_momentum,
    score_compression_release,
    score_vwap_reclaim,
]


def evaluate_entry(
    features: dict[str, Any],
    chain: list[dict[str, Any]],
    bankroll: float,
    params: dict[str, Any] | None = None,
) -> Decision:
    """Main entry decision. Returns NO_ACTION unless a candidate clears thresholds."""
    p = {**BOOTSTRAP_PARAMS, **(params or {})}
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
        return Decision(action="NO_ACTION", reason="no setup cleared thresholds", rejected=rejected)

    # Pick highest confidence among survivors
    best = max(candidates, key=lambda c: c.confidence)
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
) -> Decision:
    """Thesis-aware + time + risk exit logic."""
    p = {**BOOTSTRAP_PARAMS, **(params or {})}

    if minutes_to_close <= p["eod_flatten_minutes_before_close"]:
        return Decision(action="EXIT", reason="end-of-day flatten")

    if minutes_held >= p["max_hold_minutes"]:
        return Decision(action="EXIT", reason="max hold time reached")

    entry_price = position.get("entry_price") or 0.0
    if entry_price <= 0:
        return Decision(action="HOLD", reason="missing entry price")

    pnl_pct = (current_bid - entry_price) / entry_price

    # Simple protective rules (will be evolved)
    if pnl_pct <= -0.35:
        return Decision(action="EXIT", reason=f"hard stop {pnl_pct:.1%}")
    if pnl_pct >= 0.60:
        return Decision(action="EXIT", reason=f"profit target {pnl_pct:.1%}")

    # Thesis check — if momentum has reversed hard, exit
    ret_5 = features.get("ret_5m")
    side = position.get("side")
    if ret_5 is not None and side:
        if side == "CALL" and ret_5 < -0.002:
            return Decision(action="EXIT", reason="momentum thesis invalidation")
        if side == "PUT" and ret_5 > 0.002:
            return Decision(action="EXIT", reason="momentum thesis invalidation")

    return Decision(action="HOLD", reason="thesis still valid")
