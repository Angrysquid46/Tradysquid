"""Deterministic chronological optimizer for the research-only SURGE engine."""
from __future__ import annotations
from dataclasses import asdict,replace
from datetime import date
from itertools import product
from pathlib import Path
from statistics import mean
import argparse,json
from surge_backtest import StrategyConfig,load_snapshots,replay

def metrics(result):
    trades=result["trades"]; pnls=[t["pnl"] for t in trades]
    wins=sum(x>0 for x in pnls); losses=sum(x<0 for x in pnls)
    gross_win=sum(x for x in pnls if x>0); gross_loss=-sum(x for x in pnls if x<0)
    equity=1000.; peak=1000.; drawdown=0.
    for x in pnls:
        equity+=x; peak=max(peak,equity); drawdown=max(drawdown,peak-equity)
    return {"pnl":result["pnl"],"trades":len(trades),"wins":wins,"losses":losses,
            "win_rate":round(wins/len(trades),4) if trades else 0.,
            "expectancy":round(mean(pnls),2) if pnls else 0.,
            "profit_factor":round(gross_win/gross_loss,3) if gross_loss else None,
            "max_drawdown":round(drawdown,2)}

def candidates():
    # 288 deterministic combinations across the material signal/risk/exit dimensions.
    for values in product((3,5,8),(.30,.42,.54),(.50,.62),(.20,.35),(.12,.20),(.08,.14),(4.,12.)):
        yield StrategyConfig(signal_window=values[0],efficiency_floor=values[1],score_floor=values[2],
            allocation=values[3],stop_loss=values[4],trail_activation=values[5],max_hold=values[6],
            reversal_delay=1.,trail_giveback=.10,delta_low=.35,delta_high=.70)

def selection_score(train,validation):
    # Require activity and reward agreement; punish drawdown and train/validation instability.
    if train["trades"]<4 or validation["trades"]<1:return -1e9
    return validation["pnl"]+.20*train["pnl"]-.35*(train["max_drawdown"]+validation["max_drawdown"])-.15*abs(train["expectancy"]-validation["expectancy"])

def optimize():
    train_range=(date(2026,8,24),date(2026,8,26)); validation_range=(date(2026,8,27),date(2026,8,27)); holdout_range=(date(2026,8,28),date(2026,8,28))
    train_data=load_snapshots(*train_range); validation_data=load_snapshots(*validation_range)
    ranked=[]
    for config in candidates():
        tr=metrics(replay(train_data,*train_range,config=config)); va=metrics(replay(validation_data,*validation_range,config=config))
        ranked.append((selection_score(tr,va),config,tr,va))
    ranked.sort(key=lambda x:(x[0],x[3]["pnl"],x[2]["pnl"]),reverse=True)
    # The holdout is loaded and evaluated only after ranking is frozen.
    holdout_data=load_snapshots(*holdout_range); winner=ranked[0]
    hold=metrics(replay(holdout_data,*holdout_range,config=winner[1]))
    stressed=metrics(replay(holdout_data,*holdout_range,config=winner[1],fill_penalty=.03))
    full_data=train_data+validation_data+holdout_data
    full=replay(full_data,date(2026,8,24),date(2026,8,28),config=winner[1]); full_metrics=metrics(full)
    baseline=metrics(replay(full_data,date(2026,8,24),date(2026,8,28),config=StrategyConfig()))
    # After the robust selection is frozen, disclose the hindsight full-period
    # winner separately; it is descriptive and can never become the selected candidate.
    hindsight=[]
    for _,config,tr,va in ranked:
        ho=metrics(replay(holdout_data,*holdout_range,config=config))
        hindsight.append((tr["pnl"]+va["pnl"]+ho["pnl"],config,tr,va,ho))
    raw=max(hindsight,key=lambda x:x[0])
    return {"method":{"candidate_count":len(ranked),"train":"2026-08-24..26","validation":"2026-08-27","sealed_holdout":"2026-08-28","selection":"validation-led stability/drawdown score"},
        "baseline":baseline,"selected":{"config":asdict(winner[1]),"train":winner[2],"validation":winner[3],"holdout":hold,"holdout_three_cent_adverse_fill":stressed,"full":full_metrics,"trades":full["trades"]},
        "highest_hindsight_raw":{"partition_pnl_sum":raw[0],"config":asdict(raw[1]),"train":raw[2],"validation":raw[3],"holdout":raw[4],"warning":"Selected after seeing holdout; descriptive only and overfit by construction."},
        "top_candidates":[{"score":round(x[0],3),"config":asdict(x[1]),"train":x[2],"validation":x[3]} for x in ranked[:10]],
        "dataset_fingerprint":full["dataset_fingerprint"],"verdict":"ROBUST_SURGE_CANDIDATE_FOUND" if hold["pnl"]>0 and stressed["pnl"]>0 else "INSUFFICIENT_EVIDENCE_FOR_ROBUST_CANDIDATE"}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path);a=p.parse_args(); result=optimize(); text=json.dumps(result,indent=2);print(text)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding="utf-8")
