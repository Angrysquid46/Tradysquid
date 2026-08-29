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

@dataclass(frozen=True)
class StrategyConfig:
    signal_window:int=5; efficiency_floor:float=.48; score_floor:float=.62
    expansion_weight:float=.28; allocation:float=.35; stop_loss:float=.22
    trail_activation:float=.15; trail_giveback:float=.10
    reversal_delay:float=1.5; max_hold:float=12.; max_spread:float=.18
    delta_low:float=.35; delta_high:float=.65

def _signal(bars,config=StrategyConfig()):
    if len(bars)<20:return None,0.,"INSUFFICIENT"
    c=[float(x["close"]) for x in bars[-20:]]; h=[float(x["high"]) for x in bars[-20:]]; l=[float(x["low"]) for x in bars[-20:]]
    w=config.signal_window; net=c[-1]-c[-w-1]; path=sum(abs(c[i]-c[i-1]) for i in range(len(c)-w,len(c))) or .01
    efficiency=abs(net)/path; recent=max(h[-w:])-min(l[-w:]); prior=max(h[-3*w:-w])-min(l[-3*w:-w]) or .01
    expansion=min(2.,recent/prior); ew=config.expansion_weight
    score=min(1.,(1-ew-.14)*efficiency+ew*min(expansion/1.5,1)+.14*min(abs(net)/.8,1))
    chop=efficiency<config.efficiency_floor or sum((c[i]-c[i-1])*(c[i-1]-c[i-2])<0 for i in range(2,len(c)))>=11
    if chop or score<config.score_floor:return None,score,"CHOP" if chop else "WEAK"
    return ("call" if net>0 else "put"),score,"IMPULSE"

def _contract(options,side,bankroll,config=StrategyConfig()):
    rows=[]
    for x in options.get("contracts",[]):
        try:
            b,a,d=float(x["bid"]),float(x["ask"]),abs(float(x["delta"])); spread=(a-b)/a
            if x.get("data_class")=="VERIFIED_REAL" and x.get("side")==side and b>0 and a>=b and spread<=config.max_spread and config.delta_low<=d<=config.delta_high and a*100<=bankroll:rows.append(x)
        except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    return min(rows,key=lambda x:(abs(abs(float(x["delta"]))-.5),float(x["ask"]))) if rows else None

def _reactive_exit(position,bid,held,opposite,chop,config=StrategyConfig()):
    position["peak_bid"]=max(position.get("peak_bid",bid),bid)
    change=bid/position["ask"]-1; peak=position["peak_bid"]/position["ask"]-1
    if change<=-config.stop_loss:return "FAST_FAILURE_STOP"
    if peak>=config.trail_activation and bid<=position["peak_bid"]*(1-config.trail_giveback):return "PROFIT_TRAIL"
    if held>=config.reversal_delay and (opposite or chop):return "IMPULSE_REVERSAL"
    if held>=config.max_hold:return "MAX_HOLD"
    return None

def timestamps(start:date,end:date):
    glob=str(ROOT/"data"/"market"/"chain"/"SPY"/"**"/"*.parquet").replace("\\","/")
    q="select distinct captured_at from read_parquet(?,union_by_name=true) where cast(captured_at as date) between ? and ? order by captured_at"
    return [datetime.fromisoformat(x[0]) for x in duckdb.connect().execute(q,[glob,start.isoformat(),end.isoformat()]).fetchall()]

def load_snapshots(start:date,end:date):
    """Batch-load exactly the same causal rows as MarketView, avoiding thousands of
    repeated Parquet scans during research sweeps."""
    chain_glob=str(ROOT/"data"/"market"/"chain"/"SPY"/"**"/"*.parquet").replace("\\","/")
    bars_glob=str(ROOT/"data"/"market"/"bars"/"SPY"/"**"/"*.parquet").replace("\\","/")
    con=duckdb.connect()
    def rows(query,params):
        cur=con.execute(query,params); names=[x[0] for x in cur.description]
        return [dict(zip(names,x)) for x in cur.fetchall()]
    chains=rows("select * from read_parquet(?,union_by_name=true) where cast(captured_at as date) between ? and ? order by captured_at",
                [chain_glob,start.isoformat(),end.isoformat()])
    bars=rows("select * from read_parquet(?,union_by_name=true) where cast(to_timestamp(bar_timestamp) as date) between ? and ? order by bar_timestamp",
              [bars_glob,start.isoformat(),end.isoformat()])
    grouped={}
    for contract in chains:grouped.setdefault(contract["captured_at"],[]).append(contract)
    prepared=[(int(x["bar_timestamp"]),datetime.fromisoformat(x["captured_at"]),x) for x in bars]
    snapshots=[]
    for stamp,contracts in grouped.items():
        now=datetime.fromisoformat(stamp); cutoff=int(now.timestamp()); earliest=cutoff-3600
        causal=[x for ts,captured,x in prepared if earliest<=ts<=cutoff and captured<=now]
        snapshots.append((now,causal,{"tier":"A","captured_at":stamp,"contracts":contracts,
                                      "_by_symbol":{x["option_symbol"]:x for x in contracts}}))
    return sorted(snapshots,key=lambda x:x[0])

