"""RIPTIDE integration with neutral point-in-time data and scorekeeping."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

import backtest_lab
import scoreboard

from .engine import CONTRACT_MULTIPLIER, Decision, Position, Riptide
from .evolution import EvolutionLoop, Outcome


SCOREBOARD_BOT = "RIPTIDE"


class RiptideRuntime:
    def __init__(self, *, engine: Riptide | None = None, market_view=None, evolution: EvolutionLoop | None = None):
        self.engine = engine or Riptide()
        self.market_view = market_view or backtest_lab.MarketView("SPY")
        self.evolution = evolution or EvolutionLoop()

    def recover(self, connection: sqlite3.Connection) -> None:
        self.engine.generation = scoreboard.current_generation(connection, SCOREBOARD_BOT)
        row = scoreboard.current_position_status(connection, SCOREBOARD_BOT)
        if row is None:
            self.engine.position = None
            return
        side = str(row["side"]).lower()
        if side not in ("call", "put"):
            raise RuntimeError(f"invalid RIPTIDE side: {side!r}")
        self.engine.position = Position(str(row["trade_id"]), str(row["contract_symbol"]), side, int(row["contracts"]), float(row["entry_price"]), datetime.fromisoformat(str(row["opened_at"])))

    def evaluate(self, as_of: datetime, connection: sqlite3.Connection) -> Decision:
        self.recover(connection)
        bankroll = scoreboard.current_bankroll(connection, SCOREBOARD_BOT)
        decision = self.engine.decide(
            as_of=as_of,
            bankroll=bankroll,
            market=self.market_view.market_as_of(as_of),
            options=self.market_view.options_as_of(as_of),
            bars=self.market_view.bars_as_of(as_of, lookback_minutes=90),
        )
        if decision.action == "ENTER":
            trade_id = f"riptide-{uuid.uuid4()}"
            scoreboard.record_trade_open(connection, trade_id=trade_id, bot=SCOREBOARD_BOT,
                                         generation=self.engine.generation, opened_at=as_of.isoformat(),
                                         side=str(decision.side), contract_symbol=str(decision.contract_symbol),
                                         entry_price=float(decision.price), contracts=decision.contracts,
                                         entry_bankroll=bankroll)
            self.engine.apply_entry(decision, trade_id=trade_id, opened_at=as_of)
        elif decision.action == "EXIT":
            position = self.engine.position
            if position is None or decision.price is None:
                raise RuntimeError("RIPTIDE emitted invalid exit")
            pnl = (decision.price - position.entry_price) * position.contracts * CONTRACT_MULTIPLIER
            scoreboard.record_trade_close(connection, trade_id=position.trade_id, closed_at=as_of.isoformat(), exit_price=decision.price, pnl_usd=pnl)
            self.evolution.record(Outcome(position.trade_id, self.engine.generation, (decision.price / position.entry_price) - 1, decision.reason, as_of.isoformat()))
            self.evolution.evaluate(self.engine)
            self.engine.apply_exit(decision)
        elif decision.action == "BUST":
            if self.engine.position is not None:
                raise RuntimeError("cannot bust with an open position")
            scoreboard.record_generation_event(connection, bot=SCOREBOARD_BOT, generation=self.engine.generation, event="BUSTED", detail=decision.reason, minimum_qualifying_cost=bankroll + .02)
            self.engine.reset_generation_after_bust()
            scoreboard.record_generation_event(connection, bot=SCOREBOARD_BOT, generation=self.engine.generation, event="STARTED", detail="bankroll reset to $1,000")
        return decision
