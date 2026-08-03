from pathlib import Path
from tradysquid.core.config import AppConfig, stable_hash, redact
ROOT=Path(__file__).resolve().parents[1]
def test_config_loads_exact_strategy_set():
    c=AppConfig.load(ROOT); assert set(c.strategies)=={'regular-call','regular-put','swing-call','swing-put','bull-put-spread','bear-call-spread'}
def test_hash_is_stable(): assert stable_hash({'b':2,'a':1})==stable_hash({'a':1,'b':2})
def test_redaction(monkeypatch):
    monkeypatch.setenv('TRADIER_ACCESS_TOKEN','supersecret'); assert 'supersecret' not in redact('token supersecret')
