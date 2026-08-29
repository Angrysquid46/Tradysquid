from datetime import datetime
from surge_backtest import StrategyConfig,_signal,_contract,_reactive_exit,replay
from surge_optimizer import metrics,selection_score
def bars(values):return [{"close":x,"high":x+.05,"low":x-.05} for x in values]
def test_impulse_and_chop_are_separated():
    side,score,state=_signal(bars([100+i*.12 for i in range(20)]));assert side=="call" and state=="IMPULSE"
    side,_,state=_signal(bars([100+(-1)**i*.1 for i in range(20)]));assert side is None and state=="CHOP"
def test_contract_requires_observed_executable_quote():
    good={"data_class":"VERIFIED_REAL","side":"call","bid":1.,"ask":1.05,"delta":.5,"option_symbol":"x"}
    assert _contract({"contracts":[good]},"call",1000)==good
    assert _contract({"contracts":[{**good,"ask":2.,"bid":1.}]},"call",1000) is None
def test_reactive_exit_rides_peak_then_protects_profit_and_cuts_failure():
    p={"ask":1.,"peak_bid":.95}
    assert _reactive_exit(p,1.30,1,False,False) is None
    assert _reactive_exit(p,1.16,2,False,False)=="PROFIT_TRAIL"
    assert _reactive_exit({"ask":1.,"peak_bid":.95},.77,.5,False,False)=="FAST_FAILURE_STOP"
def test_strategy_config_changes_causal_thresholds():
    sample=bars([100+i*.06 for i in range(20)])
    assert _signal(sample,StrategyConfig(score_floor=.2))[0]=="call"
    assert _signal(sample,StrategyConfig(score_floor=.99))[0] is None
def test_selection_requires_chronological_activity():
    active={"pnl":10,"trades":4,"expectancy":2.5,"max_drawdown":5}
    idle={"pnl":100,"trades":0,"expectancy":0,"max_drawdown":0}
    assert selection_score(active,{**active,"trades":1})>-1e9
    assert selection_score(idle,active)==-1e9
def test_replay_liquidates_at_last_observed_bid():
    config=StrategyConfig(score_floor=.2,efficiency_floor=.2,max_hold=999)
    bs=bars([100+i*.12 for i in range(20)])
    for i,x in enumerate(bs):x["bar_timestamp"]=i
    contract={"data_class":"VERIFIED_REAL","side":"call","bid":1.,"ask":1.05,"delta":.5,"option_symbol":"x"}
    snap=[(datetime(2026,8,24,10),bs,{"contracts":[contract],"_by_symbol":{"x":contract}})]
    result=replay(snap,datetime(2026,8,24).date(),datetime(2026,8,24).date(),config=config)
    assert result["trades"][0]["reason"]=="END_OF_SESSION"
