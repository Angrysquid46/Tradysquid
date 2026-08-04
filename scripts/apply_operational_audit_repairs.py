from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement for {old[:80]!r}")
    write(path, content.replace(old, new, 1))


replace_once(
    "tradysquid/app.py",
    "import signal\n",
    "import signal\nimport time\n",
)
replace_once(
    "tradysquid/app.py",
    '''        self.discord = None
        self.discord_task = None
''',
    '''        self.discord = None
        self.discord_task = None
        self._market_clock_cache = {
            "observed_monotonic": 0.0,
            "open": False,
            "state": "unknown",
            "raw": {},
        }
''',
)
replace_once(
    "tradysquid/app.py",
    '''                "market-session-refresh": lambda: self.publisher.notify(
                    "diagnostics"
                ),
''',
    '''                "market-session-refresh": self.refresh_market_session,
''',
)
replace_once(
    "tradysquid/app.py",
    '''    def _position_quotes(self, position_id):
        legs = self.db.query(
            "SELECT contract_symbol,expiration FROM paper_legs WHERE position_id=?",
            (position_id,),
        )
        position = self.db.query(
            "SELECT symbol FROM paper_positions WHERE id=?",
            (position_id,),
        )
        if not position:
            raise KeyError(position_id)
        by_expiration = {}
        for leg in legs:
            by_expiration.setdefault(leg["expiration"], []).append(
                leg["contract_symbol"]
            )
        output = {}
        for expiration, symbols in by_expiration.items():
            chain = {
                contract.symbol: contract
                for contract in self.provider.option_chain(
                    position[0]["symbol"], expiration
                )
            }
            for symbol in symbols:
                contract = chain.get(symbol)
                if not contract:
                    raise ValueError(f"Current quote missing for {symbol}")
                output[symbol] = (contract.bid, contract.ask)
        return output
''',
    '''    def refresh_market_session(self):
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

    def market_is_open(self) -> bool:
        age = time.monotonic() - float(
            self._market_clock_cache.get("observed_monotonic", 0.0)
        )
        if age > 45:
            self.refresh_market_session()
        return bool(self._market_clock_cache.get("open", False))

    def _next_scan_batch(self, symbols: list[str]) -> list[str]:
        ordered = list(dict.fromkeys(symbols))
        if not ordered:
            return []
        reserve = 25
        estimated_calls_per_symbol = 6
        request_budget = max(int(self.manager.available) - reserve, 0)
        batch_size = min(8, len(ordered), request_budget // estimated_calls_per_symbol)
        if batch_size <= 0:
            return []

        rows = self.db.query(
            "SELECT value_json FROM settings WHERE key='operations.scan-cursor'"
        )
        cursor = 0
        if rows:
            try:
                cursor = int(json.loads(rows[0]["value_json"]).get("cursor", 0))
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                cursor = 0
        cursor %= len(ordered)
        batch = [ordered[(cursor + offset) % len(ordered)] for offset in range(batch_size)]
        next_cursor = (cursor + batch_size) % len(ordered)
        self.db.execute(
            "INSERT OR REPLACE INTO settings(key,value_json,updated_at) VALUES (?,?,datetime('now'))",
            (
                "operations.scan-cursor",
                json.dumps(
                    {
                        "cursor": next_cursor,
                        "batch_size": batch_size,
                        "universe_size": len(ordered),
                    },
                    sort_keys=True,
                ),
            ),
        )
        return batch

    def _position_quote_map(self, position_rows: list[dict]) -> dict[str, dict]:
        if not position_rows:
            return {}
        position_symbols = {
            str(row["id"]): str(row["symbol"])
            for row in position_rows
        }
        placeholders = ",".join("?" for _ in position_symbols)
        legs = self.db.query(
            "SELECT position_id,contract_symbol,expiration FROM paper_legs "
            f"WHERE position_id IN ({placeholders}) ORDER BY position_id,id",
            tuple(position_symbols),
        )
        grouped: dict[tuple[str, str], list[dict]] = {}
        for leg in legs:
            key = (position_symbols[str(leg["position_id"])], str(leg["expiration"]))
            grouped.setdefault(key, []).append(leg)

        output = {position_id: {} for position_id in position_symbols}
        for (underlying, expiration), group in grouped.items():
            chain = {
                contract.symbol: contract
                for contract in self.provider.option_chain(underlying, expiration)
            }
            for leg in group:
                contract_symbol = str(leg["contract_symbol"])
                contract = chain.get(contract_symbol)
                if not contract:
                    raise ValueError(f"Current quote missing for {contract_symbol}")
                output[str(leg["position_id"])][contract_symbol] = (
                    contract.bid,
                    contract.ask,
                )
        return output

    def _position_quotes(self, position_id):
        position = self.db.query(
            "SELECT id,symbol FROM paper_positions WHERE id=?",
            (position_id,),
        )
        if not position:
            raise KeyError(position_id)
        return self._position_quote_map(position)[position_id]
''',
)
replace_once(
    "tradysquid/app.py",
    '''        if configured:
            decisions = [
''',
    '''        discovery_allowed = self.market_is_open() or not self.universe.active()
        if configured:
            decisions = [
''',
)
replace_once(
    "tradysquid/app.py",
    '''            try:
                discovered = self.discovery.discover(25)
                known = {decision.symbol for decision in decisions}
                decisions.extend(
                    decision
                    for decision in discovered
                    if decision.symbol not in known
                )
            except Exception as exc:
                self.diagnostics.observe(
                    "PROVIDER",
                    "universe-discovery",
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        else:
            decisions = self.discovery.discover(25)
''',
    '''            if discovery_allowed:
                try:
                    discovered = self.discovery.discover(25)
                    known = {decision.symbol for decision in decisions}
                    decisions.extend(
                        decision
                        for decision in discovered
                        if decision.symbol not in known
                    )
                except Exception as exc:
                    self.diagnostics.observe(
                        "PROVIDER",
                        "universe-discovery",
                        f"{type(exc).__name__}: {exc}",
                        healthy=False,
                    )
        elif discovery_allowed:
            decisions = self.discovery.discover(25)
        else:
            decisions = [
                UniverseDecision(
                    symbol,
                    1.0,
                    True,
                    {"source": "preserved-active-universe"},
                    [],
                )
                for symbol in self.universe.active()
            ]
''',
)
replace_once(
    "tradysquid/app.py",
    '''    def scan_all(self):
        total = 0
        opened_before = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        for symbol in self.universe.active():
            try:
                total += len(self.scan_symbol(symbol, "scheduled", publish=False))
            except Exception as exc:
                self.diagnostics.observe(
                    "SCANNER",
                    symbol,
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        opened_after = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        result = {
            "decisions": total,
            "paper_positions_opened": max(
                int(opened_after) - int(opened_before), 0
            ),
        }
        self.publisher.notify("scan")
        if result["paper_positions_opened"]:
            self.publisher.notify("paper")
        return result

    def monitor_positions(self):
        results = []
        for row in self.db.query(
            "SELECT id FROM paper_positions WHERE state IN "
            "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
        ):
            try:
                quotes = self._position_quotes(row["id"])
                marked = self.paper.mark(row["id"], quotes)
                if marked["state"] == "EXIT_PENDING":
                    marked = self.paper.close(
                        row["id"],
                        quotes,
                        marked.get("trigger") or "management exit",
                    )
                results.append(marked)
            except Exception as exc:
                self.diagnostics.observe(
                    "PAPER_TRADING",
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        if results:
            self.publisher.notify("paper")
        return results
''',
    '''    def scan_all(self):
        if not self.market_is_open():
            return {
                "status": "SKIPPED_MARKET_CLOSED",
                "decisions": 0,
                "paper_positions_opened": 0,
                "scanned_symbols": [],
            }

        active_symbols = self.universe.active()
        batch = self._next_scan_batch(active_symbols)
        if not batch:
            return {
                "status": "SKIPPED_PROVIDER_BUDGET",
                "decisions": 0,
                "paper_positions_opened": 0,
                "scanned_symbols": [],
                "provider_available": self.manager.available,
            }

        total = 0
        opened_before = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        failures = []
        for symbol in batch:
            try:
                total += len(self.scan_symbol(symbol, "scheduled", publish=False))
            except Exception as exc:
                failures.append(symbol)
                self.diagnostics.observe(
                    "SCANNER",
                    symbol,
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        opened_after = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        result = {
            "status": "PASS" if not failures else "DEGRADED",
            "decisions": total,
            "paper_positions_opened": max(
                int(opened_after) - int(opened_before), 0
            ),
            "scanned_symbols": batch,
            "failed_symbols": failures,
            "universe_size": len(active_symbols),
        }
        self.publisher.notify("scan")
        if result["paper_positions_opened"]:
            self.publisher.notify("paper")
        return result

    def monitor_positions(self):
        if not self.market_is_open():
            return []
        rows = self.db.query(
            "SELECT id,symbol FROM paper_positions WHERE state IN "
            "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
        )
        if not rows:
            return []
        try:
            quote_map = self._position_quote_map(rows)
        except Exception as exc:
            self.diagnostics.observe(
                "PAPER_TRADING",
                "position-quote-batch",
                f"{type(exc).__name__}: {exc}",
                healthy=False,
            )
            return []

        results = []
        for row in rows:
            try:
                quotes = quote_map[row["id"]]
                marked = self.paper.mark(row["id"], quotes)
                if marked["state"] == "EXIT_PENDING":
                    marked = self.paper.close(
                        row["id"],
                        quotes,
                        marked.get("trigger") or "management exit",
                    )
                results.append(marked)
            except Exception as exc:
                self.diagnostics.observe(
                    "PAPER_TRADING",
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        if results:
            self.publisher.notify("paper")
        return results
''',
)

