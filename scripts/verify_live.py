from pathlib import Path
from dotenv import load_dotenv
from tradysquid.app import Application
root=Path(__file__).resolve().parents[1]; load_dotenv(root/'.env',override=True); app=Application(root)
active=app.initialize_universe()
if not active: raise SystemExit('FAILED: no optionable universe symbols were discovered')
decisions=app.scanner.scan_symbol(active[0],'setup-acceptance')
assert len(decisions)==6
print(f'PASS: universe={len(active)} decisions={len(decisions)}')
