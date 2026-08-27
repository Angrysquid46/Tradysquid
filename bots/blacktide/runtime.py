"""Narrow integration between BLACKTIDE and neutral shared infrastructure."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import backtest_lab
import scoreboard

from .engine import BLACKTIDE, CONTRACT_MULTIPLIER, Decision, Position
from .evolution import EvolutionLoop, Outcome

SCOREBOARD_BOT = "BLACKTIDE"
STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "blacktide"
DECISION_LOG_PATH = STATE_DIR / "decision-audit.jsonl"
DECISION_STATE_PATH = STATE_DIR / "decision-audit-state.json"


class BlacktideRuntime:
    def __init__(self, *, engine: BLACKTIDE | None = None, market_view=None, evolution=None):
        self.engine = engine or BLACKTIDE()
        self.market_view = market_view or backtest_lab.MarketView("SPY")
        self.evolution = evolution or EvolutionLoop()

    @staticmethod
    def _record_decision(decision: Decision, as_of: datetime) -> None:
        """Persist changed decisions, without making audit I/O a trade gate.

        A scanner declining a setup is valid, but it must be explainable.
        Repeated identical NO_ACTION cycles are coalesced to one record every
        five minutes; entries/exits/busts are always recorded.
        """
        payload = {
            "observed_at": as_of.isoformat(),
            "action": decision.action,
            "reason": decision.reason,
            "side": decision.side,
            "contract_symbol": decision.contract_symbol,
            "price": decision.price,
            "contracts": decision.contracts,
            "family": decision.family,
            "market_state": decision.market_state,
        }
        signature = json.dumps({key: payload[key] for key in payload if key != "observed_at"}, sort_keys=True)
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            previous: dict[str, str] = {}
            if DECISION_STATE_PATH.exists():
                previous = json.loads(DECISION_STATE_PATH.read_text(encoding="utf-8"))
            previous_at = datetime.fromisoformat(str(previous.get("observed_at") or "")) if previous.get("observed_at") else None
            unchanged = previous.get("signature") == signature
            recent = bool(previous_at and (as_of - previous_at).total_seconds() < 300)
            if decision.action == "NO_ACTION" and unchanged and recent:
                return
            with DECISION_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
            temporary = DECISION_STATE_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps({"signature": signature, "observed_at": as_of.isoformat()}), encoding="utf-8")
            temporary.replace(DECISION_STATE_PATH)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            # Audit visibility must not block an otherwise valid paper exit.
            return

    def recover(self, connection: sqlite3.Connection) -> None:
        """Reconstruct private process memory from the authoritative referee."""
        self.engine.generation = scoreboard.current_generation(connection, SCOREBOARD_BOT)
        row = scoreboard.current_position_status(connection, SCOREBOARD_BOT)
        if row is None:
            self.engine.position = None
            return
        side = str(row["side"]).lower()
        if side not in ("call", "put"):
            raise RuntimeError(f"invalid official BLACKTIDE side: {side!r}")
        self.engine.position = Position(
            trade_id=str(row["trade_id"]), contract_symbol=str(row["contract_symbol"]),
            side=side, contracts=int(row["contracts"]), entry_price=float(row["entry_price"]),
            opened_at=datetime.fromisoformat(str(row["opened_at"])),
        )

    def evaluate(self, as_of: datetime, connection: sqlite3.Connection) -> Decision:
        self.recover(connection)
        bankroll = scoreboard.current_bankroll(connection, SCOREBOARD_BOT)
        decision = self.engine.decide(
            as_of=as_of,
            bankroll=bankroll,
            market=self.market_view.market_as_of(as_of),
            options=self.market_view.options_as_of(as_of),
            bars=self.market_view.bars_as_of(as_of, lookback_minutes=120),
        )
        self._record_decision(decision, as_of)
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
            self.evolution.record(Outcome(
                position.trade_id, self.engine.generation, pnl,
                (decision.price / position.entry_price) - 1,
                position.entry_family, position.entry_state, as_of.isoformat(),
                exit_reason=decision.reason,
                held_minutes=round((as_of - position.opened_at).total_seconds() / 60, 2),
            ))
            self.evolution.evaluate(self.engine)
            self.engine.apply_exit(decision)
        elif decision.action == "BUST":
            if self.engine.position is not None:
                raise RuntimeError("cannot bust with an open position")
            scoreboard.record_generation_event(
                connection, bot=SCOREBOARD_BOT, generation=self.engine.generation,
                event="BUSTED", detail=decision.reason,
                minimum_qualifying_cost=bankroll + 0.02,
            )
            self.engine.reset_generation_after_bust()
            scoreboard.record_generation_event(
                connection, bot=SCOREBOARD_BOT, generation=self.engine.generation,
                event="STARTED", detail="bankroll reset to $1,000",
            )
        return decision
