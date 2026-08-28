"""RIPTIDE private volatility-compression breakout paper strategy.

The engine accepts only causal bars and the contemporaneous option chain. It
has no network, clock, opponent, Discord, or brokerage dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal


BOT_ID = "RIPTIDE_SPY"
STARTING_BANKROLL = 1000.0
CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class Parameters:
    min_bars: int = 35
    compression_window: int = 12
    breakout_volume_ratio: float = 1.18
    max_spread_pct: float = 0.14
    min_volume: int = 20
    min_open_interest: int = 100
    min_delta: float = 0.35
    max_delta: float = 0.60
    risk_fraction: float = 0.32
    take_profit_pct: float = 0.45
    stop_loss_pct: float = 0.16
    max_hold_minutes: int = 18


@dataclass(frozen=True)
class Position:
    trade_id: str
    contract_symbol: str
    side: Literal["call", "put"]
    contracts: int
    entry_price: float
    opened_at: datetime
    setup: str = "VOLATILITY_BREAKOUT"


@dataclass(frozen=True)
class Decision:
    action: Literal["NO_ACTION", "ENTER", "EXIT", "BUST"]
    reason: str
    contract_symbol: str | None = None
    side: str | None = None
    contracts: int = 0
    price: float | None = None
    setup: str | None = None


class Riptide:
    """Fast, directional breakout trader using only completed one-minute bars."""

    def __init__(self, parameters: Parameters | None = None):
        self.parameters = parameters or Parameters()
        self.position: Position | None = None
        self.generation = 1

    def decide(self, *, as_of: datetime, bankroll: float, market: dict[str, Any], options: dict[str, Any], bars: list[dict[str, Any]]) -> Decision:
        if self.position is not None:
            return self._exit(as_of, options, bars)
        if bankroll <= 0:
            return Decision("BUST", "generation bankroll exhausted")
        if market.get("tier") != "A" or options.get("tier") != "A":
            return Decision("NO_ACTION", "Tier A point-in-time evidence required")
        if len(bars) < self.parameters.min_bars:
            return Decision("NO_ACTION", "insufficient completed bars")
        side = self._breakout_side(bars)
        if side is None:
            return Decision("NO_ACTION", "no completed compression breakout")
        candidates = [row for row in options.get("contracts", []) if self._eligible(row, side, as_of)]
        if not candidates:
            return Decision("NO_ACTION", "no liquid same-day contract qualifies")
        affordable = [row for row in candidates if float(row["ask"]) * CONTRACT_MULTIPLIER <= bankroll]
        if not affordable:
            return Decision("BUST", "entire bankroll cannot afford a qualifying contract")
        contract = min(affordable, key=lambda row: (abs(abs(float(row["delta"])) - .45), float(row["ask"])))
        ask = float(contract["ask"])
        contracts = int((bankroll * self.parameters.risk_fraction) // (ask * CONTRACT_MULTIPLIER))
        if contracts < 1:
            return Decision("NO_ACTION", "preferred risk allocation cannot fund one contract")
        return Decision("ENTER", "causal volatility breakout and volume confirmation", str(contract["option_symbol"]), side, contracts, ask, "VOLATILITY_BREAKOUT")

    def _breakout_side(self, bars: list[dict[str, Any]]) -> Literal["call", "put"] | None:
        window = self.parameters.compression_window
        prior, trigger = bars[-(window + 3):-3], bars[-3:]
        try:
            high = max(float(row["high"]) for row in prior)
            low = min(float(row["low"]) for row in prior)
            average_volume = sum(float(row.get("volume") or 0) for row in prior) / len(prior)
            closes = [float(row["close"]) for row in trigger]
            last_volume = float(trigger[-1].get("volume") or 0)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        volume_ok = last_volume >= average_volume * self.parameters.breakout_volume_ratio
        if volume_ok and closes[0] < closes[1] < closes[2] and closes[-1] > high:
            return "call"
        if volume_ok and closes[0] > closes[1] > closes[2] and closes[-1] < low:
            return "put"
        return None

    @staticmethod
    def _quality(contract: dict[str, Any]) -> bool:
        fields = ("bid", "ask", "delta", "gamma", "theta", "iv", "volume", "open_interest")
        return contract.get("data_class") == "VERIFIED_REAL" and all(contract.get(key) is not None for key in fields)

    def _eligible(self, contract: dict[str, Any], side: str, as_of: datetime) -> bool:
        try:
            bid, ask = float(contract["bid"]), float(contract["ask"])
            delta = abs(float(contract["delta"]))
            return (self._quality(contract) and contract.get("side") == side and contract.get("expiration") == as_of.date().isoformat() and bid > 0 and ask >= bid and (ask - bid) / ask <= self.parameters.max_spread_pct and int(contract.get("volume") or 0) >= self.parameters.min_volume and int(contract.get("open_interest") or 0) >= self.parameters.min_open_interest and self.parameters.min_delta <= delta <= self.parameters.max_delta)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return False

    def _exit(self, as_of: datetime, options: dict[str, Any], bars: list[dict[str, Any]]) -> Decision:
        assert self.position is not None
        contract = next((row for row in options.get("contracts", []) if str(row.get("option_symbol")) == self.position.contract_symbol), None)
        if options.get("tier") != "A" or not contract:
            return Decision("NO_ACTION", "current observed contract bid unavailable")
        try:
            bid = float(contract["bid"])
        except (KeyError, TypeError, ValueError):
            return Decision("NO_ACTION", "invalid observed exit bid")
        change = bid / self.position.entry_price - 1
        held = (as_of - self.position.opened_at).total_seconds() / 60
        reversal = self._breakout_side(bars)
        if reversal and reversal != self.position.side:
            return Decision("EXIT", "opposite breakout invalidation", self.position.contract_symbol, self.position.side, self.position.contracts, bid)
        if change >= self.parameters.take_profit_pct:
            return Decision("EXIT", "take-profit reached", self.position.contract_symbol, self.position.side, self.position.contracts, bid)
        if change <= -self.parameters.stop_loss_pct:
            return Decision("EXIT", "risk stop reached", self.position.contract_symbol, self.position.side, self.position.contracts, bid)
        if held >= self.parameters.max_hold_minutes:
            return Decision("EXIT", "maximum holding time reached", self.position.contract_symbol, self.position.side, self.position.contracts, bid)
        return Decision("NO_ACTION", "position remains within exit envelope")

    def apply_entry(self, decision: Decision, *, trade_id: str, opened_at: datetime) -> None:
        if decision.action != "ENTER" or self.position is not None or decision.price is None:
            raise ValueError("invalid or overlapping entry")
        self.position = Position(trade_id, str(decision.contract_symbol), decision.side, decision.contracts, decision.price, opened_at)  # type: ignore[arg-type]

    def apply_exit(self, decision: Decision) -> Position:
        if decision.action != "EXIT" or self.position is None:
            raise ValueError("no valid position to close")
        closed, self.position = self.position, None
        return closed

    def evolve(self, outcomes: list[float]) -> Parameters:
        """Bounded adaptation from RIPTIDE's own immutable completed returns."""
        if len(outcomes) < 12:
            return self.parameters
        win_rate = sum(value > 0 for value in outcomes[-24:]) / min(len(outcomes), 24)
        shift = .02 if win_rate < .42 else (-.01 if win_rate > .60 else 0.0)
        self.parameters = replace(self.parameters, breakout_volume_ratio=min(1.45, max(1.05, self.parameters.breakout_volume_ratio + shift)))
        return self.parameters

    def reset_generation_after_bust(self) -> None:
        if self.position is not None:
            raise ValueError("cannot bust-reset with an open position")
        self.generation += 1
