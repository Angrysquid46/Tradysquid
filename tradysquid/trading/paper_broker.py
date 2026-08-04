from __future__ import annotations

import json
import uuid

from ..core.enums import CandidateStatus, PositionState, Structure
from ..core.models import CandidateDecision, PaperLeg, PaperPosition, utc_now
from .fills import long_entry, short_entry


ACTIVE_STATES = {
    str(PositionState.OPEN),
    str(PositionState.HOLD),
    str(PositionState.PROFIT_PROTECTED),
    str(PositionState.EXIT_PENDING),
}
CLOSED_STATES = {
    str(PositionState.CLOSED_WIN),
    str(PositionState.CLOSED_LOSS),
    str(PositionState.CLOSED_BREAKEVEN),
    str(PositionState.CLOSED_EXPIRED),
    str(PositionState.CLOSED_DATA_FAILURE),
}


class PaperBroker:
    def __init__(self, database):
        self.db = database

    def open(self, decision: CandidateDecision) -> PaperPosition:
        if decision.status not in {
            CandidateStatus.ELIGIBLE,
            CandidateStatus.SELECTED,
        }:
            raise ValueError(
                "Only eligible or selected candidates can become paper positions"
            )
        if not decision.legs:
            raise ValueError("Candidate has no option legs")

        position_id = str(uuid.uuid4())
        cycle_id = str(uuid.uuid4())
        legs = []
        for leg in decision.legs:
            fill = (
                long_entry(leg.contract)
                if leg.side == "buy"
                else short_entry(leg.contract)
            )
            legs.append(
                PaperLeg(
                    leg.contract.symbol,
                    leg.side,
                    leg.quantity,
                    leg.contract.option_type,
                    leg.contract.strike,
                    leg.contract.expiration,
                    leg.contract.multiplier,
                    leg.contract.bid,
                    leg.contract.ask,
                    fill.price,
                )
            )

        signed_entry_cost = sum(
            (1 if leg.side == "buy" else -1)
            * float(leg.entry_fill)
            * int(leg.multiplier)
            * int(leg.quantity)
            for leg in legs
        )
        if decision.structure == Structure.LONG_OPTION:
            entry_value = signed_entry_cost
            actual_maximum_risk = entry_value
        else:
            entry_value = -signed_entry_cost
            actual_maximum_risk = max(
                float(decision.maximum_risk)
                + float(decision.total_credit)
                - entry_value,
                0.0,
            )
        configured_limit = float(
            decision.configuration_snapshot["contract_filters"]
            ["maximum_risk_dollars"]
        )
        if entry_value <= 0:
            raise ValueError("Conservative paper fill produced a non-positive entry value")
        if actual_maximum_risk > configured_limit + 1e-9:
            raise ValueError(
                "Conservative paper fill exceeds the configured maximum risk: "
                f"{actual_maximum_risk:.2f} > {configured_limit:.2f}"
            )

        position = PaperPosition(
            position_id,
            decision.candidate_id,
            decision.strategy_id,
            decision.strategy_version,
            decision.strategy_hash,
            decision.symbol,
            decision.direction,
            decision.structure,
            PositionState.OPEN,
            utc_now(),
            legs,
            entry_value,
            actual_maximum_risk,
            float(
                decision.configuration_snapshot["management"]["profit_target_pct"]
            ),
            float(decision.configuration_snapshot["management"]["hard_stop_pct"]),
            entry_value,
            configuration_snapshot=decision.configuration_snapshot,
        )

        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO trade_cycles("
                "id,candidate_id,strategy_id,started_at,status"
                ") VALUES (?,?,?,?,?)",
                (
                    cycle_id,
                    decision.candidate_id,
                    decision.strategy_id,
                    position.opened_at,
                    "OPEN",
                ),
            )
            connection.execute(
                "INSERT INTO paper_positions("
                "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,"
                "strategy_hash,symbol,direction,structure,state,opened_at,"
                "entry_value,current_value,maximum_risk,pnl_dollars,pnl_pct,"
                "mfe_pct,mae_pct,config_json"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    position.position_id,
                    cycle_id,
                    position.candidate_id,
                    position.strategy_id,
                    position.strategy_version,
                    position.strategy_hash,
                    position.symbol,
                    str(position.direction),
                    str(position.structure),
                    str(position.state),
                    position.opened_at,
                    position.entry_value,
                    position.current_value,
                    position.maximum_risk,
                    0,
                    0,
                    0,
                    0,
                    json.dumps(position.configuration_snapshot, sort_keys=True),
                ),
            )
            for leg in legs:
                connection.execute(
                    "INSERT INTO paper_legs("
                    "position_id,contract_symbol,side,quantity,option_type,"
                    "strike,expiration,multiplier,entry_bid,entry_ask,entry_fill,"
                    "current_bid,current_ask,current_mark"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        position.position_id,
                        leg.contract_symbol,
                        leg.side,
                        leg.quantity,
                        leg.option_type,
                        leg.strike,
                        leg.expiration,
                        leg.multiplier,
                        leg.entry_bid,
                        leg.entry_ask,
                        leg.entry_fill,
                        0,
                        0,
                        0,
                    ),
                )
            self._event(
                connection,
                position.position_id,
                None,
                PositionState.OPEN,
                "paper-entry",
                "eligible candidate opened",
            )
            connection.execute(
                "UPDATE candidates SET status=? WHERE id=?",
                (str(CandidateStatus.OPENED), decision.candidate_id),
            )
        return position

    def open_candidate(self, candidate_id: str):
        from ..core.enums import Direction, Regime, Structure
        from ..core.models import CandidateDecision, CandidateLeg, OptionContract

        rows = self.db.query(
            "SELECT * FROM candidates WHERE id=?",
            (candidate_id,),
        )
        if not rows:
            raise KeyError(candidate_id)
        row = rows[0]
        if row["status"] not in {"ELIGIBLE", "SELECTED"}:
            raise ValueError("Candidate is not eligible for a paper position")

        raw_legs = self.db.query(
            "SELECT * FROM candidate_legs WHERE candidate_id=? ORDER BY id",
            (candidate_id,),
        )
        legs = []
        for raw in raw_legs:
            details = json.loads(raw["details_json"])
            contract = OptionContract(**details)
            legs.append(CandidateLeg(contract, raw["side"], raw["quantity"]))

        decision = CandidateDecision(
            candidate_id=row["id"],
            scan_cycle_id=row["scan_cycle_id"],
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            strategy_hash=row["strategy_hash"],
            preset=row["preset"],
            symbol=row["symbol"],
            direction=Direction(row["direction"]),
            structure=Structure(row["structure"]),
            regime=Regime(row["regime"]),
            observed_at=row["observed_at"],
            underlying_price=0.0,
            legs=legs,
            setup_score=row["setup_score"],
            ranking_score=row["ranking_score"],
            status=CandidateStatus(row["status"]),
            total_debit=row["total_debit"],
            total_credit=row["total_credit"],
            maximum_risk=row["maximum_risk"],
            configuration_snapshot=json.loads(row["config_json"]),
        )
        return self.open(decision)

    @staticmethod
    def _exit_fill(side: str, bid: float, ask: float, slippage: float) -> float:
        if side == "buy":
            return max(float(bid) - slippage, 0.0)
        return max(float(ask), 0.0) + slippage

    def mark(
        self,
        position_id: str,
        leg_quotes: dict[str, tuple[float, float]],
    ) -> dict:
        rows = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?",
            (position_id,),
        )
        if not rows:
            raise KeyError(position_id)
        position = rows[0]
        if position["state"] in CLOSED_STATES:
            return {
                "position_id": position_id,
                "current_value": position["current_value"],
                "pnl_dollars": position["pnl_dollars"],
                "pnl_pct": position["pnl_pct"],
                "mfe_pct": position["mfe_pct"],
                "mae_pct": position["mae_pct"],
                "state": position["state"],
                "trigger": None,
            }

        legs = self.db.query(
            "SELECT * FROM paper_legs WHERE position_id=?",
            (position_id,),
        )
        config = json.loads(position["config_json"])
        slippage = float(
            config.get("management", {}).get("paper_slippage_per_share", 0.01)
        )
        signed_liquidation_value = 0.0

        with self.db.transaction() as connection:
            for leg in legs:
                bid, ask = leg_quotes[leg["contract_symbol"]]
                mark = (float(bid) + float(ask)) / 2
                liquidation = self._exit_fill(
                    leg["side"], float(bid), float(ask), slippage
                )
                signed = -1 if leg["side"] == "sell" else 1
                signed_liquidation_value += (
                    signed
                    * liquidation
                    * int(leg["multiplier"])
                    * int(leg["quantity"])
                )
                connection.execute(
                    "UPDATE paper_legs SET current_bid=?,current_ask=?,"
                    "current_mark=? WHERE id=?",
                    (bid, ask, mark, leg["id"]),
                )

            if position["structure"] == str(Structure.CREDIT_SPREAD):
                current_value = -signed_liquidation_value
                pnl = float(position["entry_value"]) - current_value
                denominator = max(float(position["maximum_risk"]), 0.01)
            else:
                current_value = signed_liquidation_value
                pnl = current_value - float(position["entry_value"])
                denominator = max(float(position["entry_value"]), 0.01)

            pnl_pct = pnl / denominator
            mfe = max(float(position["mfe_pct"]), pnl_pct)
            mae = min(float(position["mae_pct"]), pnl_pct)
            state = str(position["state"])
            trigger = None
            management = config.get("management", {})
            if state in ACTIVE_STATES:
                if pnl_pct >= float(management.get("profit_target_pct", 1.0)):
                    state = str(PositionState.EXIT_PENDING)
                    trigger = "profit target"
                elif pnl_pct <= -abs(float(management.get("hard_stop_pct", 1.0))):
                    state = str(PositionState.EXIT_PENDING)
                    trigger = "hard stop"

            connection.execute(
                "UPDATE paper_positions SET current_value=?,pnl_dollars=?,"
                "pnl_pct=?,mfe_pct=?,mae_pct=?,state=? WHERE id=?",
                (current_value, pnl, pnl_pct, mfe, mae, state, position_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO mfe_mae("
                "position_id,mfe_pct,mae_pct,updated_at"
                ") VALUES (?,?,?,?)",
                (position_id, mfe, mae, utc_now()),
            )
            connection.execute(
                "INSERT INTO position_marks("
                "id,position_id,value,pnl_dollars,pnl_pct,observed_at"
                ") VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), position_id, current_value, pnl, pnl_pct, utc_now()),
            )
            if trigger and state != str(position["state"]):
                self._event(
                    connection,
                    position_id,
                    PositionState(position["state"]),
                    PositionState.EXIT_PENDING,
                    "management",
                    trigger,
                )

        return {
            "position_id": position_id,
            "current_value": current_value,
            "pnl_dollars": pnl,
            "pnl_pct": pnl_pct,
            "mfe_pct": mfe,
            "mae_pct": mae,
            "state": state,
            "trigger": trigger,
        }

    def close(
        self,
        position_id: str,
        leg_quotes: dict[str, tuple[float, float]],
        reason: str = "owner-close",
    ) -> dict:
        existing = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?", (position_id,)
        )
        if not existing:
            raise KeyError(position_id)
        if existing[0]["state"] in CLOSED_STATES:
            outcome = self.db.query(
                "SELECT * FROM closed_outcomes WHERE position_id=?", (position_id,)
            )
            return {
                "position_id": position_id,
                "state": existing[0]["state"],
                "pnl_dollars": existing[0]["pnl_dollars"],
                "pnl_pct": existing[0]["pnl_pct"],
                "reason": outcome[0]["exit_reason"] if outcome else reason,
                "already_closed": True,
            }

        mark = self.mark(position_id, leg_quotes)
        position = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?", (position_id,)
        )[0]
        pnl = float(mark["pnl_dollars"])
        final = (
            PositionState.CLOSED_WIN
            if pnl > 0
            else PositionState.CLOSED_LOSS
            if pnl < 0
            else PositionState.CLOSED_BREAKEVEN
        )
        closed_at = utc_now()
        config = json.loads(position["config_json"])
        slippage = float(
            config.get("management", {}).get("paper_slippage_per_share", 0.01)
        )

        with self.db.transaction() as connection:
            for leg in self.db.query(
                "SELECT * FROM paper_legs WHERE position_id=?", (position_id,)
            ):
                bid, ask = leg_quotes[leg["contract_symbol"]]
                connection.execute(
                    "UPDATE paper_legs SET exit_fill=? WHERE id=?",
                    (
                        self._exit_fill(
                            leg["side"], float(bid), float(ask), slippage
                        ),
                        leg["id"],
                    ),
                )
            connection.execute(
                "UPDATE paper_positions SET state=?,closed_at=? WHERE id=?",
                (str(final), closed_at, position_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO closed_outcomes("
                "position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at"
                ") VALUES (?,?,?,?,?,?)",
                (position_id, str(final), reason, pnl, mark["pnl_pct"], closed_at),
            )
            connection.execute(
                "UPDATE trade_cycles SET status=?,completed_at=? WHERE id=?",
                ("CLOSED", closed_at, position["trade_cycle_id"]),
            )
            self._event(
                connection,
                position_id,
                PositionState(position["state"]),
                final,
                "paper-exit",
                reason,
            )

        return {**mark, "state": str(final), "reason": reason}

    def _event(self, connection, position_id, previous, new, trigger, reason):
        connection.execute(
            "INSERT INTO lifecycle_events("
            "id,position_id,previous_state,new_state,trigger,reason,"
            "details_json,observed_at"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                position_id,
                str(previous) if previous else None,
                str(new),
                trigger,
                reason,
                "{}",
                utc_now(),
            ),
        )
