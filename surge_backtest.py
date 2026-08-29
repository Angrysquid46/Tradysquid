"""Causal captured-data backtest for an aggressive directional impulse hunter."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import datetime,date
from pathlib import Path
from statistics import fmean
import json,duckdb
import backtest_lab

ROOT=Path(__file__).resolve().parent
@dataclass
class Trade:
    entered_at:str; exited_at:str; side:str; symbol:str; ask:float; bid:float
    contracts:int; pnl:float; reason:str; impulse_score:float

def _signal(bars):
    if len(bars)<20:return None,0.,"INSUFFICIENT"
    c=[float(x["close"]) for x in bars[-20:]]; h=[float(x["high"]) for x in bars[-20:]]; l=[float(x["low"]) for x in bars[-20:]]
    moves=[abs(c[i]-c[i-1]) for i in range(1,len(c))]; net=c[-1]-c[-6]; path=sum(abs(c[i]-c[i-1]) for i in range(len(c)-5,len(c))) or .01
    efficiency=abs(net)/path; recent=max(h[-5:])-min(l[-5:]); prior=max(h[-15:-5])-min(l[-15:-5]) or .01
    expansion=min(2.,recent/prior); score=min(1.,.58*efficiency+.28*min(expansion/1.5,1)+.14*min(abs(net)/.8,1))
    chop=efficiency<.48 or sum((c[i]-c[i-1])*(c[i-1]-c[i-2])<0 for i in range(2,len(c)))>=11
    if chop or score<.62:return None,score,"CHOP" if chop else "WEAK"
    return ("call" if net>0 else "put"),score,"IMPULSE"

def _contract(options,side,bankroll):
    rows=[]
    for x in options.get("contracts",[]):
        try:
            b,a,d=float(x["bid"]),float(x["ask"]),abs(float(x["delta"])); spread=(a-b)/a
            if x.get("data_class")=="VERIFIED_REAL" and x.get("side")==side and b>0 and a>=b and spread<=.18 and .35<=d<=.65 and a*100<=bankroll:rows.append(x)
        except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    return min(rows,key=lambda x:(abs(abs(float(x["delta"]))-.5),float(x["ask"]))) if rows else None

def _reactive_exit(position,bid,held,opposite,chop):
    position["peak_bid"]=max(position.get("peak_bid",bid),bid)
    change=bid/position["ask"]-1; peak=position["peak_bid"]/position["ask"]-1
    if change<=-.22:return "FAST_FAILURE_STOP"
    if peak>=.15 and bid<=position["peak_bid"]*.90:return "PROFIT_TRAIL"
    if held>=1.5 and (opposite or chop):return "IMPULSE_REVERSAL"
    if held>=12:return "MAX_HOLD"
    return None

def timestamps(start:date,end:date):
    glob=str(ROOT/"data"/"market"/"chain"/"SPY"/"**"/"*.parquet").replace("\\","/")
    q="select distinct captured_at from read_parquet(?,union_by_name=true) where cast(captured_at as date) between ? and ? order by captured_at"
    return [datetime.fromisoformat(x[0]) for x in duckdb.connect().execute(q,[glob,start.isoformat(),end.isoformat()]).fetchall()]

def run(start:date,end:date,bankroll=1000.):
    view=backtest_lab.MarketView("SPY"); position=None; trades=[]; consumed=None; stats={"evaluations":0,"chop_rejections":0,"weak_rejections":0,"duplicate_evidence_rejections":0,"entries":0}
    for now in timestamps(start,end):
        bars=view.bars_as_of(now,lookback_minutes=60); opts=view.options_as_of(now); stats["evaluations"]+=1
        side,score,state=_signal(bars)
        if position:
            quote=next((x for x in opts.get("contracts",[]) if x.get("option_symbol")==position["symbol"]),None)
            if not quote or quote.get("bid") is None:continue
            bid=float(quote["bid"]); held=(now-position["time"]).total_seconds()/60; opposite=side and side!=position["side"]
            reason=_reactive_exit(position,bid,held,bool(opposite),state=="CHOP")
            if reason:
                pnl=(bid-position["ask"])*position["qty"]*100; bankroll+=pnl
                trades.append(Trade(position["time"].isoformat(),now.isoformat(),position["side"],position["symbol"],position["ask"],bid,position["qty"],round(pnl,2),reason,position["score"]));position=None
            continue
        if state=="CHOP":stats["chop_rejections"]+=1;continue
        if not side:stats["weak_rejections"]+=1;continue
        evidence=(str(bars[-1].get("bar_timestamp") or bars[-1].get("bar_time")),side)
        if evidence==consumed:stats["duplicate_evidence_rejections"]+=1;continue
        contract=_contract(opts,side,bankroll)
        if not contract:continue
        ask=float(contract["ask"]); qty=max(1,int(bankroll*.35//(ask*100)));position={"time":now,"side":side,"symbol":contract["option_symbol"],"ask":ask,"peak_bid":float(contract["bid"]),"qty":qty,"score":score};consumed=evidence;stats["entries"]+=1
    result={"start":start.isoformat(),"end":end.isoformat(),"starting_bankroll":1000.,"ending_bankroll":round(bankroll,2),"pnl":round(bankroll-1000,2),"stats":stats,"trades":[asdict(x) for x in trades],"dataset_fingerprint":backtest_lab.dataset_fingerprint("SPY",start,end),"limitations":"Captured snapshots only; no interpolation. Open final position excluded until an observed exit bid exists."}
    return result

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--start",type=date.fromisoformat,required=True);p.add_argument("--end",type=date.fromisoformat,required=True);p.add_argument("--output",type=Path)
    a=p.parse_args();r=run(a.start,a.end);text=json.dumps(r,indent=2);print(text)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding="utf-8")
