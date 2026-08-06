import pytest
from tradysquid.core.models import OptionContract
from tradysquid.trading.fills import long_entry,long_exit,FillError
from tradysquid.trading.risk import long_option_risk,credit_spread_risk
def c(bid=.8,ask=.9,multiplier=100): return OptionContract('X','X','2030-01-01',100,'call',bid,ask,100,500,.4,multiplier=multiplier)
def test_conservative_fills(): assert long_entry(c(),.01).price==.91 and long_exit(c(),.01).price==.79
def test_long_risk_cap(): assert long_option_risk(.99,100,0,100).eligible and not long_option_risk(1.01,100,0,100).eligible
def test_credit_spread_max_risk():
    r=credit_spread_risk(.80,.30,100,99,100,0,100); assert r.total_credit==50 and r.maximum_risk==50 and r.eligible
    assert not credit_spread_risk(.20,.10,100,98,100,0,100).eligible
def test_invalid_market():
    with pytest.raises(FillError): long_entry(c(bid=1,ask=.5))
