from __future__ import annotations
from dataclasses import dataclass
from ..core.models import CandidateLeg

@dataclass(frozen=True)
class RiskResult:
    eligible: bool
    total_debit: float
    total_credit: float
    maximum_risk: float
    reason: str

def long_option_risk(fill: float, multiplier: int, fees: float, limit: float=100.0) -> RiskResult:
    total=round(fill*multiplier+fees,2)
    ok=0 < total <= limit
    return RiskResult(ok,total,0,total, f'total debit ${total:.2f} is within ${limit:.2f}' if ok else f'total debit ${total:.2f} exceeds ${limit:.2f}')

def credit_spread_risk(short_fill: float, long_fill: float, short_strike: float, long_strike: float, multiplier: int, fees: float, limit: float=100.0) -> RiskResult:
    width=abs(short_strike-long_strike)
    credit=round((short_fill-long_fill)*multiplier-fees,2)
    max_risk=round(width*multiplier-credit,2)
    ok=credit>0 and 0<max_risk<=limit
    reason=(f'maximum modeled loss ${max_risk:.2f} is within ${limit:.2f}' if ok else f'maximum modeled loss ${max_risk:.2f} exceeds ${limit:.2f} or credit is invalid')
    return RiskResult(ok,0,max(credit,0),max_risk,reason)
