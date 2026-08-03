from __future__ import annotations
from .service import UniverseDecision

class UniverseDiscovery:
    """Builds a ticker-agnostic candidate pool from Tradier's read-only ETB list."""
    def __init__(self, provider, quote_batch_size:int=50, optionability_checks:int=80):
        self.provider=provider; self.quote_batch_size=quote_batch_size; self.optionability_checks=optionability_checks
    def discover(self,limit:int=25)->list[UniverseDecision]:
        securities=self.provider.etb_securities()
        symbols=sorted({str(x['symbol']).upper() for x in securities if str(x['symbol']).replace('.','').isalnum()})
        quotes=[]
        for i in range(0,len(symbols),self.quote_batch_size):
            try: quotes.extend(self.provider.quotes(symbols[i:i+self.quote_batch_size],priority=6))
            except Exception: continue
        ranked=sorted([q for q in quotes if q.last>0 and q.volume>0],key=lambda q:(-q.volume,q.symbol))[:self.optionability_checks]
        decisions=[]
        for q in ranked:
            rejections=[]; expirations=[]
            try: expirations=self.provider.expirations(q.symbol)
            except Exception as exc: rejections.append(f'optionability check failed: {type(exc).__name__}')
            eligible=bool(expirations)
            if not eligible and not rejections: rejections.append('no option expirations returned')
            score=float(q.volume)
            decisions.append(UniverseDecision(q.symbol,score,eligible,{'underlying_volume':q.volume,'last':q.last,'expiration_count':len(expirations),'quote_observed_at':q.observed_at},rejections))
            if sum(d.eligible for d in decisions)>=limit: break
        return decisions
