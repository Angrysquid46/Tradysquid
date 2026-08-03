from pathlib import Path
from tradysquid.core.config import AppConfig
from tradysquid.data.database import Database
from tradysquid.strategies.registry import StrategyRegistry
root=Path(__file__).resolve().parents[1]
config=AppConfig.load(root); db=Database(root/config.defaults['database']['path']); db.initialize(); db.register_strategies(config.strategies)
assert db.integrity_check()=='ok'; assert db.journal_mode()=='wal'; assert len(StrategyRegistry(config.strategies).all())==6
print('PASS')
