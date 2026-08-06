from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path

from dotenv import load_dotenv

from .core.config import AppConfig
from .core.enums import CandidateStatus
from .core.logging import configure_logging
from .core.process_lock import ProcessLock
from .data.database import Database
from .data.legacy_import import import_legacy_closed_trades
from .discord.bot import DiscordBotService
from .discord.publishing import DiscordPublishingService
from .learning.analysis import LearningAnalysisService
from .learning.center import LearningCenter
from .learning.recommendations import RecommendationService
from .operations.diagnostics import DiagnosticService
from .operations.health import build_health
from .operations.jobs import JobRunner
from .operations.scheduler import SchedulerService
from .providers.request_manager import RequestManager
from .providers.tradier import TradierClient
from .reporting.periods import group_period
from .reporting.service import ReportingService
from .scanner.service import ScanService
from .strategies.registry import StrategyRegistry
from .strategies.versioning import StrategyVersionService
from .trading.paper_broker import PaperBroker
from .universe.controls import UniverseControls
from .universe.discovery import UniverseDiscovery
from .universe.service import UniverseDecision, UniverseService
from .version import __version__


class Application:
    def __init__(self, root: Path):
        self.root = root
        load_dotenv(root / ".env", override=True)
        self.config = AppConfig.load(root)
        configure_logging(root / "logs", self.config.defaults["logging"]["level"])
        self.lock = ProcessLock(root / "state" / "tradysquid.pid.json")
        self.db = Database(root / self.config.defaults["database"]["path"])
        self.db.initialize()
        self.db.register_strategies(self.config.strategies)
        active_configs = self.db.active_strategy_configs(self.config.strategies)
        self.legacy_import = import_legacy_closed_trades(
            self.db,
            root / "state" / "ford-plays-log.csv",
            active_configs,
        )
        self.manager = RequestManager(self.db)
        self.provider = TradierClient(self.manager)
        self.registry = StrategyRegistry(active_configs)
        self.versions = StrategyVersionService(self.db, self.registry)
        self.universe = UniverseService(self.db, 25)
        self.universe_controls = UniverseControls(self.db)
        self.discovery = UniverseDiscovery(self.provider)
        self.scanner = ScanService(self.db, self.provider, self.registry)
        self.paper = PaperBroker(self.db)
        self.reporting = ReportingService(self.db)
        self.learning = LearningCenter(self.config.learning_center)
        self.learning_analysis = LearningAnalysisService(self.db)
        self.recommendation_service = RecommendationService(self.db)
        self.scheduler = SchedulerService(self.config.defaults["market_timezone"])
        self.job_runner = JobRunner(self.db)
        self.diagnostics = DiagnosticService(self.db)
        self._stop = asyncio.Event()
        self.discord = None
        self.discord_task = None
        self._market_clock_cache = {
            "observed_monotonic": 0.0,
            "open": False,
            "state": "unknown",
            "raw": {},
        }

        services = {
            "health": self.health,
            "restart": self.request_restart,
            "version": lambda: __version__,
            "universe": self.universe.active,
            "universe_configured": self.universe_controls.configured,
            "universe_change": self.universe_change,
            "universe_refresh": self.initialize_universe,
            "scan": self.scan_symbol,
            "scan_status": self.scan_status,
            "candidate_view": self.candidate_view,
            "paper": self.paper_command,
            "open_positions": lambda: self.paper_command("open-positions", []),
            "strategies": self.strategy_view,
            "strategy_change": self.strategy_change,
            "recommendations": self.recommendation_command,
            "report": self.report_view,
            "learn": self.learning.search,
        }
        self.publisher = DiscordPublishingService(
            self.db,
            self.root,
            self.learning,
            services,
        )

        owner = os.environ.get("DISCORD_OWNER_USER_ID")
        guild = os.environ.get("DISCORD_GUILD_ID")
        if owner and guild:
            self.discord = DiscordBotService(
                services,
                int(owner),
                int(guild),
                self.config.discord_schema,
                root=self.root,
                publishing=self.publisher,
            )

    def request_restart(self):
        self._stop.set()
        return "Restart requested. Windows startup ownership will relaunch the application."

    def strategy_view(self, value=""):
        values = []
        for strategy in self.registry.all():
            acknowledgements = self.db.query(
                "SELECT component,version,hash,acknowledged_at "
                "FROM strategy_acknowledgements WHERE strategy_id=? ORDER BY component",
                (strategy.id,),
            )
            values.append(
                {
                    "strategy_id": strategy.id,
                    "version": strategy.config["version"],
                    "hash": strategy.config["configuration_hash"],
                    "preset": strategy.config["preset"],
                    "enabled": strategy.config["enabled"],
                    "acknowledgements": acknowledgements,
                }
            )
        return (
            next((item for item in values if item["strategy_id"] == value), values)
            if value
            else values
        )

    def strategy_change(self, name, parts):
        if not parts:
            raise ValueError("Strategy ID is required")
        strategy_id = parts[0]
        if name in {"strategy-enable", "strategy-disable"}:
            proposed = self.versions.propose(
                strategy_id,
                "enabled",
                name == "strategy-enable",
                name,
            )
            result = self.versions.activate(strategy_id, proposed, name).__dict__
        elif name == "strategy-preset":
            if len(parts) < 2 or parts[1] not in self.config.presets:
                raise ValueError("A valid preset is required")
            proposed = self.versions.propose(
                strategy_id,
                "preset",
                parts[1],
                f"Owner selected {parts[1]} preset",
            )
            overrides = self.config.presets[parts[1]]["overrides"]
            for path, value in overrides.items():
                group = (
                    "contract_filters"
                    if path in proposed["contract_filters"]
                    else "entry"
                )
                if hasattr(self.versions, "propose_from_config"):
                    proposed = self.versions.propose_from_config(
                        proposed,
                        f"{group}.{path}",
                        value,
                    )
                proposed[group][path] = value
            result = self.versions.activate(
                strategy_id,
                proposed,
                f"Owner selected {parts[1]} preset",
            ).__dict__
        elif name == "strategy-setting":
            if len(parts) < 3:
                raise ValueError("Usage: strategy-id setting.path JSON-value")
            value = json.loads(" ".join(parts[2:]))
            proposed = self.versions.propose(
                strategy_id,
                parts[1],
                value,
                "Owner setting change",
            )
            result = self.versions.activate(
                strategy_id,
                proposed,
                "Owner setting change",
            ).__dict__
        elif name == "strategy-rollback":
            if len(parts) < 2:
                raise ValueError("A stored version is required")
            result = self.versions.rollback(strategy_id, parts[1]).__dict__
        else:
            raise ValueError(name)
        self.publisher.notify("strategy")
        return result

    def universe_change(self, name, symbol):
        actions = {
            "universe-add": lambda: self.universe_controls.add(symbol),
            "universe-remove": lambda: self.universe_controls.remove(symbol),
            "universe-pin": lambda: self.universe_controls.pin(symbol, True),
            "universe-unpin": lambda: self.universe_controls.pin(symbol, False),
            "universe-exclude": lambda: self.universe_controls.exclude(symbol, True),
            "universe-include": lambda: self.universe_controls.exclude(symbol, False),
        }
        result = actions[name]()
        self.publisher.notify("universe")
        return {"action": name, "symbol": result}

    def report_view(self, name, value=""):
        if name == "strategy-report":
            return self.reporting.by_strategy()
        if name == "ticker-report":
            return self.reporting.by_ticker()
        if name == "learning-results":
            return {
                "strategies": self.learning_analysis.strategy_metrics(),
                "rejections": self.learning_analysis.rejection_tradeoffs(),
            }
        rows = self.db.query("SELECT * FROM closed_outcomes ORDER BY closed_at")
        if name == "daily-report":
            return group_period(rows, "daily")
        if name == "weekly-report":
            return group_period(rows, "weekly")
        if name == "monthly-report":
            return group_period(rows, "monthly")
        return self.reporting.overall()

    def recommendation_command(self, name, parts):
        if name == "strategy-recommendations":
            return self.db.query(
                "SELECT * FROM learning_recommendations ORDER BY updated_at DESC"
            )
        if not parts:
            raise ValueError("Recommendation ID is required")
        result = {
            "recommendation_id": parts[0],
            "status": self.recommendation_service.decide(
                parts[0],
                name == "strategy-approve",
            ),
        }
        self.publisher.notify("strategy")
        return result

    def scan_status(self):
        return self.db.query(
            "SELECT * FROM scan_cycles ORDER BY started_at DESC LIMIT 10"
        )

    def candidate_view(self, name, value=""):
        if name == "candidate":
            if not value:
                raise ValueError("Candidate ID is required")
            return {
                "candidate": self.db.query(
                    "SELECT * FROM candidates WHERE id=?",
                    (value,),
                ),
                "evidence": self.db.query(
                    "SELECT * FROM candidate_evidence WHERE candidate_id=?",
                    (value,),
                ),
                "rejections": self.db.query(
                    "SELECT * FROM candidate_rejections WHERE candidate_id=?",
                    (value,),
                ),
            }
        if name == "rejections":
            return self.reporting.rejected_analysis()
        raise ValueError(f"Unsupported candidate view: {name}")

    def refresh_market_session(self):
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

    def market_is_open(self) -> bool:
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

    def paper_command(self, name, parts):
        if name == "paper-open":
            if not parts:
                raise ValueError("Candidate ID is required")
            result = self.paper.open_candidate(parts[0]).__dict__
            self.publisher.notify("paper")
            return result
        if name == "paper-close":
            if not parts:
                raise ValueError("Position ID is required")
            reason = " ".join(parts[1:]) or "owner-close"
            result = self.paper.close(
                parts[0],
                self._position_quotes(parts[0]),
                reason,
            )
            self.publisher.notify("paper")
            return result
        if name == "paper-position":
            if not parts:
                raise ValueError("Position ID is required")
            return {
                "position": self.db.query(
                    "SELECT * FROM paper_positions WHERE id=?",
                    (parts[0],),
                ),
                "legs": self.db.query(
                    "SELECT * FROM paper_legs WHERE position_id=?",
                    (parts[0],),
                ),
                "events": self.db.query(
                    "SELECT * FROM lifecycle_events WHERE position_id=? "
                    "ORDER BY observed_at",
                    (parts[0],),
                ),
            }
        if name == "open-positions":
            return self.db.query(
                "SELECT * FROM paper_positions WHERE state IN "
                "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING') "
                "ORDER BY opened_at"
            )
        return self.db.query(
            "SELECT p.*,o.exit_reason,o.closed_at FROM paper_positions p "
            "JOIN closed_outcomes o ON o.position_id=p.id "
            "ORDER BY o.closed_at DESC LIMIT 100"
        )

    def health(self):
        health = build_health(
            self.db,
            self.registry,
            self.universe,
            self.scheduler,
            bool(self.discord and self.discord.ready),
        )
        health["open_diagnostics"] = self.diagnostics.current()
        health["provider_budget"] = {
            "allowed": self.manager.allowed,
            "used": self.manager.used,
            "available": self.manager.available,
            "expires_at": self.manager.expires_at,
        }
        health["discord_publishing_ready"] = self.publisher.ready
        return health

    def initialize_universe(self):
        configured_rows = self.universe_controls.configured()
        configured = [
            row["symbol"] for row in configured_rows if not row["excluded"]
        ]
        pinned = {
            row["symbol"]
            for row in configured_rows
            if row["pinned"] and not row["excluded"]
        }
        open_symbols = {
            row["symbol"]
            for row in self.db.query(
                "SELECT DISTINCT symbol FROM paper_positions WHERE state IN "
                "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
            )
        }
        discovery_allowed = self.market_is_open() or not self.universe.active()
        if configured:
            decisions = [
                UniverseDecision(
                    symbol,
                    1.0,
                    True,
                    {"source": "owner/configuration"},
                    [],
                )
                for symbol in configured
            ]
            if discovery_allowed:
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
        active = self.universe.rotate(
            decisions,
            protected=open_symbols,
            pinned=pinned,
        )
        self.publisher.notify("universe")
        return active

    def _read_state_receipt(self, name: str) -> dict:
        path = self.root / "state" / name
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    async def _wait_for_discord_readiness(self, timeout: int = 270) -> None:
        if self.discord is None:
            raise RuntimeError("Discord owner or guild configuration is missing")
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is missing")

        self.discord_task = asyncio.create_task(
            self.discord.start(token),
            name="tradysquid-discord-bot",
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            if self.publisher.ready and self.discord.ready:
                return

            if self.discord_task.done():
                try:
                    self.discord_task.result()
                except Exception as exc:
                    raise RuntimeError(
                        "Discord task exited before readiness: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                raise RuntimeError("Discord task exited before readiness")

            discord_receipt = self._read_state_receipt("discord-readiness.json")
            if discord_receipt.get("status") == "FAILED":
                raise RuntimeError(
                    "Discord readiness failed: "
                    + str(
                        discord_receipt.get("error")
                        or "unknown Discord error"
                    )
                )

            publishing_receipt = self._read_state_receipt(
                "discord-publishing-bootstrap.json"
            )
            if publishing_receipt.get("status") == "FAILED":
                cards = publishing_receipt.get("persistent_cards", {})
                raise RuntimeError(
                    "Discord publishing bootstrap failed: "
                    f"mandatory card failures={cards.get('failed', 'unknown')}"
                )

            await asyncio.sleep(1)

        raise TimeoutError(
            "Discord publishing readiness was not reached within "
            f"{timeout} seconds. Discord connected={bool(self.discord.ready)}; "
            f"publishing ready={bool(self.publisher.ready)}."
        )

    def _write_startup(self, status: str, **details) -> None:
        receipt = {
            "status": status,
            "pid": os.getpid(),
            "version": __version__,
            "database_integrity": self.db.integrity_check(),
            "strategy_count": len(self.registry.all()),
            "active_universe_count": len(self.universe.active()),
            "scheduler_running": self.scheduler.running,
            "discord_ready": bool(self.discord and self.discord.ready),
            "discord_publishing_ready": self.publisher.ready,
            **details,
        }
        state_path = self.root / "state" / "startup.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(receipt, indent=2),
            encoding="utf-8",
        )

    async def run(self):
        self.lock.acquire()
        try:
            self.initialize_universe()
            raw_jobs = {
                "provider-budget-refresh": lambda: self.publisher.notify(
                    "diagnostics"
                ),
                "market-session-refresh": self.refresh_market_session,
                "universe-evaluation": self.initialize_universe,
                "universe-rotation": self.initialize_universe,
                "active-universe-quotes": lambda: self.publisher.notify(
                    "universe"
                ),
                "full-strategy-scan": self.scan_all,
                "open-position-monitoring": self.monitor_positions,
                "market-intelligence-refresh": lambda: self.publisher.notify(
                    "universe"
                ),
                "daily-reporting": lambda: self.publisher.notify("reports"),
                "weekly-reporting": lambda: self.publisher.notify("reports"),
                "monthly-reporting": lambda: self.publisher.notify("reports"),
                "learning-results": lambda: self.publisher.notify("reports"),
                "learning-center-reconciliation": lambda: self.publisher.notify(
                    "all"
                ),
                "strategy-control-reconciliation": lambda: self.publisher.notify(
                    "strategy"
                ),
                "diagnostics": lambda: self.publisher.notify("diagnostics"),
                "database-backup": self.backup,
                "retention-cleanup": lambda: None,
            }
            jobs = {
                job_id: self.job_runner.wrap(job_id, function)
                for job_id, function in raw_jobs.items()
            }
            self.scheduler.register(jobs)
            self.scheduler.start()
            await self._wait_for_discord_readiness()
            self._write_startup("RUNNING")

            loop = asyncio.get_running_loop()
            for signal_value in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(signal_value, self._stop.set)
                except NotImplementedError:
                    pass
            await self._stop.wait()
        except Exception as exc:
            self._write_startup(
                "FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            if self.scheduler.running:
                self.scheduler.shutdown()
            if self.discord:
                await self.discord.close()
            if self.discord_task:
                self.discord_task.cancel()
            self.lock.release()

    def scan_symbol(
        self,
        symbol: str,
        trigger: str = "manual",
        *,
        publish: bool = True,
    ):
        decisions = self.scanner.scan_symbol(symbol, trigger)
        opened = []
        for decision in decisions:
            mode = str(
                decision.configuration_snapshot.get("entry", {}).get(
                    "selection_mode",
                    "record-only",
                )
            )
            if (
                decision.status == CandidateStatus.SELECTED
                and mode
                in {
                    "automatically open qualified paper trades",
                    "ranked top-N paper entries",
                }
            ):
                try:
                    opened.append(self.paper.open(decision).__dict__)
                except Exception as exc:
                    self.diagnostics.observe(
                        "PAPER_TRADING",
                        decision.candidate_id,
                        f"{type(exc).__name__}: {exc}",
                        healthy=False,
                    )
        if publish:
            self.publisher.notify("scan")
            if opened:
                self.publisher.notify("paper")
        return decisions

    def scan_all(self):
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

    def backup(self):
        from datetime import datetime

        return self.db.backup(
            self.root
            / "backups"
            / f"tradysquid-{datetime.now():%Y%m%d-%H%M%S}.db"
        )


def main():
    asyncio.run(Application(Path(__file__).resolve().parents[1]).run())


if __name__ == "__main__":
    main()
