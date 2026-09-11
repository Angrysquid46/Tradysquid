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
POSITION_STATE_PATH = STATE_DIR / "position-state.json"


class BlacktideRuntime:
    def __init__(self, *, engine: BLACKTIDE | None = None, market_view=None, evolution=None,
                 position_state_path: Path | None = None):
        self.engine = engine or BLACKTIDE()
        self.market_view = market_view or backtest_lab.MarketView("SPY")
        self.evolution = evolution or EvolutionLoop()
        if hasattr(self.evolution, "apply"):
            self.evolution.apply(self.engine)
        self.position_state_path = position_state_path or POSITION_STATE_PATH

    def _save_position_state(self) -> None:
        position = self.engine.position
        if position is None:
            self.position_state_path.unlink(missing_ok=True)
            return
        payload = {
            "trade_id": position.trade_id,
            "entry_state": position.entry_state,
            "entry_family": position.entry_family,
        }
        self.position_state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.position_state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.position_state_path)

    def _load_position_context(self, trade_id: str) -> tuple[str, str]:
        try:
            payload = json.loads(self.position_state_path.read_text(encoding="utf-8"))
            if payload.get("trade_id") == trade_id:
                return str(payload.get("entry_state") or "UNKNOWN"), str(payload.get("entry_family") or "UNKNOWN")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return "UNKNOWN", "UNKNOWN"

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
            if previous_at and (previous_at.tzinfo is None) != (as_of.tzinfo is None):
                previous_at = previous_at.replace(tzinfo=as_of.tzinfo)
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
            self.position_state_path.unlink(missing_ok=True)
            return
        trade_id = str(row["trade_id"])
        if self.engine.position is not None and self.engine.position.trade_id == trade_id:
            return
        side = str(row["side"]).lower()
        if side not in ("call", "put"):
            raise RuntimeError(f"invalid official BLACKTIDE side: {side!r}")
        entry_state, entry_family = self._load_position_context(trade_id)
        self.engine.position = Position(
            trade_id=trade_id, contract_symbol=str(row["contract_symbol"]),
            side=side, contracts=int(row["contracts"]), entry_price=float(row["entry_price"]),
            opened_at=datetime.fromisoformat(str(row["opened_at"])),
            entry_state=entry_state, entry_family=entry_family,
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
            self._save_position_state()
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
            self._save_position_state()
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
