"""Private BLACKTIDE decision engine. No network, clock, or opponent inputs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from .amcte import MarketState, build_vector, opportunity

BOT_ID = "BLACKTIDE_SPY"
STARTING_BANKROLL = 1000.0
MAX_OPEN_TRADES = 1
CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class Parameters:
    min_bars: int = 45
    opportunity_threshold: float = 0.43
    max_spread_pct: float = 0.18
    min_volume: int = 5
    min_open_interest: int = 25
    min_delta: float = 0.30
    max_delta: float = 0.68
    risk_fraction: float = 0.24
    take_profit_pct: float = 0.32
    stop_loss_pct: float = 0.22
    max_hold_minutes: int = 35


@dataclass(frozen=True)
class Position:
    trade_id: str
    contract_symbol: str
    side: Literal["call", "put"]
    contracts: int
    entry_price: float
    opened_at: datetime
    entry_state: str = "UNKNOWN"


@dataclass(frozen=True)
class Decision:
    action: Literal["NO_ACTION", "ENTER", "EXIT", "BUST"]
    reason: str
    contract_symbol: str | None = None
    side: str | None = None
    contracts: int = 0
    price: float | None = None
    family: str | None = None
    market_state: str | None = None


class BLACKTIDE:
    def __init__(self, parameters: Parameters | None = None):
        self.parameters = parameters or Parameters()
        self.position: Position | None = None
        self.generation = 1

    def decide(self, *, as_of: datetime, bankroll: float, market: dict[str, Any],
               options: dict[str, Any], bars: list[dict[str, Any]]) -> Decision:
        if self.position is not None:
            return self._exit_decision(as_of, options, bars)
        if bankroll <= 0:
            return Decision("BUST", "generation bankroll exhausted")
        if market.get("tier") != "A" or options.get("tier") != "A":
            return Decision("NO_ACTION", "Tier A point-in-time evidence required")
        if len(bars) < self.parameters.min_bars:
            return Decision("NO_ACTION", "insufficient causal bars")
        raw_contracts = options.get("contracts", [])
        clean_count = sum(self._critical_quality(c) for c in raw_contracts)
        vector = build_vector(bars, options_quality=clean_count / max(len(raw_contracts), 1))
        if vector is None:
            return Decision("NO_ACTION", "insufficient multi-timeframe evidence")
        setup = opportunity(vector, threshold=self.parameters.opportunity_threshold)
        if setup is None:
            return Decision("NO_ACTION", f"no approved transition in {vector.state.value}")
        side = setup.side
        candidates = [c for c in raw_contracts if self._eligible(c, side, as_of)]
        if not candidates:
            return Decision("NO_ACTION", "no liquid same-day contract qualifies")
        affordable = [c for c in candidates if float(c["ask"]) * CONTRACT_MULTIPLIER <= bankroll]
        if not affordable:
            return Decision("BUST", "entire bankroll cannot afford any qualifying contract")
        contract = min(affordable, key=lambda c: (abs(abs(float(c["delta"])) - 0.50), float(c["ask"])))
        ask = float(contract["ask"])
        contracts = int((bankroll * self.parameters.risk_fraction) // (ask * CONTRACT_MULTIPLIER))
        if contracts < 1:
            return Decision("NO_ACTION", "preferred risk allocation cannot fund one contract")
        return Decision("ENTER", "private directional/liquidity criteria met",
                        str(contract["option_symbol"]), side, contracts, ask,
                        setup.family, vector.state.value)

    @staticmethod
    def _critical_quality(contract: dict[str, Any]) -> bool:
        required = ("bid", "ask", "delta", "gamma", "theta", "iv", "volume", "open_interest")
        return contract.get("data_class") == "VERIFIED_REAL" and all(contract.get(key) is not None for key in required)

    def _eligible(self, contract: dict[str, Any], side: str, as_of: datetime) -> bool:
        try:
            bid, ask = float(contract["bid"]), float(contract["ask"])
            delta = abs(float(contract["delta"]))
            spread = (ask - bid) / ask
            return (self._critical_quality(contract)
                    and contract.get("side") == side and contract.get("expiration") == as_of.date().isoformat()
                    and bid > 0 and ask >= bid and spread <= self.parameters.max_spread_pct
                    and int(contract.get("volume") or 0) >= self.parameters.min_volume
                    and int(contract.get("open_interest") or 0) >= self.parameters.min_open_interest
                    and self.parameters.min_delta <= delta <= self.parameters.max_delta)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return False

    def _exit_decision(self, as_of: datetime, options: dict[str, Any], bars: list[dict[str, Any]]) -> Decision:
        assert self.position is not None
        rows = {str(c.get("option_symbol")): c for c in options.get("contracts", [])}
        contract = rows.get(self.position.contract_symbol)
        if options.get("tier") != "A" or not contract:
            return Decision("NO_ACTION", "current observed contract bid unavailable")
        try:
            bid = float(contract["bid"])
        except (TypeError, ValueError):
            return Decision("NO_ACTION", "invalid observed exit bid")
        change = bid / self.position.entry_price - 1
        held = (as_of - self.position.opened_at).total_seconds() / 60
        vector = build_vector(bars, options_quality=1.0)
        invalidated = vector is not None and (
            (self.position.side == "call" and vector.control_delta < -.18)
            or (self.position.side == "put" and vector.control_delta > .18)
            or vector.state in (MarketState.DISORDER, MarketState.FAILED_EXPANSION)
        )
        if invalidated:
            return Decision("EXIT", "market-control invalidation", self.position.contract_symbol,
                            self.position.side, self.position.contracts, bid)
        if change >= self.parameters.take_profit_pct:
            return Decision("EXIT", "take-profit reached", self.position.contract_symbol,
                            self.position.side, self.position.contracts, bid)
        if change <= -self.parameters.stop_loss_pct:
            return Decision("EXIT", "risk stop reached", self.position.contract_symbol,
                            self.position.side, self.position.contracts, bid)
        if held >= self.parameters.max_hold_minutes:
            return Decision("EXIT", "maximum holding time reached", self.position.contract_symbol,
                            self.position.side, self.position.contracts, bid)
        return Decision("NO_ACTION", "position remains within exit envelope")

    def apply_entry(self, decision: Decision, *, trade_id: str, opened_at: datetime) -> None:
        if decision.action != "ENTER" or self.position is not None or decision.price is None:
            raise ValueError("invalid or overlapping entry")
        self.position = Position(trade_id, str(decision.contract_symbol), decision.side,  # type: ignore[arg-type]
                                 decision.contracts, decision.price, opened_at,
                                 decision.market_state or "UNKNOWN")

    def apply_exit(self, decision: Decision) -> Position:
        if decision.action != "EXIT" or self.position is None:
            raise ValueError("no valid position to close")
        closed = self.position
        self.position = None
        return closed

    def evolve(self, generation_returns: list[float]) -> Parameters:
        """Deterministic, bounded learning from BLACKTIDE's own completed trades."""
        if len(generation_returns) < 8:
            return self.parameters
        win_rate = sum(value > 0 for value in generation_returns) / len(generation_returns)
        adjustment = 0.01 if win_rate < 0.45 else (-0.01 if win_rate > 0.60 else 0.0)
        self.parameters = replace(
            self.parameters,
            opportunity_threshold=min(.62, max(.38, self.parameters.opportunity_threshold + adjustment)),
        )
        return self.parameters

    def reset_generation_after_bust(self) -> None:
        if self.position is not None:
            raise ValueError("cannot bust-reset with an open trade")
        self.generation += 1
