from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tradysquid" / "app.py"
source = path.read_text(encoding="utf-8")
old = '''    def market_is_open(self) -> bool:
        age = time.monotonic() - float(
            self._market_clock_cache.get("observed_monotonic", 0.0)
        )
        if age > 45:
            self.refresh_market_session()
        return bool(self._market_clock_cache.get("open", False))
'''
new = '''    def market_is_open(self) -> bool:
        cache = getattr(
            self,
            "_market_clock_cache",
            {
                "observed_monotonic": 0.0,
                "open": False,
                "state": "unknown",
                "raw": {},
            },
        )
        self._market_clock_cache = cache
        age = time.monotonic() - float(cache.get("observed_monotonic", 0.0))
        if age > 45:
            self.refresh_market_session()
            cache = self._market_clock_cache
        return bool(cache.get("open", False))
'''
if old not in source:
    raise RuntimeError("Operational market-clock method was not found")
path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