replace_once(
    "tradysquid/trading/paper_broker.py",
    '''        entry_value = (
            decision.total_debit
            if decision.structure == Structure.LONG_OPTION
            else decision.total_credit
        )
        position = PaperPosition(
''',
    '''        signed_entry_cost = sum(
            (1 if leg.side == "buy" else -1)
            * float(leg.entry_fill)
            * int(leg.multiplier)
            * int(leg.quantity)
            for leg in legs
        )
        if decision.structure == Structure.LONG_OPTION:
            entry_value = signed_entry_cost
            actual_maximum_risk = entry_value
        else:
            entry_value = -signed_entry_cost
            actual_maximum_risk = max(
                float(decision.maximum_risk)
                + float(decision.total_credit)
                - entry_value,
                0.0,
            )
        configured_limit = float(
            decision.configuration_snapshot["contract_filters"]
            ["maximum_risk_dollars"]
        )
        if entry_value <= 0:
            raise ValueError("Conservative paper fill produced a non-positive entry value")
        if actual_maximum_risk > configured_limit + 1e-9:
            raise ValueError(
                "Conservative paper fill exceeds the configured maximum risk: "
                f"{actual_maximum_risk:.2f} > {configured_limit:.2f}"
            )

        position = PaperPosition(
''',
)
replace_once(
    "tradysquid/trading/paper_broker.py",
    '''            decision.maximum_risk,
''',
    '''            actual_maximum_risk,
''',
)

