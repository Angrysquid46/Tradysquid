from __future__ import annotations
import json, uuid
from dataclasses import dataclass
from typing import Any
from ..core.models import utc_now

@dataclass(frozen=True)
class UniverseDecision:
    symbol: str; score: float; eligible: bool; evidence: dict[str,Any]; rejections: list[str]

class UniverseService:
    def __init__(self,database,maximum_active:int=25):
        if maximum_active!=25: raise ValueError('Maximum active universe must be 25')
        self.db=database; self.maximum_active=maximum_active
    def seed(self,symbols:list[str]) -> None:
        now=utc_now()
        with self.db.transaction() as conn:
            for raw in symbols:
                symbol=raw.strip().upper()
                if not symbol or not symbol.replace('.','').isalnum(): continue
                conn.execute('INSERT OR IGNORE INTO universe_candidates(symbol,source,pinned,excluded,updated_at) VALUES (?,?,?,?,?)',(symbol,'configuration',0,0,now))
    def rotate(self,decisions:list[UniverseDecision],protected:set[str]|None=None,pinned:set[str]|None=None) -> list[str]:
        protected={s.upper() for s in (protected or set())}; pinned={s.upper() for s in (pinned or set())}
        eligible={d.symbol.upper():d for d in decisions if d.eligible}
        ordered=sorted(eligible.values(),key=lambda d:(d.symbol.upper() not in pinned,-d.score,d.symbol.upper()))
        selected=[]
        for s in sorted(protected|pinned):
            if s not in selected: selected.append(s)
        for d in ordered:
            if d.symbol.upper() not in selected and len(selected)<self.maximum_active: selected.append(d.symbol.upper())
        if len(selected)>self.maximum_active: raise ValueError('Protected and pinned symbols exceed the 25-symbol universe limit')
        now=utc_now()
        with self.db.transaction() as conn:
            prior={r['symbol']:bool(r['active']) for r in conn.execute('SELECT symbol,active FROM universe_membership')}
            all_symbols=set(prior)|set(selected)|set(eligible)
            for symbol in all_symbols:
                active=symbol in selected; d=eligible.get(symbol); score=d.score if d else 0.0
                reason='protected' if symbol in protected else 'pinned' if symbol in pinned else 'ranked' if active else 'not selected'
                conn.execute('INSERT OR REPLACE INTO universe_membership(symbol,active,pinned,protected,score,reason,updated_at) VALUES (?,?,?,?,?,?,?)',(symbol,int(active),int(symbol in pinned),int(symbol in protected),score,reason,now))
                if prior.get(symbol)!=active:
                    conn.execute('INSERT INTO universe_history(symbol,previous_state,new_state,reason,observed_at) VALUES (?,?,?,?,?)',(symbol,str(prior.get(symbol)),str(active),reason,now))
            for d in decisions:
                conn.execute('INSERT INTO universe_evaluations(id,symbol,observed_at,score,eligible,evidence_json,rejection_json) VALUES (?,?,?,?,?,?,?)',(str(uuid.uuid4()),d.symbol,now,d.score,int(d.eligible),json.dumps(d.evidence),json.dumps(d.rejections)))
        return selected
    def active(self)->list[str]:
        return [r['symbol'] for r in self.db.query('SELECT symbol FROM universe_membership WHERE active=1 ORDER BY pinned DESC, score DESC, symbol')]
