from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN=['/accounts/{account_id}/orders','/orders','place_order','cancel_order','preview_order']
def test_no_brokerage_write_capability():
    runtime='\n'.join(p.read_text(encoding='utf-8',errors='ignore') for p in (ROOT/'tradysquid').rglob('*.py'))
    for term in FORBIDDEN: assert term not in runtime
def test_no_hardcoded_tickers_in_strategy_source():
    source='\n'.join(p.read_text() for p in (ROOT/'tradysquid'/'strategies').glob('*.py'))
    for ticker in ['SPY','QQQ','FORD','AAPL','TSLA']: assert ticker not in source
