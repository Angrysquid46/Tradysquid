"""RIPTIDE contextual policy evolution from its own immutable outcomes.

Learning is deliberately causal: chronological training and holdout segments
must agree before a family or market-state preference is promoted.  The live
policy is rebuilt from evidence rather than repeatedly accumulating a fixed
penalty, and losing periods reduce both risk and experimentation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import fmean

from .engine import Riptide


STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "riptide"
MIN_FAMILY_SAMPLE = 8
MIN_CONTEXT_SAMPLE = 6
STATE_PATH = STATE_DIR / "promoted-learning.json"
RECEIPT_PATH = STATE_DIR / "evolution-receipts.jsonl"


@dataclass(frozen=True)
class Outcome:
    trade_id: str
    generation: int
    return_pct: float
    exit_reason: str
    closed_at: str
    family: str = "UNKNOWN"
    market_state: str = "UNKNOWN"
    policy_version: int = 1
    holding_minutes: float = 0.0


class EvolutionLoop:
    def __init__(self, path: Path | None = None, state_path: Path | None = None):
        self.path = path or STATE_DIR / "outcomes.jsonl"
        # A caller supplying an isolated outcome ledger (tests/research) must
        # never be able to overwrite the live promoted policy by omission.
        self.state_path = state_path or (STATE_PATH if path is None else self.path.with_name("promoted-learning.json"))

    def apply(self, engine: Riptide) -> None:
        if not self.state_path.exists(): return
        try:
            data=json.loads(self.state_path.read_text(encoding="utf-8"))
            engine.parameters=replace(
                engine.parameters,
                base_risk_fraction=float(data["risk"]),
                exploration_rate=float(data["exploration"]),
                family_bias=tuple((str(k),float(v)) for k,v in data.get("family_bias",{}).items()),
                context_bias=tuple((str(k),float(v)) for k,v in data.get("context_bias",{}).items()),
                policy_version=int(data.get("policy_version",1)),
            )
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return

    def load(self) -> list[Outcome]:
        if not self.path.exists():
            return []
        return [Outcome(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def record(self, outcome: Outcome) -> None:
        if outcome.trade_id in {row.trade_id for row in self.load()}:
            raise ValueError("completed RIPTIDE outcome is immutable")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(outcome), sort_keys=True) + "\n")

    @staticmethod
    def _validated_bias(values: list[float], minimum: int) -> tuple[float, dict[str, object]]:
        if len(values) < minimum:
            return 0.0, {"sample":len(values),"status":"INSUFFICIENT"}
        split=max(4,int(len(values)*.7)); train,holdout=values[:split],values[split:]
        if len(holdout)<2:
            return 0.0, {"sample":len(values),"status":"INSUFFICIENT_HOLDOUT"}
        train_mean,holdout_mean=fmean(train),fmean(holdout)
        same_sign=(train_mean>0 and holdout_mean>0) or (train_mean<0 and holdout_mean<0)
        # Shrink noisy realized option returns heavily; stable losers can be
        # quarantined while stable winners receive only modest preference.
        raw=(.7*holdout_mean+.3*train_mean) if same_sign else 0.0
        bias=max(-.45,min(.16,raw*1.5))
        status="PROMOTED" if same_sign and abs(bias)>=.015 else "REJECTED_UNSTABLE"
        return (bias if status=="PROMOTED" else 0.0), {
            "sample":len(values),"train":train_mean,"holdout":holdout_mean,"status":status,
        }

    def evaluate(self, engine: Riptide) -> dict[str, object]:
        rows = self.load()
        recent=[r.return_pct for r in rows[-32:]]
        recent_mean=fmean(recent) if recent else 0.0
        recent_win=sum(v>0 for v in recent)/len(recent) if recent else .5
        if len(recent)<8:
            risk,exploration=engine.parameters.base_risk_fraction,engine.parameters.exploration_rate
        elif recent_mean<-.03 or recent_win<.38:
            risk,exploration=.12,.05
        elif recent_mean> .04 and recent_win>.52:
            risk,exploration=.34,.14
        else:
            risk,exploration=.20,.08
        engine.parameters=replace(engine.parameters,base_risk_fraction=risk,exploration_rate=exploration)
        family_bias:dict[str,float]={}; context_bias:dict[str,float]={}; decisions={}
        for family in sorted({r.family for r in rows}):
            values=[r.return_pct for r in rows if r.family==family]
            bias,evidence=self._validated_bias(values,MIN_FAMILY_SAMPLE)
            if bias: family_bias[family]=bias
            decisions[f"family:{family}"]={**evidence,"bias":bias}
        contexts=sorted({(r.market_state,r.family) for r in rows if r.market_state!="UNKNOWN"})
        for market_state,family in contexts:
            values=[r.return_pct for r in rows if r.market_state==market_state and r.family==family]
            bias,evidence=self._validated_bias(values,MIN_CONTEXT_SAMPLE)
            key=f"{market_state}|{family}"
            if bias: context_bias[key]=bias
            decisions[f"context:{key}"]={**evidence,"bias":bias}
        old=(dict(engine.parameters.family_bias),dict(engine.parameters.context_bias),engine.parameters.base_risk_fraction,engine.parameters.exploration_rate)
        new=(family_bias,context_bias,engine.parameters.base_risk_fraction,engine.parameters.exploration_rate)
        version=engine.parameters.policy_version+(1 if old!=new else 0)
        engine.parameters=replace(engine.parameters,family_bias=tuple(sorted(family_bias.items())),context_bias=tuple(sorted(context_bias.items())),policy_version=version)
        state={"schema":2,"sample":len(rows),"policy_version":version,"risk":engine.parameters.base_risk_fraction,"exploration":engine.parameters.exploration_rate,"family_bias":family_bias,"context_bias":context_bias}
        self.state_path.parent.mkdir(parents=True,exist_ok=True); tmp=self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(state,sort_keys=True),encoding="utf-8"); tmp.replace(self.state_path)
        receipt_path=self.state_path.with_name("evolution-receipts.jsonl")
        with receipt_path.open("a",encoding="utf-8") as h:h.write(json.dumps({**state,"decisions":decisions,"promoted":old!=new},sort_keys=True)+"\n")
        return state
