"""RIPTIDE integration with neutral point-in-time data and scorekeeping."""

from __future__ import annotations

import sqlite3
import uuid
import json
from dataclasses import asdict
from pathlib import Path
from datetime import datetime

import backtest_lab
import market_api_budget
import market_data
import scoreboard

from .engine import CONTRACT_MULTIPLIER, Decision, Position, Riptide
from .evolution import EvolutionLoop, Outcome


SCOREBOARD_BOT = "RIPTIDE"
TELEMETRY_PATH = Path(__file__).resolve().parents[2] / "state" / "riptide" / "decision-telemetry.jsonl"


class RiptideRuntime:
    def __init__(self, *, engine: Riptide | None = None, market_view=None, evolution: EvolutionLoop | None = None,
                 telemetry_path: Path | None = None, quote_loader=None, daily_history_loader=None):
        self.engine = engine or Riptide()
        self.market_view = market_view or backtest_lab.MarketView("SPY")
        self.evolution = evolution or EvolutionLoop()
        if hasattr(self.evolution, "apply"):
            self.evolution.apply(self.engine)
        self.telemetry_path = telemetry_path or TELEMETRY_PATH
        self.quote_loader = quote_loader or market_data.get_quote
        self.daily_history_loader = daily_history_loader or market_data.get_daily_history

    @staticmethod
    def _contract_terms(symbol: str) -> tuple[str, float]:
        if len(symbol) < 15 or symbol[-9] not in "CP":
            raise ValueError(f"invalid OCC option symbol: {symbol!r}")
        return ("call" if symbol[-9] == "C" else "put", int(symbol[-8:]) / 1000)

    def _expired_settlement(self, as_of: datetime) -> Decision | None:
        position = self.engine.position
        if position is None:
            return None
        expiry = datetime.strptime(position.contract_symbol[-15:-9], "%y%m%d").date()
        if as_of.date() <= expiry:
            return None
        side, strike = self._contract_terms(position.contract_symbol)
        rows = self.daily_history_loader("SPY", days=max(10, (as_of.date() - expiry).days + 5))
        row = next((item for item in rows if str(item.get("date")) == expiry.isoformat()), None)
        if row is None or row.get("close") is None:
            return Decision("NO_ACTION", "expired contract awaits verified underlying close")
        underlying_close = float(row["close"])
        settlement = max(underlying_close - strike, 0.0) if side == "call" else max(strike - underlying_close, 0.0)
        return Decision("EXIT", f"expiration settlement from verified SPY close {underlying_close:.2f}",
                        position.contract_symbol, position.side, position.contracts, settlement, position.setup)

    def _add_direct_position_quote(self, options: dict) -> dict:
        position = self.engine.position
        if position is None:
            return options
        contracts = list(options.get("contracts") or [])
        if any(str(row.get("option_symbol")) == position.contract_symbol for row in contracts):
            return options
        quote = self.quote_loader(position.contract_symbol, priority=market_api_budget.PRIORITY_EXIT_CRITICAL_DATA)
        if quote is None or quote.get("bid") is None:
            return options
        contracts.append({**quote, "option_symbol": position.contract_symbol, "data_class": "VERIFIED_REAL"})
        return {**options, "tier": "A", "contracts": contracts}

    def recover(self, connection: sqlite3.Connection) -> None:
        self.engine.generation = scoreboard.current_generation(connection, SCOREBOARD_BOT)
        row = scoreboard.current_position_status(connection, SCOREBOARD_BOT)
        if row is None:
            self.engine.position = None
            return
        if self.engine.position is not None and self.engine.position.trade_id == str(row["trade_id"]):
            return
        side = str(row["side"]).lower()
        if side not in ("call", "put"):
            raise RuntimeError(f"invalid RIPTIDE side: {side!r}")
        self.engine.position = Position(str(row["trade_id"]), str(row["contract_symbol"]), side, int(row["contracts"]), float(row["entry_price"]), datetime.fromisoformat(str(row["opened_at"])))

    def evaluate(self, as_of: datetime, connection: sqlite3.Connection) -> Decision:
        self.recover(connection)
        bankroll = scoreboard.current_bankroll(connection, SCOREBOARD_BOT)
        decision = self._expired_settlement(as_of)
        if decision is None:
            market = self.market_view.market_as_of(as_of)
            options = self._add_direct_position_quote(self.market_view.options_as_of(as_of))
            bars = self.market_view.bars_as_of(as_of, lookback_minutes=90)
            decision = self.engine.decide(
                as_of=as_of,
                bankroll=bankroll,
                market=market,
                options=options,
                bars=bars,
            )
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(decision)
        payload.update({"observed_at": as_of.isoformat(), "bankroll": bankroll})
        with self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        if decision.action == "ENTER":
            trade_id = f"riptide-{uuid.uuid4()}"
            scoreboard.record_trade_open(connection, trade_id=trade_id, bot=SCOREBOARD_BOT,
                                         generation=self.engine.generation, opened_at=as_of.isoformat(),
                                         side=str(decision.side), contract_symbol=str(decision.contract_symbol),
                                         entry_price=float(decision.price), contracts=decision.contracts,
                                         entry_bankroll=bankroll)
            selected = next((row for row in options.get("contracts", []) if str(row.get("option_symbol")) == decision.contract_symbol), {})
            self.engine.apply_entry(decision, trade_id=trade_id, opened_at=as_of,
                                    entry_iv=float(selected["iv"]) if selected.get("iv") is not None else None)
        elif decision.action == "EXIT":
            position = self.engine.position
            if position is None or decision.price is None:
                raise RuntimeError("RIPTIDE emitted invalid exit")
            pnl = (decision.price - position.entry_price) * position.contracts * CONTRACT_MULTIPLIER
            scoreboard.record_trade_close(connection, trade_id=position.trade_id, closed_at=as_of.isoformat(), exit_price=decision.price, pnl_usd=pnl)
            self.evolution.record(Outcome(position.trade_id, self.engine.generation, (decision.price / position.entry_price) - 1, decision.reason, as_of.isoformat(), position.setup))
            self.evolution.evaluate(self.engine)
            self.engine.apply_exit(decision)
        elif decision.action == "BUST":
            if self.engine.position is not None:
                raise RuntimeError("cannot bust with an open position")
            scoreboard.record_generation_event(connection, bot=SCOREBOARD_BOT, generation=self.engine.generation, event="BUSTED", detail=decision.reason, minimum_qualifying_cost=bankroll + .02)
            self.engine.reset_generation_after_bust()
            scoreboard.record_generation_event(connection, bot=SCOREBOARD_BOT, generation=self.engine.generation, event="STARTED", detail="bankroll reset to $1,000")
        return decision
