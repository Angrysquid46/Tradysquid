"""GROK private learning — observes only its own trades and decisions.

Never consumes another competitor's private entries, exits, thresholds,
or postmortems. Public scoreboard outcomes are allowed as context only.
"""

from __future__ import annotations

from typing import Any

from bots.grok.state import load_state, save_state


def record_decision_cycle(payload: dict[str, Any]) -> None:
    """Append decision-cycle telemetry for later diagnosis."""
    state = load_state()
    state.decision_log_tail.append(payload)
    state.decision_log_tail = state.decision_log_tail[-500:]
    save_state(state)


def record_completed_trade(trade_summary: dict[str, Any]) -> None:
    """Store rich private post-trade facts for learning."""
    state = load_state()
    metrics = state.learning_metrics.setdefault("trades", [])
    metrics.append(trade_summary)
    state.learning_metrics["trades"] = metrics[-1000:]
    save_state(state)


def diagnose_generation(generation: int, official_trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a private postmortem for a finished generation."""
    if not official_trades:
        return {"generation": generation, "note": "no trades", "suggestions": []}

    wins = [t for t in official_trades if (t.get("pnl_usd") or 0) > 0]
    losses = [t for t in official_trades if (t.get("pnl_usd") or 0) < 0]
    net = sum(t.get("pnl_usd") or 0 for t in official_trades)

    suggestions = []
    if len(losses) > len(wins) and net < 0:
        suggestions.append("entries or timing may be weak — raise confidence threshold")
    if losses and abs(sum(t["pnl_usd"] for t in losses)) > sum(t["pnl_usd"] for t in wins or [{"pnl_usd": 0}]):
        suggestions.append("losers larger than winners — tighten stops or exit earlier")

    return {
        "generation": generation,
        "trade_count": len(official_trades),
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl": net,
        "suggestions": suggestions,
    }


def propose_parameter_updates(diagnosis: dict[str, Any], current_params: dict[str, Any]) -> dict[str, Any]:
    """Evidence-light bootstrap evolution proposals. Full walk-forward comes later."""
    proposals = dict(current_params)
    for s in diagnosis.get("suggestions", []):
        if "confidence threshold" in s:
            proposals["min_confidence_to_enter"] = min(0.85, current_params.get("min_confidence_to_enter", 0.62) + 0.03)
        if "tighten stops" in s:
            proposals["hard_stop_pct"] = max(0.20, current_params.get("hard_stop_pct", 0.35) - 0.05)
    return proposals
