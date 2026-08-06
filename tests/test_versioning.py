from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.data.database import Database
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.strategies.versioning import StrategyVersionService
ROOT=Path(__file__).resolve().parents[1]

def service(tmp_path):
    config=AppConfig.load(ROOT); db=Database(tmp_path/'v.db'); db.initialize(); db.register_strategies(config.strategies); registry=StrategyRegistry(config.strategies); return db,registry,StrategyVersionService(db,registry)

def test_owner_setting_creates_new_version(tmp_path):
    db,registry,versions=service(tmp_path); proposed=versions.propose('regular-call','management.profit_target_pct',.25,'test'); result=versions.activate('regular-call',proposed,'test')
    assert result.previous_version=='1.0.0' and result.new_version=='1.0.1'; assert registry.get('regular-call').config['management']['profit_target_pct']==.25
    assert len(db.query("SELECT * FROM strategy_acknowledgements WHERE strategy_id='regular-call'"))==3

def test_unknown_setting_rejected(tmp_path):
    _,_,versions=service(tmp_path)
    try: versions.propose('regular-call','management.nope',1,'bad')
    except ValueError as exc: assert 'Unknown' in str(exc)
    else: raise AssertionError('Expected ValueError')

def test_rollback_preserves_history(tmp_path):
    db,registry,versions=service(tmp_path); p=versions.propose('regular-call','management.profit_target_pct',.25,'test'); versions.activate('regular-call',p,'test'); result=versions.rollback('regular-call','1.0.0')
    assert result.new_version=='1.0.2'; assert len(versions.history('regular-call'))==3
