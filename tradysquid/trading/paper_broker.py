from __future__ import annotations
import json, uuid
from ..core.enums import CandidateStatus, PositionState, Structure
from ..core.models import CandidateDecision, PaperLeg, PaperPosition, utc_now
from .fills import long_entry, long_exit, short_entry, short_exit

class PaperBroker:
    def __init__(self,database): self.db=database
    def open(self,d:CandidateDecision)->PaperPosition:
        if d.status not in {CandidateStatus.ELIGIBLE,CandidateStatus.SELECTED}: raise ValueError('Only eligible or selected candidates can become paper positions')
        if not d.legs: raise ValueError('Candidate has no option legs')
        position_id=str(uuid.uuid4()); cycle_id=str(uuid.uuid4()); legs=[]
        for leg in d.legs:
            fill=long_entry(leg.contract) if leg.side=='buy' else short_entry(leg.contract)
            legs.append(PaperLeg(leg.contract.symbol,leg.side,leg.quantity,leg.contract.option_type,leg.contract.strike,leg.contract.expiration,leg.contract.multiplier,leg.contract.bid,leg.contract.ask,fill.price))
        entry=d.total_debit if d.structure==Structure.LONG_OPTION else d.total_credit
        p=PaperPosition(position_id,d.candidate_id,d.strategy_id,d.strategy_version,d.strategy_hash,d.symbol,d.direction,d.structure,PositionState.OPEN,utc_now(),legs,entry,d.maximum_risk,float(d.configuration_snapshot['management']['profit_target_pct']),float(d.configuration_snapshot['management']['hard_stop_pct']),entry,configuration_snapshot=d.configuration_snapshot)
        with self.db.transaction() as c:
            c.execute('INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,status) VALUES (?,?,?,?,?)',(cycle_id,d.candidate_id,d.strategy_id,p.opened_at,'OPEN'))
            c.execute('INSERT INTO paper_positions(id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,symbol,direction,structure,state,opened_at,entry_value,current_value,maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (p.position_id,cycle_id,p.candidate_id,p.strategy_id,p.strategy_version,p.strategy_hash,p.symbol,str(p.direction),str(p.structure),str(p.state),p.opened_at,p.entry_value,p.current_value,p.maximum_risk,0,0,0,0,json.dumps(p.configuration_snapshot,sort_keys=True)))
            for leg in legs:
                c.execute('INSERT INTO paper_legs(position_id,contract_symbol,side,quantity,option_type,strike,expiration,multiplier,entry_bid,entry_ask,entry_fill,current_bid,current_ask,current_mark) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(p.position_id,leg.contract_symbol,leg.side,leg.quantity,leg.option_type,leg.strike,leg.expiration,leg.multiplier,leg.entry_bid,leg.entry_ask,leg.entry_fill,0,0,0))
            self._event(c,p.position_id,None,PositionState.OPEN,'paper-entry','eligible candidate opened')
            c.execute('UPDATE candidates SET status=? WHERE id=?',(str(CandidateStatus.OPENED),d.candidate_id))
        return p
    def mark(self,position_id:str,leg_quotes:dict[str,tuple[float,float]])->dict:
        rows=self.db.query('SELECT * FROM paper_positions WHERE id=?',(position_id,));
        if not rows: raise KeyError(position_id)
        p=rows[0]; legs=self.db.query('SELECT * FROM paper_legs WHERE position_id=?',(position_id,)); value=0.0
        with self.db.transaction() as c:
            for leg in legs:
                bid,ask=leg_quotes[leg['contract_symbol']]
                mark=(bid+ask)/2
                signed = -1 if leg['side']=='sell' else 1
                value += signed*mark*leg['multiplier']*leg['quantity']
                c.execute('UPDATE paper_legs SET current_bid=?,current_ask=?,current_mark=? WHERE id=?',(bid,ask,mark,leg['id']))
            if p['structure']=='credit-spread':
                current_value=-value; pnl=p['entry_value']-current_value
                denominator=max(p['maximum_risk'],.01)
            else:
                current_value=value; pnl=current_value-p['entry_value']; denominator=max(p['entry_value'],.01)
            pnl_pct=pnl/denominator; mfe=max(p['mfe_pct'],pnl_pct); mae=min(p['mae_pct'],pnl_pct)
            state=p['state']; trigger=None
            cfg=json.loads(p['config_json'])
            if pnl_pct>=float(cfg['management']['profit_target_pct']): state=str(PositionState.EXIT_PENDING); trigger='profit target'
            elif pnl_pct<=-float(cfg['management']['hard_stop_pct']): state=str(PositionState.EXIT_PENDING); trigger='hard stop'
            c.execute('UPDATE paper_positions SET current_value=?,pnl_dollars=?,pnl_pct=?,mfe_pct=?,mae_pct=?,state=? WHERE id=?',(current_value,pnl,pnl_pct,mfe,mae,state,position_id))
            c.execute('INSERT OR REPLACE INTO mfe_mae(position_id,mfe_pct,mae_pct,updated_at) VALUES (?,?,?,?)',(position_id,mfe,mae,utc_now()))
            c.execute('INSERT INTO position_marks(id,position_id,value,pnl_dollars,pnl_pct,observed_at) VALUES (?,?,?,?,?,?)',(str(uuid.uuid4()),position_id,current_value,pnl,pnl_pct,utc_now()))
            if trigger: self._event(c,position_id,PositionState(p['state']),PositionState.EXIT_PENDING,'management',trigger)
        return {'position_id':position_id,'current_value':current_value,'pnl_dollars':pnl,'pnl_pct':pnl_pct,'mfe_pct':mfe,'mae_pct':mae,'state':state}
    def close(self,position_id:str,leg_quotes:dict[str,tuple[float,float]],reason='owner-close')->dict:
        mark=self.mark(position_id,leg_quotes); p=self.db.query('SELECT * FROM paper_positions WHERE id=?',(position_id,))[0]
        pnl=mark['pnl_dollars']; final=PositionState.CLOSED_WIN if pnl>0 else PositionState.CLOSED_LOSS if pnl<0 else PositionState.CLOSED_BREAKEVEN
        with self.db.transaction() as c:
            c.execute('UPDATE paper_positions SET state=?,closed_at=? WHERE id=?',(str(final),utc_now(),position_id))
            c.execute('INSERT INTO closed_outcomes(position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at) VALUES (?,?,?,?,?,?)',(position_id,str(final),reason,pnl,mark['pnl_pct'],utc_now()))
            c.execute('UPDATE trade_cycles SET status=?,completed_at=? WHERE id=?',('CLOSED',utc_now(),p['trade_cycle_id']))
            self._event(c,position_id,PositionState(p['state']),final,'paper-exit',reason)
        return {**mark,'state':str(final),'reason':reason}
    def _event(self,c,position_id,previous,new,trigger,reason):
        c.execute('INSERT INTO lifecycle_events(id,position_id,previous_state,new_state,trigger,reason,details_json,observed_at) VALUES (?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),position_id,str(previous) if previous else None,str(new),trigger,reason,'{}',utc_now()))
