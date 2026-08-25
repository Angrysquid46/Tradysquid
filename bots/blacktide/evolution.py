"""Private deterministic BLACKTIDE evolution with anti-overfit gates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean

from .engine import BLACKTIDE, Parameters

MIN_SAMPLE = 30
HOLDOUT_FRACTION = .25
MIN_HOLDOUT = 8
MIN_IMPROVEMENT = .03
STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "blacktide"


@dataclass(frozen=True)
class Outcome:
    trade_id: str
    generation: int
    pnl_usd: float
    return_pct: float
    family: str
    market_state: str
    closed_at: str


class EvolutionLoop:
    stages = ("OBSERVE", "RECORD", "MEASURE", "DIAGNOSE", "HYPOTHESIZE",
              "TEST", "CHALLENGE", "VALIDATE", "PROMOTE_OR_REJECT")

    def __init__(self, path: Path | None = None):
        self.path = path or STATE_DIR / "outcomes.jsonl"

    def record(self, outcome: Outcome) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {o.trade_id for o in self.load()}
        if outcome.trade_id in existing:
            raise ValueError("completed outcome is immutable and already recorded")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(outcome), sort_keys=True) + "\n")

    def load(self) -> list[Outcome]:
        if not self.path.exists():
            return []
        return [Outcome(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    @staticmethod
    def _fitness(rows: list[Outcome], threshold_shift: float) -> float:
        # Conservative deterministic challenge: tighter hypotheses exclude the
        # weakest tail; transaction outcomes are never relabeled or rewritten.
        if not rows:
            return float("-inf")
        retained = rows[max(0, int(len(rows) * max(threshold_shift, 0) * 2)):]
        if len(retained) < MIN_HOLDOUT:
            return float("-inf")
        mean = fmean(o.return_pct for o in retained)
        downside = fmean(abs(min(o.return_pct, 0)) for o in retained)
        return mean - downside * .5

    def evaluate(self, engine: BLACKTIDE) -> dict[str, object]:
        rows = self.load()
        receipt: dict[str, object] = {"stages": self.stages, "sample": len(rows), "decision": "REJECT"}
        if len(rows) < MIN_SAMPLE:
            receipt["reason"] = "minimum sample not met"
            return receipt
        split = max(MIN_SAMPLE - MIN_HOLDOUT, int(len(rows) * (1 - HOLDOUT_FRACTION)))
        train, holdout = rows[:split], rows[split:]
        if len(holdout) < MIN_HOLDOUT:
            receipt["reason"] = "chronological holdout too small"
            return receipt
        baseline = self._fitness(holdout, 0)
        candidates = (-.01, .01)
        scored = [(shift, self._fitness(train, shift), self._fitness(holdout, shift)) for shift in candidates]
        stable = [row for row in scored if row[1] > baseline and row[2] >= baseline + MIN_IMPROVEMENT]
        if not stable:
            receipt.update(reason="no stable holdout improvement", baseline=baseline)
            return receipt
        shift, _, score = max(stable, key=lambda row: row[2])
        old = engine.parameters
        engine.parameters = Parameters(**{**asdict(old), "opportunity_threshold": min(.62, max(.38, old.opportunity_threshold + shift))})
        receipt.update(decision="PROMOTE", shift=shift, baseline=baseline, holdout_score=score,
                       train_count=len(train), holdout_count=len(holdout))
        return receipt
