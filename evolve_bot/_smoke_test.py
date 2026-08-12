"""One-off manual smoke test against real live Tradier data - not part of
the automated test suite (no mocks, hits the real API, deliberately not
named test_*.py so pytest doesn't collect it). Reads .env directly rather
than importing the frozen run_with_env.py, keeping this fully independent
of the live production launcher.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for raw_line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    os.environ[name.strip()] = value.strip()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine

print(engine.run_cycle())
