"""GROK independent decision engine — DEGEN MODE.

Philosophy: SPY 0DTE is a casino with a tape. Size into conviction, hunt
asymmetry, cut dead money, let runners cook, and if you go broke the
referee hands you another $1,000. Hard constraints (one position, bankroll
ceiling) are enforced by the neutral scoreboard — everything else is fair game.

Does not import or derive from any other competitor's private strategy.
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


# Aggressive bootstrap — evolve from own busts/wins later.
# Lower bars = more swings. Hard bankroll rules live in scoreboard, not here.
BOOTSTRAP_PARAMS = {
    "min_confidence_to_enter": 0.42,
    "min_score_to_consider": 0.28,
    "max_spread_pct": 0.35,
    "min_volume": 10,
    "min_open_interest": 25,
    "preferred_delta_range": (0.12, 0.70),
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
    """Chase short-horizon SPY flow hard."""
    ret_5 = features.get("ret_5m")
    ret_3 = features.get("ret_3m")
    rsi = features.get("rsi_14")
    adx = features.get("adx_14")
    if ret_5 is None and ret_3 is None:
        return None

    r = ret_5 if ret_5 is not None else ret_3
    score = 0.0
    side = None
    parts: list[str] = []

    # Lower bar than the careful version — we want swings
    if r is not None and r > 0.0006:
        side = "CALL"
        score += min(abs(r) * 120, 0.55)
        parts.append(f"rip {r:.4f}")
        if rsi is not None and rsi >= 52:
            score += 0.12
            parts.append(f"RSI {rsi:.0f}")
        if adx is not None and adx > 18:
            score += 0.12
            parts.append(f"ADX {adx:.0f}")
    elif r is not None and r < -0.0006:
        side = "PUT"
        score += min(abs(r) * 120, 0.55)
        parts.append(f"dump {r:.4f}")
        if rsi is not None and rsi <= 48:
            score += 0.12
            parts.append(f"RSI {rsi:.0f}")
        if adx is not None and adx > 18:
            score += 0.12
            parts.append(f"ADX {adx:.0f}")

    if side is None or score < 0.22:
        return None

    confidence = min(0.97, 0.38 + score)
    return SetupCandidate(
        family="momentum",
        side=side,
        score=score,
        confidence=confidence,
        reason="; ".join(parts),
        features_snapshot={"ret_5m": ret_5, "ret_3m": ret_3, "rsi_14": rsi, "adx_14": adx},
    )


def score_compression_release(features: dict[str, Any]) -> SetupCandidate | None:
    """Squeeze → expansion = lottery ticket window."""
    bb_width = features.get("bb_width")
    ret_3 = features.get("ret_3m")
    if bb_width is None or ret_3 is None:
        return None
    # Accept slightly wider "compression" so we fire more often
    if bb_width > 0.018:
        return None
    if abs(ret_3) < 0.0004:
        return None

    side = "CALL" if ret_3 > 0 else "PUT"
    score = 0.32 + min(abs(ret_3) * 90, 0.40)
    confidence = min(0.95, 0.40 + score * 0.7)
    return SetupCandidate(
        family="compression_release",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"squeeze {bb_width:.4f} + blast {ret_3:.4f}",
        features_snapshot={"bb_width": bb_width, "ret_3m": ret_3},
    )


def score_vwap_reclaim(features: dict[str, Any]) -> SetupCandidate | None:
    """VWAP flip with any volume pulse."""
    vwap_dist = features.get("vwap_distance_pct")
    rel_vol = features.get("relative_volume")
    if vwap_dist is None:
        return None
    if abs(vwap_dist) > 0.006:
        return None

    vol_ok = rel_vol is None or rel_vol >= 0.85
    if vwap_dist > 0.0002 and vol_ok:
        return SetupCandidate(
            family="vwap_reclaim",
            side="CALL",
            score=0.38,
            confidence=0.50,
            reason=f"VWAP reclaim {vwap_dist:.4f}",
            features_snapshot={"vwap_distance_pct": vwap_dist, "relative_volume": rel_vol},
        )
    if vwap_dist < -0.0002 and vol_ok:
        return SetupCandidate(
            family="vwap_reclaim",
            side="PUT",
            score=0.38,
            confidence=0.50,
            reason=f"VWAP reject {vwap_dist:.4f}",
            features_snapshot={"vwap_distance_pct": vwap_dist, "relative_volume": rel_vol},
        )
    return None


def score_panic_chase(features: dict[str, Any]) -> SetupCandidate | None:
    """Big 5m move = lean into continuation (degen trend follow)."""
    ret_5 = features.get("ret_5m")
    rel_vol = features.get("relative_volume")
    if ret_5 is None:
        return None
    if abs(ret_5) < 0.0025:
        return None
    side = "CALL" if ret_5 > 0 else "PUT"
    score = 0.45 + min(abs(ret_5) * 50, 0.35)
    if rel_vol is not None and rel_vol > 1.3:
        score += 0.12
    confidence = min(0.98, 0.48 + score * 0.5)
    return SetupCandidate(
        family="panic_chase",
        side=side,
        score=score,
        confidence=confidence,
        reason=f"violent move {ret_5:.4f} lean continuation",
        features_snapshot={"ret_5m": ret_5, "relative_volume": rel_vol},
    )


FAMILY_SCORERS = [
    score_momentum,
    score_compression_release,
    score_vwap_reclaim,
    score_panic_chase,
]


def evaluate_entry(
    features: dict[str, Any],
    chain: list[dict[str, Any]],
    bankroll: float,
    params: dict[str, Any] | None = None,
) -> Decision:
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
        return Decision(action="NO_ACTION", reason="no degen setup cleared", rejected=rejected)

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
    """Aggressive management: cut losers, arm runners, moon-bag winners."""
    p = {**BOOTSTRAP_PARAMS, **(params or {})}

    if minutes_to_close <= p["eod_flatten_minutes_before_close"]:
        return Decision(action="EXIT", reason="eod flatten — no overnight 0DTE graves")

    if minutes_held >= p["max_hold_minutes"]:
        return Decision(action="EXIT", reason="time stop — capital rotation")

    entry_price = float(position.get("entry_price") or 0.0)
    if entry_price <= 0 or current_bid <= 0:
        return Decision(action="HOLD", reason="waiting on a real bid")

    pnl_pct = (current_bid - entry_price) / entry_price
    peak = peak_pnl_pct if peak_pnl_pct is not None else pnl_pct

    # Hard stop — still a floor so one trade doesn't always zero the gen instantly
    if pnl_pct <= p["hard_stop_pct"]:
        return Decision(action="EXIT", reason=f"hard stop {pnl_pct:.0%}")

    # Soft stop if thesis already dead early
    if pnl_pct <= p["soft_stop_pct"] and minutes_held >= 8:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < -0.001:
                return Decision(action="EXIT", reason=f"soft stop + thesis dead {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0.001:
                return Decision(action="EXIT", reason=f"soft stop + thesis dead {pnl_pct:.0%}")

    # Moon bag
    if pnl_pct >= p["moon_target_pct"]:
        return Decision(action="EXIT", reason=f"moon bag {pnl_pct:.0%}")

    # Runner: once armed, trail giveback from peak
    if peak >= p["runner_arm_pct"]:
        giveback = peak - pnl_pct
        if giveback >= p["runner_trail_giveback"]:
            return Decision(action="EXIT", reason=f"trail off peak {peak:.0%} → {pnl_pct:.0%}")

    # Quick scalp if it prints fast and stalls
    if pnl_pct >= p["quick_scalp_pct"] and minutes_held <= 12:
        ret_5 = features.get("ret_5m")
        side = str(position.get("side") or "").upper()
        if ret_5 is not None:
            if side in ("CALL", "C") and ret_5 < 0:
                return Decision(action="EXIT", reason=f"scalp lock {pnl_pct:.0%}")
            if side in ("PUT", "P") and ret_5 > 0:
                return Decision(action="EXIT", reason=f"scalp lock {pnl_pct:.0%}")

    # Thesis invalidation without full soft-stop hit
    ret_5 = features.get("ret_5m")
    side = str(position.get("side") or "").upper()
    if ret_5 is not None and side:
        if side in ("CALL", "C") and ret_5 < -0.003:
            return Decision(action="EXIT", reason="momentum flipped against call")
        if side in ("PUT", "P") and ret_5 > 0.003:
            return Decision(action="EXIT", reason="momentum flipped against put")

    return Decision(action="HOLD", reason=f"ride {pnl_pct:+.0%} (peak {peak:+.0%})")
