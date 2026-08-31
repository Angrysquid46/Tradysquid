from datetime import datetime,timedelta
from bots.surge.engine import Surge
from bots.surge.preflight import INSTANCE_PORT
from bots.surge.scheduler import cycle_allowed
def bars(step=.2):return [{"close":100+i*step,"high":100+i*step+.05,"low":100+i*step-.05} for i in range(20)]
def test_exact_three_minute_signal_and_tier_a_entry():
    bot=Surge();side,score,state=bot.signal(bars());assert side=="call" and state=="IMPULSE"
    contract={"data_class":"VERIFIED_REAL","side":"call","bid":.95,"ask":1.,"delta":.5,"option_symbol":"x"}
    d=bot.decide(datetime.now(),1000,{"tier":"A"},{"tier":"A","contracts":[contract]},bars());assert d.action=="ENTER" and d.price==1. and d.contracts==3
def test_exit_uses_observed_bid_and_rides_winner():
    bot=Surge();now=datetime.now();contract={"data_class":"VERIFIED_REAL","side":"call","bid":1.,"ask":1.05,"delta":.5,"option_symbol":"x"};d=bot.decide(now,1000,{"tier":"A"},{"tier":"A","contracts":[contract]},bars());bot.apply_entry(d,"t",now,1.)
    quote={**contract,"bid":1.30};assert bot.decide(now+timedelta(minutes=1),1000,{"tier":"A"},{"tier":"A","contracts":[quote]},bars()).action=="NO_ACTION"
    quote["bid"]=1.16;out=bot.decide(now+timedelta(minutes=2),1000,{"tier":"A"},{"tier":"A","contracts":[quote]},bars());assert out.action=="EXIT" and out.price==1.16
def test_market_window():
    assert cycle_allowed(datetime(2026,8,28,10),False)

def test_instance_port_is_reserved_for_surge():
    assert INSTANCE_PORT == 8895
