from datetime import datetime,timedelta
import scoreboard
from bots.surge import runtime as surge_runtime
from bots.surge.engine import Surge
from bots.surge.runtime import SurgeRuntime
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

def test_three_minute_bounce_cannot_buy_call_against_unconfirmed_downtrend():
    values=[510-index*.12 for index in range(55)]+[503.5,503.56,503.63,503.70]
    observed=[{"close":x,"high":x+.04,"low":x-.04,"volume":1000} for x in values]
    contract={"data_class":"VERIFIED_REAL","side":"call","bid":.95,"ask":1.,"delta":.5,"option_symbol":"x"}
    decision=Surge().decide(datetime.now(),1000,{"tier":"A"},{"tier":"A","contracts":[contract]},observed)
    assert decision.action=="NO_ACTION"
    assert "conflicts with verified direction" in decision.reason

def test_valid_signal_uses_one_contract_when_full_bankroll_can_afford_it():
    contract={"data_class":"VERIFIED_REAL","side":"call","bid":3.90,"ask":4.00,"delta":.5,"option_symbol":"x"}
    decision=Surge().decide(datetime.now(),1000,{"tier":"A"},{"tier":"A","contracts":[contract]},bars())
    assert decision.action=="ENTER"
    assert decision.contracts==1

def test_runtime_records_bust_and_starts_fresh_generation(tmp_path,monkeypatch):
    class View:
        def market_as_of(self,_):return {"tier":"A"}
        def bars_as_of(self,_,lookback_minutes=180):return bars()
        def options_as_of(self,_):return {"tier":"A","contracts":[{"data_class":"VERIFIED_REAL","side":"call","bid":11.90,"ask":12.00,"delta":.5,"option_symbol":"x"}]}
    monkeypatch.setattr(scoreboard,"DB_PATH",tmp_path/"scoreboard.db")
    monkeypatch.setattr(surge_runtime,"POSITION_STATE",tmp_path/"position-state.json")
    db=scoreboard.connect_db()
    result=SurgeRuntime(market_view=View(),telemetry_path=tmp_path/"decisions.jsonl").evaluate(datetime.now(),db)
    assert result.action=="BUST"
    assert scoreboard.current_generation(db,"SURGE")==2
    assert scoreboard.current_bankroll(db,"SURGE")==1000
    assert scoreboard.bust_count(db,"SURGE")==1
