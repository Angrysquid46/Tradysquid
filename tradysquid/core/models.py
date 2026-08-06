from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from .enums import CandidateStatus, Direction, PositionState, Regime, Structure


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    observed_at: str

    @property
    def midpoint(self) -> float:
        return round((self.bid + self.ask) / 2, 4) if self.bid >= 0 and self.ask >= 0 else 0.0

@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    expiration: str
    strike: float
    option_type: str
    bid: float
    ask: float
    volume: int
    open_interest: int
    delta: float | None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_volatility: float | None = None
    multiplier: int = 100
    observed_at: str = field(default_factory=utc_now)

    @property
    def midpoint(self) -> float:
        return round((self.bid + self.ask) / 2, 4)

    @property
    def spread_pct(self) -> float:
        mid = self.midpoint
        return float('inf') if mid <= 0 else (self.ask - self.bid) / mid

@dataclass(frozen=True)
class CandidateLeg:
    contract: OptionContract
    side: str
    quantity: int = 1

@dataclass
class CandidateDecision:
    candidate_id: str
    scan_cycle_id: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    preset: str
    symbol: str
    direction: Direction
    structure: Structure
    regime: Regime
    observed_at: str
    underlying_price: float
    legs: list[CandidateLeg]
    setup_score: float
    ranking_score: float
    status: CandidateStatus
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    rules_passed: list[str] = field(default_factory=list)
    rules_failed: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    total_debit: float = 0.0
    total_credit: float = 0.0
    maximum_risk: float = 0.0
    configuration_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value['direction'] = str(self.direction)
        value['structure'] = str(self.structure)
        value['regime'] = str(self.regime)
        value['status'] = str(self.status)
        return value

@dataclass
class PaperLeg:
    contract_symbol: str
    side: str
    quantity: int
    option_type: str
    strike: float
    expiration: str
    multiplier: int
    entry_bid: float
    entry_ask: float
    entry_fill: float
    current_bid: float = 0.0
    current_ask: float = 0.0
    current_mark: float = 0.0
    exit_fill: float | None = None

@dataclass
class PaperPosition:
    position_id: str
    candidate_id: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    symbol: str
    direction: Direction
    structure: Structure
    state: PositionState
    opened_at: str
    legs: list[PaperLeg]
    entry_value: float
    maximum_risk: float
    target_pct: float
    stop_pct: float
    current_value: float
    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    configuration_snapshot: dict[str, Any] = field(default_factory=dict)
