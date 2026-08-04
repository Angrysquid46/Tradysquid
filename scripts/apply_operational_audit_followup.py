from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "tradysquid" / "app.py"
source = app_path.read_text(encoding="utf-8")
old_refresh = '''    def refresh_market_session(self):
        try:
            clock = self.provider.market_clock()
            state = str(
                clock.get("state")
                or clock.get("status")
                or clock.get("market_state")
                or "unknown"
            ).casefold()
            is_open = state in {"open", "regular", "regular_hours"}
            self._market_clock_cache = {
                "observed_monotonic": time.monotonic(),
                "open": is_open,
                "state": state,
                "raw": clock,
            }
            self.publisher.notify("diagnostics")
            return dict(self._market_clock_cache)
        except Exception as exc:
            self.diagnostics.observe(
                "PROVIDER",
                "market-clock",
                f"{type(exc).__name__}: {exc}",
                healthy=False,
            )
            cached = dict(self._market_clock_cache)
            cached["status"] = "DEGRADED"
            cached["error"] = f"{type(exc).__name__}: {exc}"
            return cached
'''
new_refresh = '''    def refresh_market_session(self):
        try:
            response = self.provider.market_clock()
            clock = (
                response.get("clock", response)
                if isinstance(response, dict)
                else {}
            )
            state = str(
                clock.get("state")
                or clock.get("status")
                or clock.get("market_state")
                or "unknown"
            ).casefold()
            is_open = state in {"open", "regular", "regular_hours"}
            self._market_clock_cache = {
                "observed_monotonic": time.monotonic(),
                "open": is_open,
                "state": state,
                "raw": response,
            }
            self.publisher.notify("diagnostics")
            return dict(self._market_clock_cache)
        except Exception as exc:
            self.diagnostics.observe(
                "PROVIDER",
                "market-clock",
                f"{type(exc).__name__}: {exc}",
                healthy=False,
            )
            cached = dict(
                getattr(
                    self,
                    "_market_clock_cache",
                    {
                        "observed_monotonic": 0.0,
                        "open": False,
                        "state": "unknown",
                        "raw": {},
                    },
                )
            )
            cached["status"] = "DEGRADED"
            cached["error"] = f"{type(exc).__name__}: {exc}"
            return cached
'''
old_market = '''    def market_is_open(self) -> bool:
        age = time.monotonic() - float(
            self._market_clock_cache.get("observed_monotonic", 0.0)
        )
        if age > 45:
            self.refresh_market_session()
        return bool(self._market_clock_cache.get("open", False))
'''
new_market = '''    def market_is_open(self) -> bool:
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
for old, new, label in (
    (old_refresh, new_refresh, "market refresh"),
    (old_market, new_market, "market state"),
):
    if old not in source:
        raise RuntimeError(f"Operational {label} method was not found")
    source = source.replace(old, new, 1)
app_path.write_text(source, encoding="utf-8", newline="\n")

lifecycle_path = ROOT / "tests" / "test_full_audit_regressions.py"
lifecycle = lifecycle_path.read_text(encoding="utf-8")
old_test = '''    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app._position_quotes = lambda position_id: {"CALL": (1.20, 1.25)}

    results = Application.monitor_positions(app)
'''
new_test = '''    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app.market_is_open = lambda: True
    app._position_quote_map = lambda rows: {
        position.position_id: {"CALL": (1.20, 1.25)}
    }

    results = Application.monitor_positions(app)
'''
if old_test not in lifecycle:
    raise RuntimeError("Lifecycle test market context block was not found")
lifecycle_path.write_text(
    lifecycle.replace(old_test, new_test, 1),
    encoding="utf-8",
    newline="\n",
)

operational_path = ROOT / "tests" / "test_operational_audit_regressions.py"
operational = operational_path.read_text(encoding="utf-8")
clock_test = '''\n\ndef test_nested_tradier_clock_response_is_recognized(tmp_path):
    app = _app(tmp_path)
    app.provider = SimpleNamespace(
        market_clock=lambda: {"clock": {"state": "open", "description": "Market is open"}}
    )

    result = Application.refresh_market_session(app)

    assert result["open"] is True
    assert result["state"] == "open"
'''
if "test_nested_tradier_clock_response_is_recognized" not in operational:
    operational += clock_test
operational_path.write_text(operational, encoding="utf-8", newline="\n")
