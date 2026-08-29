from datetime import datetime
from surge_backtest import _signal,_contract,_reactive_exit
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
