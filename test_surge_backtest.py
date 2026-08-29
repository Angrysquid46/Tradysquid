from datetime import datetime
from surge_backtest import _signal,_contract
def bars(values):return [{"close":x,"high":x+.05,"low":x-.05} for x in values]
def test_impulse_and_chop_are_separated():
    side,score,state=_signal(bars([100+i*.12 for i in range(20)]));assert side=="call" and state=="IMPULSE"
    side,_,state=_signal(bars([100+(-1)**i*.1 for i in range(20)]));assert side is None and state=="CHOP"
def test_contract_requires_observed_executable_quote():
    good={"data_class":"VERIFIED_REAL","side":"call","bid":1.,"ask":1.05,"delta":.5,"option_symbol":"x"}
    assert _contract({"contracts":[good]},"call",1000)==good
    assert _contract({"contracts":[{**good,"ask":2.,"bid":1.}]},"call",1000) is None
