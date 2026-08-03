from datetime import date,timedelta
from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import CandidateStatus,Regime
from tradysquid.core.models import OptionContract
from tradysquid.strategies.registry import StrategyRegistry
ROOT=Path(__file__).resolve().parents[1]
def chain():
    e=(date.today()+timedelta(days=14)).isoformat()
    return [OptionContract('CALL','X',e,100,'call',.70,.80,100,500,.4),OptionContract('PUT100','X',e,100,'put',.60,.70,100,500,-.2),OptionContract('PUT99','X',e,99,'put',.20,.25,100,500,-.1),OptionContract('CALL101','X',e,101,'call',.20,.25,100,500,.1)]
def test_registry_and_acknowledgements():
    c=AppConfig.load(ROOT); r=StrategyRegistry(c.strategies); assert len(r.all())==6; assert len(r.acknowledgements('scanner'))==6
def test_regular_call_qualifies():
    c=AppConfig.load(ROOT); s=StrategyRegistry(c.strategies).get('regular-call'); d=s.evaluate('scan','X',100,Regime.BULLISH_CONTROLLED,chain(),80); assert d.status==CandidateStatus.ELIGIBLE
def test_wrong_regime_rejects():
    c=AppConfig.load(ROOT); s=StrategyRegistry(c.strategies).get('regular-call'); d=s.evaluate('scan','X',100,Regime.BEARISH_CONTROLLED,chain(),80); assert d.status==CandidateStatus.REJECTED; assert d.rejection_reasons
