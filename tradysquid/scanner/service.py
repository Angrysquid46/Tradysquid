from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from ..core.enums import CandidateStatus
from ..core.models import CandidateDecision, utc_now
from ..market.regime import classify_regime
from .selection import CandidateSelector


class ScanService:
    def __init__(self, database, provider, registry):
        self.db = database
        self.provider = provider
        self.registry = registry
        self.selector = CandidateSelector()

    def _persist(self, decision: CandidateDecision) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO candidates("
                "id,scan_cycle_id,strategy_id,strategy_version,strategy_hash,preset,"
                "symbol,direction,structure,regime,status,setup_score,ranking_score,"
                "total_debit,total_credit,maximum_risk,config_json,observed_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision.candidate_id,
                    decision.scan_cycle_id,
                    decision.strategy_id,
                    decision.strategy_version,
                    decision.strategy_hash,
                    decision.preset,
                    decision.symbol,
                    str(decision.direction),
                    str(decision.structure),
                    str(decision.regime),
                    str(decision.status),
                    decision.setup_score,
                    decision.ranking_score,
                    decision.total_debit,
                    decision.total_credit,
                    decision.maximum_risk,
                    json.dumps(decision.configuration_snapshot, sort_keys=True),
                    decision.observed_at,
                ),
            )
            for leg in decision.legs:
                connection.execute(
                    "INSERT INTO candidate_legs("
                    "candidate_id,contract_symbol,side,quantity,details_json"
                    ") VALUES (?,?,?,?,?)",
                    (
                        decision.candidate_id,
                        leg.contract.symbol,
                        leg.side,
                        leg.quantity,
                        json.dumps(leg.contract.__dict__, sort_keys=True),
                    ),
                )
            for value in decision.supporting_evidence:
                connection.execute(
                    "INSERT INTO candidate_evidence(candidate_id,evidence_type,value) "
                    "VALUES (?,?,?)",
                    (decision.candidate_id, "supporting", value),
                )
            for value in decision.opposing_evidence:
                connection.execute(
                    "INSERT INTO candidate_evidence(candidate_id,evidence_type,value) "
                    "VALUES (?,?,?)",
                    (decision.candidate_id, "opposing", value),
                )
            for value in decision.missing_evidence:
                connection.execute(
                    "INSERT INTO candidate_evidence(candidate_id,evidence_type,value) "
                    "VALUES (?,?,?)",
                    (decision.candidate_id, "missing", value),
                )
            for value in decision.rules_passed:
                connection.execute(
                    "INSERT INTO candidate_rules(candidate_id,rule_id,passed,detail) "
                    "VALUES (?,?,1,?)",
                    (decision.candidate_id, value, value),
                )
            for value in decision.rules_failed:
                connection.execute(
                    "INSERT INTO candidate_rules(candidate_id,rule_id,passed,detail) "
                    "VALUES (?,?,0,?)",
                    (decision.candidate_id, value, value),
                )
            for value in decision.rejection_reasons:
                connection.execute(
                    "INSERT INTO candidate_rejections(candidate_id,reason) VALUES (?,?)",
                    (decision.candidate_id, value),
                )

    def scan_symbol(
        self,
        symbol: str,
        trigger: str = "manual",
    ) -> list[CandidateDecision]:
        scan_id = str(uuid.uuid4())
        started_at = utc_now()
        self.db.execute(
            "INSERT INTO scan_cycles("
            "id,trigger,source,status,started_at,universe_json,totals_json,errors_json"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                scan_id,
                trigger,
                "scan-service",
                "RUNNING",
                started_at,
                json.dumps([symbol]),
                "{}",
                "[]",
            ),
        )
        try:
            end = date.today()
            start = end - timedelta(days=500)
            bars = self.provider.history(symbol, start.isoformat(), end.isoformat())
            regime = classify_regime(bars)
            price = float(bars[-1]["close"]) if bars else 0.0
            expirations = self.provider.expirations(symbol)
            contracts = []
            for expiration in expirations[:4]:
                contracts.extend(self.provider.option_chain(symbol, expiration))

            setup_score = regime.confidence
            decisions: list[CandidateDecision] = []
            for strategy in self.registry.enabled():
                decision = strategy.evaluate(
                    scan_id,
                    symbol,
                    price,
                    regime.regime,
                    contracts,
                    setup_score,
                )
                open_duplicate = self.db.query(
                    "SELECT 1 FROM paper_positions WHERE strategy_id=? AND symbol=? "
                    "AND state IN ('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING') "
                    "LIMIT 1",
                    (strategy.id, symbol),
                )
                if open_duplicate and decision.status == CandidateStatus.ELIGIBLE:
                    decision.status = CandidateStatus.REJECTED
                    decision.rejection_reasons.append(
                        "duplicate active paper position"
                    )
                    decision.rules_failed.append("duplicate active paper position")
                self._persist(decision)
                decisions.append(decision)

            selected = self.selector.select(decisions)
            for decision in selected:
                self.db.execute(
                    "UPDATE candidates SET status=? WHERE id=?",
                    (str(CandidateStatus.SELECTED), decision.candidate_id),
                )

            totals = {
                "candidates": len(decisions),
                "rejected": sum(
                    decision.status == CandidateStatus.REJECTED
                    for decision in decisions
                ),
                "eligible": sum(
                    decision.status == CandidateStatus.ELIGIBLE
                    for decision in decisions
                ),
                "selected": len(selected),
            }
            self.db.execute(
                "UPDATE scan_cycles SET status=?,completed_at=?,totals_json=? WHERE id=?",
                ("COMPLETED", utc_now(), json.dumps(totals), scan_id),
            )
            return decisions
        except Exception as exc:
            self.db.execute(
                "UPDATE scan_cycles SET status=?,completed_at=?,errors_json=? WHERE id=?",
                (
                    "FAILED",
                    utc_now(),
                    json.dumps([f"{type(exc).__name__}: {exc}"]),
                    scan_id,
                ),
            )
            raise
