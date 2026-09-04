"""RIPTIDE intelligent-degenerate multi-family SPY 0DTE paper engine."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any, Literal

BOT_ID="RIPTIDE_SPY"; STARTING_BANKROLL=1000.; CONTRACT_MULTIPLIER=100
FAMILIES=("MOMENTUM_CHASE","FAILED_MOVE_FADE","VOLATILITY_EXPANSION","COMPRESSION_RELEASE","REVERSAL_ATTEMPT","TREND_CONTINUATION","OVEREXTENSION_SNAPBACK","VWAP_RECLAIM_REJECTION","RANGE_EDGE_SPECULATION","MICROSTRUCTURE_DISLOCATION","LATE_CONFIRMATION_CHASE","CONTROLLED_EXPLORATION")

@dataclass(frozen=True)
class Parameters:
    min_bars:int=18; base_action_floor:float=.52; minimum_action_floor:float=.16
    pressure_floor_reduction:float=.34; max_spread_pct:float=.20; min_volume:int=5
    min_open_interest:int=25; min_delta:float=.22; max_delta:float=.68
    base_risk_fraction:float=.38; maximum_risk_fraction:float=.78
    take_profit_pct:float=.28; stop_loss_pct:float=.18; max_hold_minutes:int=10
    exploration_rate:float=.22; family_bias:tuple[tuple[str,float],...]=()
    context_bias:tuple[tuple[str,float],...]=(); policy_version:int=1
@dataclass(frozen=True)
class Position:
    trade_id:str; contract_symbol:str; side:Literal["call","put"]; contracts:int
    entry_price:float; opened_at:datetime; setup:str="RECOVERED"; entry_iv:float|None=None
    entry_state:str="UNKNOWN"; policy_version:int=1
@dataclass(frozen=True)
class Candidate:
    family:str; style:str; side:Literal["call","put"]; score:float
    opportunity:float; urgency:float; asymmetry:float; excitement:float
    uncertainty:float; reason:str
@dataclass(frozen=True)
class Decision:
    action:Literal["NO_ACTION","ENTER","EXIT","BUST"]; reason:str
    contract_symbol:str|None=None; side:str|None=None; contracts:int=0
    price:float|None=None; setup:str|None=None; action_pressure:float=0.
    action_floor:float=1.; market_state:str|None=None
    candidates:tuple[Candidate,...]=field(default_factory=tuple)
@dataclass(frozen=True)
class Features:
    direction:float; acceleration:float; volatility:float; expansion:float
    compression:float; reversal:float; participation:float; location:float
    disagreement:float; instability:float; vwap_gap:float
    range_position:float; state:str
def clamp(v:float,lo:float=0.,hi:float=1.)->float:return min(hi,max(lo,v))

class Riptide:
    def __init__(self,parameters:Parameters|None=None):
        self.parameters=parameters or Parameters(); self.position=None; self.generation=1
    def decide(self,*,as_of:datetime,bankroll:float,market:dict[str,Any],options:dict[str,Any],bars:list[dict[str,Any]])->Decision:
        if self.position:return self._exit(as_of,options,bars)
        if bankroll<=0:return Decision("BUST","generation bankroll exhausted")
        if market.get("tier")!="A" or options.get("tier")!="A":return Decision("NO_ACTION","Tier A point-in-time evidence required")
        if len(bars)<self.parameters.min_bars:return Decision("NO_ACTION","insufficient completed bars")
        try:f=self._features(bars)
        except (KeyError,TypeError,ValueError,ZeroDivisionError):return Decision("NO_ACTION","completed market observations malformed")
        pressure=self._pressure(as_of); candidates=tuple(sorted(self._candidates(f,pressure),key=lambda x:x.score,reverse=True))
        floor=max(self.parameters.minimum_action_floor,self.parameters.base_action_floor-pressure*self.parameters.pressure_floor_reduction)
        pool=[x for x in candidates if x.score>=floor]
        if not pool:return Decision("NO_ACTION","every opportunity below documented actionability floor",action_pressure=pressure,action_floor=floor,market_state=f.state,candidates=candidates)
        chosen=self._explore(pool,as_of,pressure)
        eligible=[x for x in options.get("contracts",[]) if self._eligible(x,chosen.side,as_of)]
        if not eligible:return Decision("NO_ACTION","no legitimate same-day contract qualifies",action_pressure=pressure,action_floor=floor,market_state=f.state,candidates=candidates)
        affordable=[x for x in eligible if float(x["ask"])*100<=bankroll]
        if not affordable:return Decision("BUST","entire bankroll cannot afford a legitimate qualifying contract",action_pressure=pressure,action_floor=floor,market_state=f.state,candidates=candidates)
        target=.38+.12*chosen.opportunity
        contract=min(affordable,key=lambda x:(abs(abs(float(x["delta"]))-target),(float(x["ask"])-float(x["bid"]))/float(x["ask"]),float(x["ask"])))
        ask=float(contract["ask"]); ruin=clamp(bankroll/1000,.20,1.); wager=min(self.parameters.maximum_risk_fraction,self.parameters.base_risk_fraction+.12*pressure+.12*chosen.score)*ruin
        qty=max(1,int(bankroll*wager//(ask*100)))
        return Decision("ENTER",chosen.reason,str(contract["option_symbol"]),chosen.side,qty,ask,chosen.family,pressure,floor,f.state,candidates)
    def _features(self,bars:list[dict[str,Any]])->Features:
        rows=bars[-60:]; c=[float(x["close"]) for x in rows]; h=[float(x["high"]) for x in rows]; l=[float(x["low"]) for x in rows]; v=[max(0.,float(x.get("volume") or 0)) for x in rows]
        r=[c[i]/c[i-1]-1 for i in range(1,len(c)) if c[i-1]]; vol=pstdev(r[-20:]) if len(r)>1 else 0.; short=c[-1]/c[-4]-1; med=c[-1]/c[-10]-1; long=c[-1]/c[0]-1
        recent=max(h[-8:])-min(l[-8:]); prior=max(h[-20:-8])-min(l[-20:-8]); av=fmean(v[-20:-1]) if any(v[-20:-1]) else 1.; rv=v[-1]/av; vw=sum(px*max(vo,1) for px,vo in zip(c,v))/sum(max(vo,1) for vo in v); pos=(c[-1]-min(l[-20:]))/max(max(h[-20:])-min(l[-20:]),.01)
        draw=.5*short+.32*med+.18*long; direction=clamp(.5+draw/max(vol*4,.001))*2-1; prev=c[-4]/c[-7]-1; accel=clamp(.5+(short-prev)/max(vol*3,.001))*2-1
        volatility=clamp(vol/.0025); expansion=clamp(recent/max(prior,.01)-.65); compression=clamp(1.2-recent/max(prior,.01)); reversal=clamp(abs(short-med)/max(vol*4,.001)); part=clamp(rv/1.6); loc=clamp(abs(pos-.5)*2); disagree=clamp(abs(short-long)/max(vol*5,.001)); unstable=clamp((pstdev(r[-6:]) if len(r)>=6 else vol)/max(vol,.0001)-.55); gap=(c[-1]/vw-1)/max(vol,.0002)
        state="CHAOTIC_EXPANSION" if volatility>.7 and expansion>.55 else "COILED" if compression>.6 else "RUNNING" if abs(direction)>.55 and part>.45 else "CONFLICTED" if reversal>.55 or disagree>.55 else "RANGE_EDGE" if loc>.65 else "DRIFTING"
        return Features(direction,accel,volatility,expansion,compression,reversal,part,loc,disagree,unstable,gap,pos,state)
    def _make(self,fam,style,side,raw,p,u,reason,state):
        learned=dict(self.parameters.family_bias).get(fam,0)+dict(self.parameters.context_bias).get(f"{state}|{fam}",0)
        opp=clamp(raw+learned); urgency=clamp(.35*p+.65*opp); asym=clamp(.35+.55*opp); excite=clamp(.25+.4*p+.35*opp); score=clamp(.42*opp+.18*urgency+.14*asym+.16*excite-.10*u)
        return Candidate(fam,style,side,score,opp,urgency,asym,excite,u,reason)
    def _candidates(self,f:Features,p:float)->list[Candidate]:
        t="call" if f.direction>=0 else "put"; fade="put" if t=="call" else "call"; edge="put" if f.range_position>.58 else "call"; vw="call" if f.vwap_gap>=0 else "put"
        s=[("MOMENTUM_CHASE","CHASER",t,.34+.36*abs(f.direction)+.2*f.participation,.22,"momentum worth chasing"),("FAILED_MOVE_FADE","CONTRARIAN",fade,.25+.3*f.reversal+.27*f.disagreement+.18*f.location,.36,"failed move offers a fade"),("VOLATILITY_EXPANSION","VOLATILITY_JUNKIE",t,.28+.38*f.expansion+.22*f.volatility+.12*f.participation,.3,"volatility is expanding"),("COMPRESSION_RELEASE","VOLATILITY_JUNKIE",t,.28+.36*f.compression+.22*abs(f.acceleration)+.14*f.participation,.34,"stored pressure is releasing"),("REVERSAL_ATTEMPT","CONTRARIAN",fade,.24+.36*f.reversal+.24*f.location+.16*f.instability,.44,"early reversal gamble"),("TREND_CONTINUATION","CHASER",t,.32+.38*abs(f.direction)+.18*(1-f.disagreement)+.12*f.participation,.24,"persistent direction"),("OVEREXTENSION_SNAPBACK","CONTRARIAN",edge,.24+.36*f.location+.22*f.volatility+.18*f.disagreement,.42,"overextension snapback"),("VWAP_RECLAIM_REJECTION","CHASER",vw,.27+.34*clamp(abs(f.vwap_gap)/2)+.22*abs(f.acceleration)+.17*f.participation,.33,"VWAP interaction"),("RANGE_EDGE_SPECULATION","CONTRARIAN",edge,.3+.43*f.location+.17*(1-f.expansion)+.1*p,.37,"range-edge gamble"),("MICROSTRUCTURE_DISLOCATION","VOLATILITY_JUNKIE",t,.23+.32*f.instability+.27*f.participation+.18*f.expansion,.48,"short-lived dislocation"),("LATE_CONFIRMATION_CHASE","CHASER",t,.25+.27*abs(f.direction)+.23*max(0,f.acceleration*f.direction)+.25*p,.39,"late chase"),("CONTROLLED_EXPLORATION","LOTTERY_EXPLORER",t if abs(f.direction)>.12 else edge,.18+.18*f.volatility+.16*f.participation+.3*p+.18*f.location,.58,"controlled weak-edge exploration")]
        return [self._make(*x[:4],p,x[4],x[5],f.state) for x in s]
    def _explore(self,pool,as_of,p):
        roll=((as_of.toordinal()*1440+as_of.hour*60+as_of.minute)*2654435761%1000)/1000; rate=min(.40,self.parameters.exploration_rate+p*.18)
        return pool[int(roll*1000)%min(4,len(pool))] if len(pool)>1 and roll<rate else pool[0]
    def _pressure(self,t):return clamp(max(0,t.hour*60+t.minute-515)/210)
    def _eligible(self,x,side,t):
        try:
            b,a,d=float(x["bid"]),float(x["ask"]),abs(float(x["delta"])); fields=("bid","ask","delta","gamma","theta","iv","volume","open_interest")
            return x.get("data_class")=="VERIFIED_REAL" and all(x.get(k) is not None for k in fields) and x.get("side")==side and x.get("expiration")==t.date().isoformat() and b>0 and a>=b and (a-b)/a<=self.parameters.max_spread_pct and int(x.get("volume") or 0)>=self.parameters.min_volume and int(x.get("open_interest") or 0)>=self.parameters.min_open_interest and self.parameters.min_delta<=d<=self.parameters.max_delta
        except (KeyError,TypeError,ValueError,ZeroDivisionError):return False
    def _exit(self,t,options,bars):
        x=next((x for x in options.get("contracts",[]) if str(x.get("option_symbol"))==self.position.contract_symbol),None)
        if options.get("tier")!="A" or not x:return Decision("NO_ACTION","current observed contract bid unavailable")
        try:b=float(x["bid"])
        except (KeyError,TypeError,ValueError):return Decision("NO_ACTION","invalid observed exit evidence")
        if b<0:return Decision("NO_ACTION","invalid observed exit evidence")
        ch=b/self.position.entry_price-1; held=(t-self.position.opened_at).total_seconds()/60
        state=None; failed=False
        try:
            f=self._features(bars); state=f.state
            failed=(self.position.side=="call" and f.direction<-.18) or (self.position.side=="put" and f.direction>.18)
        except (IndexError,KeyError,TypeError,ValueError,ZeroDivisionError):
            pass
        reason="end-of-session liquidation" if t.hour*60+t.minute>=900 else "aggressive profit capture" if ch>=self.parameters.take_profit_pct else "loss intolerance stop" if ch<=-self.parameters.stop_loss_pct else "directional reversal invalidation" if failed else "rapid-turnover maximum holding time" if held>=self.parameters.max_hold_minutes else None
        return Decision("EXIT",reason,self.position.contract_symbol,self.position.side,self.position.contracts,b,self.position.setup,market_state=state) if reason else Decision("NO_ACTION","position remains inside fast exit envelope",market_state=state)
    def apply_entry(self,d,*,trade_id,opened_at,entry_iv=None):
        if d.action!="ENTER" or self.position or d.price is None or not d.setup:raise ValueError("invalid or overlapping entry")
        self.position=Position(trade_id,str(d.contract_symbol),d.side,d.contracts,d.price,opened_at,d.setup,entry_iv,d.market_state or "UNKNOWN",self.parameters.policy_version)
    def apply_exit(self,d):
        if d.action!="EXIT" or not self.position:raise ValueError("no valid position to close")
        old,self.position=self.position,None; return old
    def evolve(self,outcomes):
        if len(outcomes)<8:return self.parameters
        vals=[float(getattr(x,"return_pct",x if isinstance(x,(int,float)) else 0)) for x in outcomes[-32:]]; mean=fmean(vals); win=sum(x>0 for x in vals)/len(vals)
        self.parameters=replace(self.parameters,base_risk_fraction=max(.12,min(.48,self.parameters.base_risk_fraction+(-.04 if mean<-.04 else .02 if mean>.04 else 0))),exploration_rate=max(.05,min(.22,self.parameters.exploration_rate+(-.03 if win<.42 else .01 if win>.58 and mean>0 else 0))))
        return self.parameters
    def reset_generation_after_bust(self):
        if self.position:raise ValueError("cannot bust-reset with an open position")
        self.generation+=1
