from datetime import date,timedelta
from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.scanner.service import ScanService
from tradysquid.strategies.registry import StrategyRegistry
ROOT=Path(__file__).resolve().parents[1]
class Provider:
    def history(self,*a,**k): return [{'close':100+i*.5} for i in range(60)]
    def expirations(self,*a): return [(date.today()+timedelta(days=14)).isoformat()]
    def option_chain(self,*a): return [OptionContract('C','X',(date.today()+timedelta(days=14)).isoformat(),100,'call',.7,.8,100,500,.4),OptionContract('P100','X',(date.today()+timedelta(days=14)).isoformat(),100,'put',.6,.7,100,500,-.2),OptionContract('P99','X',(date.today()+timedelta(days=14)).isoformat(),99,'put',.2,.25,100,500,-.1),OptionContract('C101','X',(date.today()+timedelta(days=14)).isoformat(),101,'call',.2,.25,100,500,.1)]
def test_scan_persists_all_six_decisions(tmp_path):
    db=Database(tmp_path/'s.db'); db.initialize(); c=AppConfig.load(ROOT); db.register_strategies(c.strategies)
    result=ScanService(db,Provider(),StrategyRegistry(c.strategies)).scan_symbol('X'); assert len(result)==6; assert db.query('SELECT COUNT(*) n FROM candidates')[0]['n']==6; assert db.query('SELECT COUNT(*) n FROM candidate_rejections')[0]['n']>0
