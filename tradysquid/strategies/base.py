from __future__ import annotations
import copy, uuid
from datetime import date, datetime
from typing import Any
from ..core.enums import CandidateStatus, Direction, Regime, Structure
from ..core.models import CandidateDecision, CandidateLeg, OptionContract, utc_now
from ..trading.fills import long_entry, short_entry
from ..trading.risk import long_option_risk, credit_spread_risk

class Strategy:
    def __init__(self, config: dict[str,Any]): self.config=copy.deepcopy(config)
    @property
    def id(self): return self.config['strategy_id']
    def acknowledgement(self, component: str) -> dict[str,str]:
        return {'strategy_id':self.id,'version':self.config['version'],'hash':self.config['configuration_hash'],'component':component}

    def _base_rejections(self, contract: OptionContract, regime: Regime) -> list[str]:
        f=self.config['contract_filters']; reasons=[]
        if regime.value not in self.config['entry']['allowed_regimes']: reasons.append(f'blocked regime: {regime.value}')
        if contract.volume < int(f['minimum_option_volume']): reasons.append('insufficient option volume')
        if contract.open_interest < int(f['minimum_open_interest']): reasons.append('insufficient open interest')
        if contract.spread_pct > float(f['maximum_bid_ask_pct']): reasons.append('bid/ask spread too wide')
        if contract.delta is None: reasons.append('delta unavailable')
        elif not float(f['minimum_abs_delta']) <= abs(contract.delta) <= float(f['maximum_abs_delta']): reasons.append('delta outside configured range')
        if contract.ask <= 0: reasons.append('invalid option ask')
        try:
            dte=(datetime.strptime(contract.expiration,'%Y-%m-%d').date()-date.today()).days
            if not int(f['minimum_dte']) <= dte <= int(f['maximum_dte']): reasons.append('DTE outside configured range')
        except ValueError: reasons.append('invalid expiration date')
        return reasons

    def evaluate_long(self, scan_id: str, symbol: str, underlying_price: float, regime: Regime, contracts: list[OptionContract], setup_score: float) -> CandidateDecision:
        direction=Direction(self.config['direction']); target_type=direction.value
        matching=[c for c in contracts if c.option_type==target_type]
        matching.sort(key=lambda c:(len(self._base_rejections(c,regime)), abs((abs(c.delta) if c.delta is not None else 9)-0.4), c.spread_pct, -c.open_interest))
        if not matching:
            return self._empty(scan_id,symbol,regime,underlying_price,setup_score,['no matching option contracts'])
        contract=matching[0]; reasons=self._base_rejections(contract,regime)
        if setup_score < float(self.config['entry']['minimum_setup_score']): reasons.append('setup score below configured minimum')
        max_distance=float(self.config['contract_filters'].get('maximum_strike_distance_pct',1.0))
        if underlying_price>0 and abs(contract.strike-underlying_price)/underlying_price>max_distance: reasons.append('strike outside configured distance')
        fill=long_entry(contract,float(self.config['management']['paper_slippage_per_share']))
        risk=long_option_risk(fill.price,contract.multiplier,float(self.config['management']['estimated_fees']),float(self.config['contract_filters']['maximum_risk_dollars']))
        if not risk.eligible: reasons.append(risk.reason)
        if contract.ask > float(self.config['contract_filters']['maximum_quoted_premium']): reasons.append('premium exceeds configured per-share limit')
        status=CandidateStatus.REJECTED if reasons else CandidateStatus.ELIGIBLE
        return CandidateDecision(str(uuid.uuid4()),scan_id,self.id,self.config['version'],self.config['configuration_hash'],self.config['preset'],symbol,direction,Structure.LONG_OPTION,regime,utc_now(),underlying_price,[CandidateLeg(contract,'buy')],setup_score,setup_score,status,
            supporting_evidence=['contract selected by delta, liquidity, and spread quality'] if not reasons else [], opposing_evidence=[], missing_evidence=[],
            rules_passed=[] if reasons else ['regime','liquidity','delta','risk'], rules_failed=reasons.copy(), rejection_reasons=reasons,
            total_debit=risk.total_debit, maximum_risk=risk.maximum_risk, configuration_snapshot=copy.deepcopy(self.config))

    def evaluate_credit_spread(self, scan_id: str, symbol: str, underlying_price: float, regime: Regime, contracts: list[OptionContract], setup_score: float) -> CandidateDecision:
        direction=Direction(self.config['direction']); option_type=direction.value; f=self.config['contract_filters']
        candidates=[c for c in contracts if c.option_type==option_type and c.delta is not None and float(f['minimum_abs_delta'])<=abs(c.delta)<=float(f['maximum_abs_delta'])]
        reverse = direction==Direction.CALL
        candidates.sort(key=lambda c:c.strike, reverse=reverse)
        best=None
        for short in candidates:
            protective=[c for c in contracts if c.option_type==option_type and c.expiration==short.expiration and ((c.strike<short.strike) if direction==Direction.PUT else (c.strike>short.strike))]
            protective.sort(key=lambda c:abs(c.strike-short.strike))
            for long in protective:
                if abs(long.strike-short.strike) <= float(f['maximum_spread_width']):
                    best=(short,long); break
            if best: break
        if not best: return self._empty(scan_id,symbol,regime,underlying_price,setup_score,['no valid protective spread leg'])
        short,long=best; reasons=self._base_rejections(short,regime)+self._base_rejections(long,regime)
        if setup_score < float(self.config['entry']['minimum_setup_score']): reasons.append('setup score below configured minimum')
        sf=short_entry(short,float(self.config['management']['paper_slippage_per_share']))
        lf=long_entry(long,float(self.config['management']['paper_slippage_per_share']))
        risk=credit_spread_risk(sf.price,lf.price,short.strike,long.strike,short.multiplier,float(self.config['management']['estimated_fees']),float(f['maximum_risk_dollars']))
        if risk.total_credit < float(f['minimum_spread_credit_dollars']): reasons.append('spread credit below configured minimum')
        if not risk.eligible: reasons.append(risk.reason)
        status=CandidateStatus.REJECTED if reasons else CandidateStatus.ELIGIBLE
        return CandidateDecision(str(uuid.uuid4()),scan_id,self.id,self.config['version'],self.config['configuration_hash'],self.config['preset'],symbol,direction,Structure.CREDIT_SPREAD,regime,utc_now(),underlying_price,[CandidateLeg(short,'sell'),CandidateLeg(long,'buy')],setup_score,setup_score,status,
            supporting_evidence=['defined-risk spread assembled from adjacent liquid legs'] if not reasons else [], rules_passed=[] if reasons else ['regime','liquidity','delta','defined-risk'], rules_failed=reasons.copy(), rejection_reasons=reasons,
            total_credit=risk.total_credit,maximum_risk=risk.maximum_risk,configuration_snapshot=copy.deepcopy(self.config))

    def _empty(self,scan_id,symbol,regime,price,score,reasons):
        return CandidateDecision(str(uuid.uuid4()),scan_id,self.id,self.config['version'],self.config['configuration_hash'],self.config['preset'],symbol,Direction(self.config['direction']),Structure(self.config['structure']),regime,utc_now(),price,[],score,score,CandidateStatus.REJECTED,rejection_reasons=reasons,rules_failed=reasons.copy(),configuration_snapshot=copy.deepcopy(self.config))

    def evaluate(self,*args,**kwargs):
        return self.evaluate_long(*args,**kwargs) if self.config['structure']=='long-option' else self.evaluate_credit_spread(*args,**kwargs)