write(
    "tests/test_operational_audit_regressions.py",
    '''from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tradysquid.app import Application
from tradysquid.core.config import AppConfig
from tradysquid.core.enums import CandidateStatus, Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker


class Publisher:
    def __init__(self):
        self.events = []

    def notify(self, event):
        self.events.append(event)


class Diagnostics:
    def __init__(self):
        self.events = []

    def observe(self, *args, **kwargs):
        self.events.append((args, kwargs))


def _app(tmp_path):
    app = object.__new__(Application)
    app.db = Database(tmp_path / "ops.db")
    app.db.initialize()
    app.manager = SimpleNamespace(available=125)
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app._market_clock_cache = {
        "observed_monotonic": 10**12,
        "open": True,
        "state": "open",
        "raw": {},
    }
    return app


def _eligible_call(root, ask=0.80):
    config = AppConfig.load(root)
    contract = OptionContract(
        "CALL",
        "X",
        (date.today() + timedelta(days=14)).isoformat(),
        100,
        "call",
        max(ask - 0.10, 0.01),
        ask,
        100,
        500,
        0.40,
    )
    strategy = StrategyRegistry(config.strategies).get("regular-call")
    decision = strategy.evaluate(
        "scan", "X", 100, Regime.BULLISH_CONTROLLED, [contract], 80
    )
    decision.status = CandidateStatus.SELECTED
    return config, decision


def test_market_closed_scan_does_not_touch_scanner(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: False
    app.universe = SimpleNamespace(active=lambda: ["A", "B"])
    app.scan_symbol = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("scanner ran while market was closed")
    )

    result = Application.scan_all(app)

    assert result["status"] == "SKIPPED_MARKET_CLOSED"
    assert result["scanned_symbols"] == []


def test_scan_batches_rotate_without_exceeding_eight_symbols(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: True
    symbols = [f"T{index:02d}" for index in range(25)]
    app.universe = SimpleNamespace(active=lambda: symbols)
    scanned = []
    app.scan_symbol = lambda symbol, trigger, publish=False: scanned.append(symbol) or []

    first = Application.scan_all(app)
    second = Application.scan_all(app)

    assert len(first["scanned_symbols"]) == 8
    assert len(second["scanned_symbols"]) == 8
    assert set(first["scanned_symbols"]).isdisjoint(second["scanned_symbols"])
    assert scanned == first["scanned_symbols"] + second["scanned_symbols"]


def test_scan_skips_when_provider_reserve_would_be_consumed(tmp_path):
    app = _app(tmp_path)
    app.market_is_open = lambda: True
    app.manager.available = 25
    app.universe = SimpleNamespace(active=lambda: ["A", "B"])
    app.scan_symbol = lambda *args, **kwargs: []

    result = Application.scan_all(app)

    assert result["status"] == "SKIPPED_PROVIDER_BUDGET"


def test_position_quotes_batch_same_underlying_expiration(tmp_path):
    app = _app(tmp_path)
    expiration = (date.today() + timedelta(days=7)).isoformat()
    now = "2026-08-03T15:00:00+00:00"
    for index in (1, 2):
        app.db.execute(
            "INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,status) "
            "VALUES (?,?,?,?,?)",
            (f"c{index}", f"candidate{index}", "regular-call", now, "OPEN"),
        )
        app.db.execute(
            "INSERT INTO paper_positions("
            "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,"
            "symbol,direction,structure,state,opened_at,entry_value,current_value,"
            "maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"p{index}", f"c{index}", f"candidate{index}", "regular-call",
                "1", "hash", "X", "call", "long-option", "OPEN", now,
                50, 50, 50, 0, 0, 0, 0, "{}",
            ),
        )
        app.db.execute(
            "INSERT INTO paper_legs("
            "position_id,contract_symbol,side,quantity,option_type,strike,expiration,"
            "multiplier,entry_bid,entry_ask,entry_fill,current_bid,current_ask,current_mark"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"p{index}", f"CALL{index}", "buy", 1, "call", 100 + index,
                expiration, 100, .4, .5, .51, 0, 0, 0,
            ),
        )

    calls = []
    contracts = [
        OptionContract("CALL1", "X", expiration, 101, "call", .6, .7, 1, 1, .4),
        OptionContract("CALL2", "X", expiration, 102, "call", .8, .9, 1, 1, .4),
    ]
    app.provider = SimpleNamespace(
        option_chain=lambda symbol, expiry: calls.append((symbol, expiry)) or contracts
    )

    result = Application._position_quote_map(
        app,
        [{"id": "p1", "symbol": "X"}, {"id": "p2", "symbol": "X"}],
    )

    assert calls == [("X", expiration)]
    assert result["p1"]["CALL1"] == (.6, .7)
    assert result["p2"]["CALL2"] == (.8, .9)


def test_paper_entry_uses_conservative_fill_value(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    config, decision = _eligible_call(root, ask=.80)
    database = Database(tmp_path / "fill.db")
    database.initialize()
    database.register_strategies(config.strategies)

    position = PaperBroker(database).open(decision)

    assert position.entry_value == pytest.approx(81.0)
    assert position.maximum_risk == pytest.approx(81.0)


def test_paper_entry_rejects_slippage_above_risk_limit(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    config, decision = _eligible_call(root, ask=1.00)
    decision.status = CandidateStatus.SELECTED
    database = Database(tmp_path / "risk.db")
    database.initialize()
    database.register_strategies(config.strategies)

    with pytest.raises(ValueError, match="exceeds the configured maximum risk"):
        PaperBroker(database).open(decision)
''',
)

replace_once(
    "docs/CURRENT-REQUIREMENTS.md",
    '''| Scanning and position monitoring begin immediately | scheduler startup jobs | scheduler receipts | scheduler tests | recent scheduler runs |
''',
    '''| Scanning and position monitoring begin immediately during regular market hours | scheduler startup jobs plus cached Tradier market clock | scheduler receipts | scheduler and operational audit tests | recent scheduler runs |
| Provider load remains below the shared minute budget | rotating batches of at most eight symbols, 25-request reserve, grouped position chains | persisted scan cursor and request ledger | operational audit tests | live provider-budget receipt |
| Paper risk uses conservative executable fills | `PaperBroker.open` | stored leg fills and actual maximum risk | paper-fill regression tests | opened-position ledger |
''',
)

print("Operational audit repairs applied.")
