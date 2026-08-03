from pathlib import Path
from tradysquid.core.config import AppConfig
ROOT=Path(__file__).resolve().parents[1]
def test_presets_are_distinct_and_loaded():
    c=AppConfig.load(ROOT); assert set(c.presets)=={'loose','balanced','tight','profit-focused'}
    values=[c.presets[x]['overrides']['minimum_setup_score'] for x in ['loose','balanced','tight','profit-focused']]
    assert values==sorted(values) and len(set(values))==4
