"""RIPTIDE's own bounded, outcome-only adaptation ledger."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import fmean

from .engine import Riptide


STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "riptide"
MIN_FAMILY_SAMPLE = 6
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


class EvolutionLoop:
    def __init__(self, path: Path | None = None, state_path: Path | None = None):
        self.path = path or STATE_DIR / "outcomes.jsonl"
        self.state_path = state_path or STATE_PATH

    def apply(self, engine: Riptide) -> None:
        if not self.state_path.exists(): return
        try:
            data=json.loads(self.state_path.read_text(encoding="utf-8"))
            engine.parameters=replace(engine.parameters,base_risk_fraction=float(data["risk"]),exploration_rate=float(data["exploration"]),family_bias=tuple((str(k),float(v)) for k,v in data["family_bias"].items()))
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

    def evaluate(self, engine: Riptide) -> dict[str, object]:
        rows = self.load()
        engine.evolve(rows)
        bias=dict(engine.parameters.family_bias); decisions={}
        for family in sorted({r.family for r in rows}):
            sample=[r.return_pct for r in rows if r.family==family]
            if len(sample)<MIN_FAMILY_SAMPLE: continue
            split=max(4,int(len(sample)*.7)); train,holdout=sample[:split],sample[split:]
            if len(holdout)<2: continue
            train_score=fmean(train); holdout_score=fmean(holdout)
            change=-.06 if train_score<-.03 and holdout_score<-.03 else .025 if train_score>.02 and holdout_score>0 else 0
            if change:
                bias[family]=max(-.24,min(.12,bias.get(family,0)+change)); decisions[family]={"change":change,"train":train_score,"holdout":holdout_score}
        engine.parameters=replace(engine.parameters,family_bias=tuple(sorted(bias.items())))
        state={"sample":len(rows),"risk":engine.parameters.base_risk_fraction,"exploration":engine.parameters.exploration_rate,"family_bias":dict(engine.parameters.family_bias)}
        self.state_path.parent.mkdir(parents=True,exist_ok=True); tmp=self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(state,sort_keys=True),encoding="utf-8"); tmp.replace(self.state_path)
        receipt_path=self.state_path.with_name("evolution-receipts.jsonl")
        with receipt_path.open("a",encoding="utf-8") as h:h.write(json.dumps({**state,"decisions":decisions},sort_keys=True)+"\n")
        return state
