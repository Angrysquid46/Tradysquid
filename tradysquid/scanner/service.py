from __future__ import annotations
import json, uuid
from datetime import date, timedelta
from ..core.enums import CandidateStatus
from ..core.models import CandidateDecision, utc_now
from ..market.regime import classify_regime
from .selection import CandidateSelector

class ScanService:
    def __init__(self,database,provider,registry): self.db=database; self.provider=provider; self.registry=registry; self.selector=CandidateSelector()
    def _persist(self,d:CandidateDecision):
        with self.db.transaction() as c:
            c.execute('INSERT INTO candidates(id,scan_cycle_id,strategy_id,strategy_version,strategy_hash,preset,symbol,direction,structure,regime,status,setup_score,ranking_score,total_debit,total_credit,maximum_risk,config_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (d.candidate_id,d.scan_cycle_id,d.strategy_id,d.strategy_version,d.strategy_hash,d.preset,d.symbol,str(d.direction),str(d.structure),str(d.regime),str(d.status),d.setup_score,d.ranking_score,d.total_debit,d.total_credit,d.maximum_risk,json.dumps(d.configuration_snapshot,sort_keys=True),d.observed_at))
            for leg in d.legs:
                c.execute('INSERT INTO candidate_legs(candidate_id,contract_symbol,side,quantity,details_json) VALUES (?,?,?,?,?)',(d.candidate_id,leg.contract.symbol,leg.side,leg.quantity,json.dumps(leg.contract.__dict__,sort_keys=True)))
            for x in d.supporting_evidence: c.execute('INSERT INTO candidate_evidence(candidate_id,evidence_type,value) VALUES (?,?,?)',(d.candidate_id,'supporting',x))
            for x in d.opposing_evidence: c.execute('INSERT INTO candidate_evidence(candidate_id,evidence_type,value) VALUES (?,?,?)',(d.candidate_id,'opposing',x))
            for x in d.missing_evidence: c.execute('INSERT INTO candidate_evidence(candidate_id,evidence_type,value) VALUES (?,?,?)',(d.candidate_id,'missing',x))
            for x in d.rules_passed: c.execute('INSERT INTO candidate_rules(candidate_id,rule_id,passed,detail) VALUES (?,?,1,?)',(d.candidate_id,x,x))
            for x in d.rules_failed: c.execute('INSERT INTO candidate_rules(candidate_id,rule_id,passed,detail) VALUES (?,?,0,?)',(d.candidate_id,x,x))
            for x in d.rejection_reasons: c.execute('INSERT INTO candidate_rejections(candidate_id,reason) VALUES (?,?)',(d.candidate_id,x))
            if d.status==CandidateStatus.REJECTED and d.legs:
                c.execute('INSERT OR IGNORE INTO shadow_candidates(candidate_id,source_status,opened_at) VALUES (?,?,?)',(d.candidate_id,str(d.status),d.observed_at))
    def scan_symbol(self,symbol:str,trigger='manual')->list[CandidateDecision]:
        scan_id=str(uuid.uuid4()); start=utc_now()
        self.db.execute('INSERT INTO scan_cycles(id,trigger,source,status,started_at,universe_json,totals_json,errors_json) VALUES (?,?,?,?,?,?,?,?)',(scan_id,trigger,'scan-service','RUNNING',start,json.dumps([symbol]),'{}','[]'))
        try:
            end=date.today(); start_date=end-timedelta(days=500)
            bars=self.provider.history(symbol,start_date.isoformat(),end.isoformat())
            regime=classify_regime(bars); price=float(bars[-1]['close']) if bars else 0
            expirations=self.provider.expirations(symbol)
            contracts=[]
            for expiration in expirations[:4]: contracts.extend(self.provider.option_chain(symbol,expiration))
            setup_score=regime.confidence
            decisions=[]
            for strategy in self.registry.enabled():
                d=strategy.evaluate(scan_id,symbol,price,regime.regime,contracts,setup_score)
                open_duplicate=self.db.query("SELECT 1 FROM paper_positions WHERE strategy_id=? AND symbol=? AND state IN ('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING') LIMIT 1",(strategy.id,symbol))
                if open_duplicate and d.status==CandidateStatus.ELIGIBLE:
                    d.status=CandidateStatus.REJECTED; d.rejection_reasons.append('duplicate active paper position'); d.rules_failed.append('duplicate active paper position')
                self._persist(d); decisions.append(d)
            selected=self.selector.select(decisions)
            for d in selected:
                self.db.execute('UPDATE candidates SET status=? WHERE id=?',(str(CandidateStatus.SELECTED),d.candidate_id))
            totals={'candidates':len(decisions),'rejected':sum(d.status==CandidateStatus.REJECTED for d in decisions),'eligible':sum(d.status==CandidateStatus.ELIGIBLE for d in decisions),'selected':len(selected),'shadow':sum(d.status==CandidateStatus.REJECTED and bool(d.legs) for d in decisions)}
            self.db.execute('UPDATE scan_cycles SET status=?,completed_at=?,totals_json=? WHERE id=?',('COMPLETED',utc_now(),json.dumps(totals),scan_id))
            return decisions
        except Exception as exc:
            self.db.execute('UPDATE scan_cycles SET status=?,completed_at=?,errors_json=? WHERE id=?',('FAILED',utc_now(),json.dumps([f'{type(exc).__name__}: {exc}']),scan_id))
            raise
