"""Private causal implementation of owner-selected SURGE configuration."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

MULTIPLIER=100
@dataclass
class Position:
    trade_id:str; symbol:str; side:str; contracts:int; entry:float; opened_at:datetime; peak_bid:float
@dataclass(frozen=True)
class Decision:
    action:str; reason:str; side:str|None=None; contract_symbol:str|None=None; price:float|None=None; contracts:int=0; score:float=0.

class Surge:
    def __init__(self):self.generation=1;self.position=None
    @staticmethod
    def signal(bars):
        if len(bars)<20:return None,0.,"INSUFFICIENT"
        c=[float(x["close"]) for x in bars[-20:]];h=[float(x["high"]) for x in bars[-20:]];l=[float(x["low"]) for x in bars[-20:]]
        w=3;net=c[-1]-c[-w-1];path=sum(abs(c[i]-c[i-1]) for i in range(len(c)-w,len(c))) or .01
        efficiency=abs(net)/path;recent=max(h[-w:])-min(l[-w:]);prior=max(h[-3*w:-w])-min(l[-3*w:-w]) or .01
        score=min(1.,.58*efficiency+.28*min(min(2.,recent/prior)/1.5,1)+.14*min(abs(net)/.8,1))
        flips=sum((c[i]-c[i-1])*(c[i-1]-c[i-2])<0 for i in range(2,len(c)))
        if efficiency<.30 or flips>=11:return None,score,"CHOP"
        if score<.62:return None,score,"WEAK"
        return ("call" if net>0 else "put"),score,"IMPULSE"
    @staticmethod
    def contract(options,side,bankroll):
        valid=[]
        for x in options.get("contracts",[]):
            try:
                bid,ask,delta=float(x["bid"]),float(x["ask"]),abs(float(x["delta"]));spread=(ask-bid)/ask
                if x.get("data_class")=="VERIFIED_REAL" and x.get("side")==side and bid>0 and ask>=bid and spread<=.18 and .35<=delta<=.70 and ask*100<=bankroll:valid.append(x)
            except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
        return min(valid,key=lambda x:(abs(abs(float(x["delta"]))-.5),float(x["ask"]))) if valid else None
    def decide(self,as_of,bankroll,market,options,bars):
        side,score,state=self.signal(bars)
        if self.position:
            quote=next((x for x in options.get("contracts",[]) if x.get("option_symbol")==self.position.symbol),None)
            if not quote or quote.get("data_class")!="VERIFIED_REAL" or quote.get("bid") is None:return Decision("NO_ACTION","OPEN_POSITION_QUOTE_UNAVAILABLE")
            bid=float(quote["bid"]);self.position.peak_bid=max(self.position.peak_bid,bid);change=bid/self.position.entry-1;peak=self.position.peak_bid/self.position.entry-1;held=(as_of-self.position.opened_at).total_seconds()/60
            reason=None
            if change<=-.20:reason="FAST_FAILURE_STOP"
            elif peak>=.08 and bid<=self.position.peak_bid*.90:reason="PROFIT_TRAIL"
            elif held>=1 and (state=="CHOP" or (side and side!=self.position.side)):reason="IMPULSE_REVERSAL"
            elif held>=12:reason="MAX_HOLD"
            if reason:return Decision("EXIT",reason,price=bid)
            return Decision("NO_ACTION","HOLDING")
        if market.get("tier")!="A" or options.get("tier") not in {"A","B"}:return Decision("NO_ACTION","TIER_A_REQUIRED")
        if not side:return Decision("NO_ACTION",state,score=score)
        contract=self.contract(options,side,bankroll)
        if not contract:return Decision("NO_ACTION","NO_AFFORDABLE_CONTRACT",score=score)
        ask=float(contract["ask"]);qty=int(bankroll*.35//(ask*100))
        if qty<1:return Decision("NO_ACTION","NO_AFFORDABLE_CONTRACT",score=score)
        return Decision("ENTER","THREE_MINUTE_IMPULSE",side,str(contract["option_symbol"]),ask,qty,score)
    def apply_entry(self,d,trade_id,opened_at,bid):self.position=Position(trade_id,str(d.contract_symbol),str(d.side),d.contracts,float(d.price),opened_at,bid)
    def apply_exit(self):self.position=None