def replay(snapshots,start:date,end:date,bankroll=1000.,config=StrategyConfig(),fill_penalty=0.):
    position=None; trades=[]; consumed=None; prior_day=None; last_bid=None; last_time=None
    stats={"evaluations":0,"chop_rejections":0,"weak_rejections":0,"duplicate_evidence_rejections":0,"entries":0}
    def close(at,bid,reason):
        nonlocal position,bankroll
        pnl=(bid-position["ask"])*position["qty"]*100; bankroll+=pnl
        trades.append(Trade(position["time"].isoformat(),at.isoformat(),position["side"],position["symbol"],position["ask"],bid,position["qty"],round(pnl,2),reason,position["score"]));position=None
    for now,bars,opts in snapshots:
        if position and prior_day is not None and now.date()!=prior_day and last_bid is not None:
            close(last_time,last_bid,"END_OF_SESSION")
        prior_day=now.date()
        stats["evaluations"]+=1
        side,score,state=_signal(bars,config)
        if position:
            quote=opts.get("_by_symbol",{}).get(position["symbol"])
            if quote is None:quote=next((x for x in opts.get("contracts",[]) if x.get("option_symbol")==position["symbol"]),None)
            if not quote or quote.get("bid") is None:continue
            bid=max(0.,float(quote["bid"])-fill_penalty); held=(now-position["time"]).total_seconds()/60; opposite=side and side!=position["side"]
            last_bid,last_time=bid,now
            reason=_reactive_exit(position,bid,held,bool(opposite),state=="CHOP",config)
            if reason:
                close(now,bid,reason)
            continue
        if state=="CHOP":stats["chop_rejections"]+=1;continue
        if not side:stats["weak_rejections"]+=1;continue
        evidence=(str(bars[-1].get("bar_timestamp") or bars[-1].get("bar_time")),side)
        if evidence==consumed:stats["duplicate_evidence_rejections"]+=1;continue
        contract=_contract(opts,side,bankroll,config)
        if not contract:continue
        ask=float(contract["ask"])+fill_penalty; qty=int(bankroll*config.allocation//(ask*100))
        if qty<1:continue
        last_bid=max(0.,float(contract["bid"])-fill_penalty);last_time=now
        position={"time":now,"side":side,"symbol":contract["option_symbol"],"ask":ask,"peak_bid":last_bid,"qty":qty,"score":score};consumed=evidence;stats["entries"]+=1
    if position and last_bid is not None:close(last_time,last_bid,"END_OF_SESSION")
    result={"start":start.isoformat(),"end":end.isoformat(),"starting_bankroll":1000.,"ending_bankroll":round(bankroll,2),"pnl":round(bankroll-1000,2),"stats":stats,"trades":[asdict(x) for x in trades],"config":asdict(config),"dataset_fingerprint":backtest_lab.dataset_fingerprint("SPY",start,end),"limitations":"Captured snapshots only; no interpolation. Session liquidation uses the final actually observed contract bid."}
    return result

def run(start:date,end:date,bankroll=1000.,config=StrategyConfig(),fill_penalty=0.):
    return replay(load_snapshots(start,end),start,end,bankroll,config,fill_penalty)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--start",type=date.fromisoformat,required=True);p.add_argument("--end",type=date.fromisoformat,required=True);p.add_argument("--output",type=Path)
    a=p.parse_args();r=run(a.start,a.end);text=json.dumps(r,indent=2);print(text)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding="utf-8")
