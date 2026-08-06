from datetime import date,timedelta
from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import CandidateStatus,Regime
from tradysquid.core.models import OptionContract
from tradysquid.strategies.registry import StrategyRegistry
ROOT=Path(__file__).resolve().parents[1]
def contracts(days):
    e=(date.today()+timedelta(days=days)).isoformat()
    return [OptionContract('C100','X',e,100,'call',.70,.80,100,500,.20),OptionContract('C101','X',e,101,'call',.20,.25,100,500,.10),OptionContract('P100','X',e,100,'put',.70,.80,100,500,-.20),OptionContract('P99','X',e,99,'put',.20,.25,100,500,-.10)]
def test_each_required_strategy_has_a_valid_path():
    registry=StrategyRegistry(AppConfig.load(ROOT).strategies)
    cases=[('regular-call',Regime.BULLISH_CONTROLLED,14),('regular-put',Regime.BEARISH_CONTROLLED,14),('swing-call',Regime.BULLISH_CONTROLLED,30),('swing-put',Regime.BEARISH_CONTROLLED,30),('bull-put-spread',Regime.BULLISH_CONTROLLED,30),('bear-call-spread',Regime.BEARISH_CONTROLLED,30)]
    for sid,regime,days in cases:
        decision=registry.get(sid).evaluate('scan','X',100,regime,contracts(days),80)
        assert decision.status==CandidateStatus.ELIGIBLE,(sid,decision.rejection_reasons)
        assert decision.maximum_risk<=100
