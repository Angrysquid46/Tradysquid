from datetime import datetime,timedelta
import pytest
from bots.riptide.engine import FAMILIES,Riptide
from bots.riptide.evolution import EvolutionLoop,Outcome
NOW=datetime(2026,8,28,10,0)
def bars(kind="trend",n=40):
    out=[]
    for i in range(n):
        if kind=="trend": close=500+i*.12
        elif kind=="reverse": close=500+i*.15 if i<n-5 else 506-(i-(n-5))*.5
        elif kind=="range": close=500+(i%8-4)*.12
        elif kind=="volatile": close=500+((-1)**i)*(i%5)*.3
        else: close=500+i*.015
        out.append({"close":close,"high":close+.08,"low":close-.08,"volume":900+(i%6)*140})
    return out
def option(side="call",bid=1.,ask=1.05):
    return {"option_symbol":"SPY260828"+("C" if side=="call" else "P")+"00500000","side":side,"expiration":NOW.date().isoformat(),"bid":bid,"ask":ask,"delta":.45 if side=="call" else -.45,"gamma":.01,"theta":-.05,"iv":.25,"data_class":"VERIFIED_REAL","volume":50,"open_interest":200}
def decide(kind="trend",at=NOW):
    e=Riptide(); return e.decide(as_of=at,bankroll=1000,market={"tier":"A"},options={"tier":"A","contracts":[option(),option("put")]},bars=bars(kind))
def test_all_required_families_compete_and_action_pressure_changes_floor():
    early=decide("range",NOW.replace(hour=8,minute=36)); late=decide("range",NOW.replace(hour=13))
    assert {c.family for c in early.candidates}==set(FAMILIES)
    assert late.action_pressure>early.action_pressure and late.action_floor<early.action_floor
def test_multiple_regimes_are_actionable_without_one_breakout_pattern():
    decisions=[decide(x) for x in ("trend","reverse","range","volatile","quiet")]
    assert sum(d.action=="ENTER" for d in decisions)>=4
    assert len({d.setup for d in decisions if d.action=="ENTER"})>=3
def test_not_timer_forced_but_weak_edge_exploration_becomes_actionable():
    e=Riptide(); bad=e.decide(as_of=NOW,bankroll=1000,market={"tier":"C"},options={"tier":"A","contracts":[option()]},bars=bars("quiet"))
    assert bad.action=="NO_ACTION"
    late=decide("quiet",NOW.replace(hour=13,minute=30)); assert late.action=="ENTER"
def test_real_ask_entry_fast_bid_exit_and_one_position():
    e=Riptide(); d=decide("trend"); assert d.price==1.05 and d.contracts>=1
    e.apply_entry(d,trade_id="r",opened_at=NOW,entry_iv=.25)
    x=e.decide(as_of=NOW+timedelta(minutes=1),bankroll=600,market={"tier":"A"},options={"tier":"A","contracts":[option(d.side,bid=.80,ask=.85)]},bars=bars("reverse"))
    assert x.action=="EXIT" and x.price==.80

def test_end_of_session_exit_does_not_require_analytics_bars():
    e=Riptide(); d=decide("trend"); e.apply_entry(d,trade_id="r",opened_at=NOW,entry_iv=.25)
    x=e.decide(as_of=NOW.replace(hour=15),bankroll=600,market={"tier":"A"},options={"tier":"A","contracts":[option(d.side,bid=.70,ask=.75)]},bars=[])
    assert x.action=="EXIT" and x.price==.70 and x.reason=="end-of-session liquidation"
def test_contract_and_bankroll_safety_remain_absolute():
    e=Riptide(); wide=option(bid=.5,ask=1.05)
    d=e.decide(as_of=NOW,bankroll=1000,market={"tier":"A"},options={"tier":"A","contracts":[wide]},bars=bars())
    assert d.action=="NO_ACTION"
    expensive=option(bid=11,ask=12)
    d=e.decide(as_of=NOW,bankroll=1000,market={"tier":"A"},options={"tier":"A","contracts":[expensive,option("put",bid=11,ask=12)]},bars=bars())
    assert d.action=="BUST"
def test_evolution_is_bounded():
    e=Riptide(); assert e.evolve([-1.]*7).base_risk_fraction==pytest.approx(.38)
    p=e.evolve([-1.]*8); assert .28<=p.base_risk_fraction<=.52 and .14<=p.exploration_rate<=.4

def test_chronological_replay_is_active_varied_and_rapidly_redeploys():
    """Representative regimes must create intelligence-led turnover, not timer buys."""
    engine=Riptide(); entered=[]; entries=exits=eligible_flat=0
    regimes=("trend","range","volatile","reverse","quiet","trend","range")
    for minute in range(42):
        at=NOW+timedelta(minutes=minute)
        kind=regimes[minute//6]
        observed=bars(kind)
        contracts=[option(),option("put")]
        if engine.position:
            # A real observed bid move closes the official position; the next
            # completed minute is immediately eligible without a cooldown.
            side=engine.position.side
            contracts=[option(side,bid=1.38,ask=1.42)]
        else:
            eligible_flat+=1
        decision=engine.decide(as_of=at,bankroll=1000,market={"tier":"A"},
                               options={"tier":"A","contracts":contracts},bars=observed)
        if decision.action=="ENTER":
            entries+=1; entered.append(decision.setup)
            engine.apply_entry(decision,trade_id=f"replay-{minute}",opened_at=at,entry_iv=.25)
        elif decision.action=="EXIT":
            exits+=1; engine.apply_exit(decision)
    assert entries>=18 and exits>=17
    assert entries/eligible_flat>=.8
    assert len(set(entered))>=5
    assert set(entered).issubset(set(FAMILIES))

def test_family_learning_suppresses_loser_and_persists(tmp_path):
    loop=EvolutionLoop(tmp_path/"outcomes.jsonl",tmp_path/"learning.json")
    for i in range(8):
        loop.record(Outcome(str(i),1,-.12,"stop",f"2026-08-28T12:{i:02}:00","VWAP_RECLAIM_REJECTION"))
    first=Riptide(); state=loop.evaluate(first)
    assert dict(first.parameters.family_bias)["VWAP_RECLAIM_REJECTION"]<0
    restarted=Riptide(); loop.apply(restarted)
    assert restarted.parameters==first.parameters
    assert state["sample"]==8

def test_losing_policy_reduces_risk_and_exploration_instead_of_revenge_sampling(tmp_path):
    loop=EvolutionLoop(tmp_path/"outcomes.jsonl",tmp_path/"learning.json")
    for i in range(12):
        loop.record(Outcome(str(i),1,-.10,"stop",f"2026-08-28T12:{i:02}:00","FAILED_MOVE_FADE","CONFLICTED"))
    engine=Riptide(); state=loop.evaluate(engine)
    assert state["risk"]==pytest.approx(.12)
    assert state["exploration"]==pytest.approx(.05)
    assert state["family_bias"]["FAILED_MOVE_FADE"]<0
    assert state["context_bias"]["CONFLICTED|FAILED_MOVE_FADE"]<0
    assert state["policy_version"]>1

def test_isolated_outcome_ledger_cannot_write_live_promoted_state(tmp_path):
    loop=EvolutionLoop(tmp_path/"outcomes.jsonl")
    assert loop.state_path==tmp_path/"promoted-learning.json"
