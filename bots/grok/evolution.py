"""GROK's evidence-gated evolution for its aggressive tape-trading style."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from bots.grok.engine import BOOTSTRAP_PARAMS
from bots.grok.state import GrokPrivateState, StrategyVersion, load_state, save_state

MIN_SAMPLE = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def propose_version(
    description: str,
    parameters: dict[str, Any],
    parent_version: str | None = None,
) -> StrategyVersion:
    state = load_state()
    version_id = f"v0.{len(state.strategy_versions) + 1}.0"
    ver = StrategyVersion(
        version_id=version_id,
        created_at=_now_iso(),
        description=description,
        parameters=parameters,
        parent_version=parent_version or state.strategy_version,
        promoted=False,
        validation_notes="pending walk-forward",
    )
    state.strategy_versions.append({
        "version_id": ver.version_id,
        "created_at": ver.created_at,
        "description": ver.description,
        "parameters": ver.parameters,
        "parent_version": ver.parent_version,
        "promoted": False,
        "validation_notes": ver.validation_notes,
    })
    save_state(state)
    return ver


def promote_version(version_id: str, validation_notes: str) -> bool:
    """Promote only after explicit validation evidence is attached."""
    state = load_state()
    for v in state.strategy_versions:
        if v["version_id"] == version_id:
            if "pending" in (v.get("validation_notes") or ""):
                return False  # refuse blind promotion
            v["promoted"] = True
            v["validation_notes"] = validation_notes
            state.strategy_version = version_id
            save_state(state)
            return True
    return False


def active_parameters(state: GrokPrivateState) -> dict[str, Any]:
    for version in reversed(state.strategy_versions):
        if version.get("version_id") == state.strategy_version and version.get("promoted"):
            return {**BOOTSTRAP_PARAMS, **version.get("parameters", {})}
    return dict(BOOTSTRAP_PARAMS)


def derive_policy(trades: list[dict[str, Any]], current: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a challenger using chronological train/holdout agreement.

    This is an online contextual bandit update, not a fabricated counterfactual
    backtest: it changes selection preference only for families GROK actually
    traded and observed.
    """
    params={**BOOTSTRAP_PARAMS,**current}; biases={}; evidence={}
    for family in sorted({str(t.get("family") or "unknown") for t in trades}):
        values=[float(t["return_pct"]) for t in trades if str(t.get("family") or "unknown")==family]
        if len(values)<MIN_SAMPLE:
            evidence[family]={"sample":len(values),"status":"INSUFFICIENT"}; continue
        split=max(4,int(len(values)*.7)); train,holdout=values[:split],values[split:]
        if len(holdout)<2:
            evidence[family]={"sample":len(values),"status":"INSUFFICIENT_HOLDOUT"}; continue
        a,b=fmean(train),fmean(holdout)
        stable=(a>0 and b>0) or (a<0 and b<0)
        bias=max(-.22,min(.12,(.35*a+.65*b)*1.2)) if stable else 0.0
        if abs(bias)>=.015: biases[family]=bias
        evidence[family]={"sample":len(values),"train":a,"holdout":b,"bias":bias,"status":"PROMOTED" if abs(bias)>=.015 else "REJECTED_UNSTABLE"}
    recent=[float(t["return_pct"]) for t in trades[-24:]]
    mean=fmean(recent) if recent else 0.0; win=sum(v>0 for v in recent)/len(recent) if recent else .5
    params["family_bias"]=biases
    params["risk_multiplier"]=.35 if len(recent)>=8 and (mean<-.04 or win<.38) else .65 if len(recent)>=8 and mean<=0 else 1.0
    params["min_confidence_to_enter"]=.42 if len(recent)>=8 and mean<-.04 else .34 if len(recent)>=8 and mean<=0 else .30
    return params,{"sample":len(trades),"recent_mean":mean,"recent_win_rate":win,"families":evidence}


def evolve_state(state: GrokPrivateState) -> dict[str, Any]:
    trades=list(state.learning_metrics.get("trades") or [])
    current=active_parameters(state)
    challenger,evidence=derive_policy(trades,current)
    comparable={k:v for k,v in current.items() if k in challenger}
    if challenger==comparable:
        return {**evidence,"promoted":False,"version":state.strategy_version}
    version_id=f"v0.{len(state.strategy_versions)+2}.0"
    state.strategy_versions.append({
        "version_id":version_id,"created_at":_now_iso(),"description":"outcome-validated aggressive tape policy",
        "parameters":challenger,"parent_version":state.strategy_version,"promoted":True,
        "validation_notes":"chronological per-family train/holdout agreement; recent risk gate",
    })
    state.strategy_version=version_id
    return {**evidence,"promoted":True,"version":version_id,"parameters":challenger}
