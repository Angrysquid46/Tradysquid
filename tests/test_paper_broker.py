from datetime import date,timedelta
from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker
ROOT=Path(__file__).resolve().parents[1]
def test_long_position_lifecycle(tmp_path):
    c=AppConfig.load(ROOT); s=StrategyRegistry(c.strategies).get('regular-call'); contract=OptionContract('C','X',(date.today()+timedelta(days=14)).isoformat(),100,'call',.7,.8,100,500,.4)
    d=s.evaluate('scan','X',100,Regime.BULLISH_CONTROLLED,[contract],80); db=Database(tmp_path/'p.db'); db.initialize(); db.register_strategies(c.strategies); b=PaperBroker(db); p=b.open(d)
    mark=b.mark(p.position_id,{'C':(1.0,1.1)}); assert mark['mfe_pct']>0
    closed=b.close(p.position_id,{'C':(1.0,1.1)},'test'); assert closed['state'].startswith('CLOSED_')
