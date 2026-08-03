from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..core.models import utc_now


class ShadowTrackingService:
    """Track rejected candidates with real option marks and close outcomes.

    Rejected candidates that had usable option legs are retained as shadow
    observations. This service values those legs from current read-only Tradier
    chains, stores MFE/MAE marks, and closes the observation when the strategy's
    recorded target, stop, or expiration is reached.
    """

    def __init__(self, database) -> None:
        self.db = database

    def mark(
        self,
        candidate_id: str,
        current_value: float,
        entry_value: float,
    ) -> dict[str, float | str]:
        if entry_value <= 0:
            raise ValueError("entry_value must be positive")
        move = (current_value - entry_value) / entry_value
        self.db.execute(
            "INSERT INTO shadow_marks("
            "candidate_id,observed_at,value,favorable_pct,adverse_pct"
            ") VALUES (?,?,?,?,?)",
            (
                candidate_id,
                utc_now(),
                current_value,
                max(move, 0.0),
                min(move, 0.0),
            ),
        )
        rows = self.db.query(
            "SELECT MAX(favorable_pct) AS mfe,MIN(adverse_pct) AS mae "
            "FROM shadow_marks WHERE candidate_id=?",
            (candidate_id,),
        )
        metrics = rows[0] if rows else {}
        return {
            "candidate_id": candidate_id,
            "current_value": current_value,
            "entry_value": entry_value,
            "move_pct": move,
            "mfe_pct": float(metrics.get("mfe") or 0.0),
            "mae_pct": float(metrics.get("mae") or 0.0),
        }

    @staticmethod
    def _details(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("details_json")
        if isinstance(raw, dict):
            return raw
        try:
            value = json.loads(str(raw or "{}"))
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _midpoint(contract: Any) -> float:
        bid = max(float(getattr(contract, "bid", 0.0) or 0.0), 0.0)
        ask = max(float(getattr(contract, "ask", 0.0) or 0.0), 0.0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        return max(bid, ask)

    @staticmethod
    def _management(config_json: Any) -> tuple[float, float]:
        if isinstance(config_json, dict):
            config = config_json
        else:
            try:
                config = json.loads(str(config_json or "{}"))
            except (TypeError, ValueError):
                config = {}
        management = config.get("management", {}) if isinstance(config, dict) else {}
        target = float(management.get("profit_target_pct", 0.20) or 0.20)
        stop = float(management.get("hard_stop_pct", -0.15) or -0.15)
        if target <= 0:
            target = 0.20
        if stop >= 0:
            stop = -abs(stop or 0.15)
        return target, stop

    @staticmethod
    def _expiration_reached(legs: list[dict[str, Any]]) -> bool:
        expirations: list[date] = []
        for leg in legs:
            raw = str(leg.get("expiration") or "")
            try:
                expirations.append(datetime.strptime(raw, "%Y-%m-%d").date())
            except ValueError:
                continue
        return bool(expirations) and max(expirations) <= date.today()

    def _finish(
        self,
        candidate_id: str,
        outcome: str,
        metrics: dict[str, Any],
    ) -> None:
        closed_at = utc_now()
        self.db.execute(
            "INSERT OR REPLACE INTO shadow_outcomes("
            "candidate_id,outcome,mfe_pct,mae_pct,closed_at"
            ") VALUES (?,?,?,?,?)",
            (
                candidate_id,
                outcome,
                float(metrics.get("mfe_pct") or 0.0),
                float(metrics.get("mae_pct") or 0.0),
                closed_at,
            ),
        )
        self.db.execute(
            "UPDATE shadow_candidates SET closed_at=?,outcome=? WHERE candidate_id=?",
            (closed_at, outcome, candidate_id),
        )

    def monitor(self, provider: Any) -> dict[str, Any]:
        candidates = self.db.query(
            "SELECT s.candidate_id,c.symbol,c.structure,c.total_debit,c.total_credit,"
            "c.config_json,s.opened_at FROM shadow_candidates s "
            "JOIN candidates c ON c.id=s.candidate_id "
            "WHERE s.closed_at IS NULL ORDER BY s.opened_at"
        )
        chain_cache: dict[tuple[str, str], dict[str, Any]] = {}
        marked: list[dict[str, Any]] = []
        closed: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        for candidate in candidates:
            candidate_id = str(candidate["candidate_id"])
            try:
                raw_legs = self.db.query(
                    "SELECT contract_symbol,side,quantity,details_json "
                    "FROM candidate_legs WHERE candidate_id=? ORDER BY id",
                    (candidate_id,),
                )
                if not raw_legs:
                    raise ValueError("shadow candidate has no option legs")

                legs: list[dict[str, Any]] = []
                for raw_leg in raw_legs:
                    details = self._details(raw_leg)
                    expiration = str(details.get("expiration") or "")
                    if not expiration:
                        raise ValueError(
                            f"expiration missing for {raw_leg['contract_symbol']}"
                        )
                    legs.append(
                        {
                            "contract_symbol": str(raw_leg["contract_symbol"]),
                            "side": str(raw_leg["side"]).casefold(),
                            "quantity": int(raw_leg.get("quantity") or 1),
                            "expiration": expiration,
                            "multiplier": int(details.get("multiplier") or 100),
                        }
                    )

                leg_values: list[tuple[dict[str, Any], float]] = []
                symbol = str(candidate["symbol"])
                for leg in legs:
                    key = (symbol, leg["expiration"])
                    if key not in chain_cache:
                        chain_cache[key] = {
                            contract.symbol: contract
                            for contract in provider.option_chain(symbol, leg["expiration"])
                        }
                    contract = chain_cache[key].get(leg["contract_symbol"])
                    if contract is None:
                        raise ValueError(
                            f"current quote missing for {leg['contract_symbol']}"
                        )
                    midpoint = self._midpoint(contract)
                    if midpoint <= 0:
                        raise ValueError(
                            f"non-positive current mark for {leg['contract_symbol']}"
                        )
                    notional = midpoint * leg["multiplier"] * leg["quantity"]
                    leg_values.append((leg, notional))

                structure = str(candidate["structure"])
                total_debit = float(candidate.get("total_debit") or 0.0)
                total_credit = float(candidate.get("total_credit") or 0.0)
                if structure == "credit-spread":
                    entry_value = total_credit
                    current_close_cost = sum(
                        value if leg["side"] == "sell" else -value
                        for leg, value in leg_values
                    )
                    current_value = entry_value + (entry_value - current_close_cost)
                else:
                    entry_value = total_debit
                    current_value = sum(
                        value if leg["side"] == "buy" else -value
                        for leg, value in leg_values
                    )

                metrics = self.mark(candidate_id, current_value, entry_value)
                target, stop = self._management(candidate.get("config_json"))
                move = float(metrics["move_pct"])
                outcome = None
                if move >= target:
                    outcome = "TARGET"
                elif move <= stop:
                    outcome = "STOP"
                elif self._expiration_reached(legs):
                    outcome = "EXPIRED_WIN" if move > 0 else "EXPIRED_LOSS"

                result = {
                    **metrics,
                    "symbol": symbol,
                    "structure": structure,
                    "target_pct": target,
                    "stop_pct": stop,
                    "outcome": outcome,
                }
                marked.append(result)
                if outcome:
                    self._finish(candidate_id, outcome, metrics)
                    closed.append(result)
            except Exception as exc:
                failures.append(
                    {
                        "candidate_id": candidate_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        return {
            "open_candidates": len(candidates),
            "marked": len(marked),
            "closed": len(closed),
            "failed": len(failures),
            "marks": marked,
            "outcomes": closed,
            "failures": failures,
        }
