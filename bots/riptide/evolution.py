"""RIPTIDE's own bounded, outcome-only adaptation ledger."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .engine import Riptide


STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "riptide"


@dataclass(frozen=True)
class Outcome:
    trade_id: str
    generation: int
    return_pct: float
    exit_reason: str
    closed_at: str


class EvolutionLoop:
    def __init__(self, path: Path | None = None):
        self.path = path or STATE_DIR / "outcomes.jsonl"

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
        engine.evolve([row.return_pct for row in rows])
        return {"sample": len(rows), "volume_ratio": engine.parameters.breakout_volume_ratio}
