"""Narrow integration between BLACKTIDE and neutral shared infrastructure."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

import backtest_lab
import scoreboard

from .engine import BLACKTIDE, CONTRACT_MULTIPLIER, Decision

SCOREBOARD_BOT = "BLACKTIDE"


class BlacktideRuntime:
    def __init__(self, *, engine: BLACKTIDE | None = None, market_view=None):
        self.engine = engine or BLACKTIDE()
        self.market_view = market_view or backtest_lab.MarketView("SPY")

    def evaluate(self, as_of: datetime, connection: sqlite3.Connection) -> Decision:
        bankroll = scoreboard.current_bankroll(connection, SCOREBOARD_BOT)
        decision = self.engine.decide(
            as_of=as_of,
            bankroll=bankroll,
            market=self.market_view.market_as_of(as_of),
            options=self.market_view.options_as_of(as_of),
            bars=self.market_view.bars_as_of(as_of, lookback_minutes=120),
        )
        if decision.action == "ENTER":
            trade_id = f"blacktide-{uuid.uuid4()}"
            scoreboard.record_trade_open(
                connection, trade_id=trade_id, bot=SCOREBOARD_BOT,
                generation=self.engine.generation, opened_at=as_of.isoformat(),
                side=str(decision.side), contract_symbol=str(decision.contract_symbol),
                entry_price=float(decision.price), contracts=decision.contracts,
                entry_bankroll=bankroll,
            )
            self.engine.apply_entry(decision, trade_id=trade_id, opened_at=as_of)
        elif decision.action == "EXIT":
            position = self.engine.position
            if position is None or decision.price is None:
                raise RuntimeError("engine emitted EXIT without an open position")
            pnl = (decision.price - position.entry_price) * position.contracts * CONTRACT_MULTIPLIER
            scoreboard.record_trade_close(
                connection, trade_id=position.trade_id, closed_at=as_of.isoformat(),
                exit_price=decision.price, pnl_usd=pnl,
            )
            self.engine.apply_exit(decision)
        elif decision.action == "BUST":
            if self.engine.position is not None:
                raise RuntimeError("cannot bust with an open position")
            scoreboard.record_generation_event(
                connection, bot=SCOREBOARD_BOT, generation=self.engine.generation,
                event="BUSTED", detail=decision.reason,
            )
            self.engine.reset_generation_after_bust()
            scoreboard.record_generation_event(
                connection, bot=SCOREBOARD_BOT, generation=self.engine.generation,
                event="STARTED", detail="bankroll reset to $1,000",
            )
        return decision
