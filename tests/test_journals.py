from datetime import date,timedelta
from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.discord.journals import JournalService
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker
ROOT=Path(__file__).resolve().parents[1]
def test_journal_contains_lifecycle_and_strategy(tmp_path):
    cfg=AppConfig.load(ROOT); db=Database(tmp_path/'j.db'); db.initialize(); db.register_strategies(cfg.strategies)
    e=(date.today()+timedelta(days=14)).isoformat(); contract=OptionContract('C','X',e,100,'call',.7,.8,100,500,.4)
    d=StrategyRegistry(cfg.strategies).get('regular-call').evaluate('s','X',100,Regime.BULLISH_CONTROLLED,[contract],80)
    db.execute("INSERT INTO scan_cycles VALUES ('s','manual','test','COMPLETED','now','now','[]','{}','[]')")
    db.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(d.candidate_id,'s',d.strategy_id,d.strategy_version,d.strategy_hash,d.preset,'X','call','long-option','BULLISH_CONTROLLED','ELIGIBLE',80,80,d.total_debit,0,d.maximum_risk,__import__('json').dumps(d.configuration_snapshot),'now'))
    db.execute("INSERT INTO candidate_legs(candidate_id,contract_symbol,side,quantity,details_json) VALUES (?,?,?,?,?)",(d.candidate_id,'C','buy',1,__import__('json').dumps(contract.__dict__)))
    p=PaperBroker(db).open_candidate(d.candidate_id); text='\n'.join(JournalService(db).render(p.position_id)); assert 'regular-call' in text and 'Lifecycle' in text and 'Maximum risk' in text
