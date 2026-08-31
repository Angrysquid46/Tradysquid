"""GROK private state — generation, learning telemetry, strategy version, recovery.

Official bankroll and open position live in the neutral scoreboard.
This module holds only GROK-private intelligence and recovery aids.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = STATE_DIR / "grok_private_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class GenerationSummary:
    generation: int
    started_at: str
    ended_at: str | None = None
    starting_bankroll: float = 1000.0
    ending_bankroll: float | None = None
    net_pnl: float | None = None
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    busted: bool = False
    postmortem: str = ""
    setup_family_performance: dict[str, Any] = field(default_factory=dict)
    exit_reason_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class StrategyVersion:
    version_id: str
    created_at: str
    description: str
    parameters: dict[str, Any]
    parent_version: str | None = None
    promoted: bool = False
    validation_notes: str = ""


@dataclass
class GrokPrivateState:
    current_generation: int = 1
    strategy_version: str = "v0.1.0-bootstrap"
    last_decision_at: str | None = None
    generations: list[dict[str, Any]] = field(default_factory=list)
    strategy_versions: list[dict[str, Any]] = field(default_factory=list)
    decision_log_tail: list[dict[str, Any]] = field(default_factory=list)
    learning_metrics: dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrokPrivateState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def load_state() -> GrokPrivateState:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = GrokPrivateState()
        save_state(state)
        return state
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return GrokPrivateState.from_dict(data)


def save_state(state: GrokPrivateState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state.last_updated = _now_iso()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, sort_keys=True)
