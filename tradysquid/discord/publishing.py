from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import discord
except ImportError:  # pragma: no cover - production dependency check handles this
    discord = None

from .journals import JournalService
from .reconciliation import MessageReconciler
from .state import DiscordStateRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any, limit: int = 1600) -> str:
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    if len(text) > limit:
        text = text[: limit - 32] + "\n... truncated by Discord limit"
    return text


def _payload(title: str, value: Any, *, freshness: str = "CURRENT") -> dict[str, Any]:
    return {
        "content": (
            f"**{title}**\n"
            f"Freshness: `{freshness}` | Updated: `{_utc_now()}`\n"
            f"```json\n{_json_text(value)}\n```"
        )
    }


class DiscordChannelApi:
    """Synchronous adapter used by MessageReconciler from a worker thread."""

    def __init__(self, loop: asyncio.AbstractEventLoop, channels: dict[str, Any]):
        self.loop = loop
        self.channels = channels

    def _wait(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=30)

    def _channel(self, channel_id: str):
        channel = self.channels.get(str(channel_id))
        if channel is None:
            raise KeyError(f"Discord channel is not mapped: {channel_id}")
        return channel

    @staticmethod
    def _embeds(payload: dict[str, Any]) -> list[Any]:
        if discord is None:
            return []
        return [discord.Embed.from_dict(item) for item in payload.get("embeds", [])]

    def create_message(self, channel_id: str, payload: dict[str, Any]) -> dict[str, str]:
        channel = self._channel(channel_id)

        async def create():
            message = await channel.send(
                content=payload.get("content"),
                embeds=self._embeds(payload),
            )
            return {"id": str(message.id)}

        return self._wait(create())

    def update_message(
        self, channel_id: str, message_id: str, payload: dict[str, Any]
    ) -> dict[str, str]:
        channel = self._channel(channel_id)

        async def update():
            message = await channel.fetch_message(int(message_id))
            await message.edit(
                content=payload.get("content"),
                embeds=self._embeds(payload),
            )
            return {"id": str(message.id)}

        return self._wait(update())

    def get_message(self, channel_id: str, message_id: str) -> dict[str, str]:
        channel = self._channel(channel_id)

        async def fetch():
            message = await channel.fetch_message(int(message_id))
            return {"id": str(message.id)}

        return self._wait(fetch())


class DiscordPublishingService:
    """Publishes SQLite-backed Discord views and reconciles them in place."""

    REQUIRED_BOOTSTRAP_CARDS = (
        ("system-health", "system-health", "System Health"),
        ("system-activity", "system-activity", "System Activity"),
        ("diagnostics", "diagnostics", "Diagnostics"),
        ("update-status", "update-status", "Update Status"),
        ("active-universe", "active-universe", "Active Universe"),
        ("market-regime", "market-regime", "Market Regime"),
        ("provider-status", "provider-status", "Provider Status"),
        ("latest-scan", "scan-results", "Latest Scan"),
        ("accepted-candidates", "accepted-candidates", "Accepted Candidates"),
        ("rejected-candidates", "rejected-candidates", "Rejected Candidates"),
        ("shadow-candidates", "shadow-candidates", "Shadow Candidates"),
        ("open-positions", "open-positions", "Open Positions"),
        ("recent-lifecycle-events", "lifecycle-events", "Lifecycle Events"),
        ("daily-recap", "daily-recap", "Daily Recap"),
        ("weekly-report", "weekly-report", "Weekly Report"),
        ("monthly-dashboard", "monthly-dashboard", "Monthly Dashboard"),
        ("ticker-results", "ticker-results", "Ticker Results"),
        ("strategy-breakdown", "strategy-breakdown", "Strategy Breakdown"),
        ("regular-call", "regular-calls", "Regular Calls"),
        ("regular-put", "regular-puts", "Regular Puts"),
        ("swing-call", "swing-calls", "Swing Calls"),
        ("swing-put", "swing-puts", "Swing Puts"),
        ("bull-put-spread", "bull-put-spreads", "Bull Put Spreads"),
        ("bear-call-spread", "bear-call-spreads", "Bear Call Spreads"),
        ("learning-results", "learning-results", "Learning Results"),
        ("strategy-control", "strategy-control", "Strategy Control"),
        ("strategy-settings", "strategy-settings", "Strategy Settings"),
        ("strategy-versions", "strategy-versions", "Strategy Versions"),
        ("strategy-recommendations", "strategy-recommendations", "Strategy Recommendations"),
    )

    def __init__(
        self,
        database,
        root: Path,
        learning_center,
        services: dict[str, Callable[..., Any]],
    ) -> None:
        self.db = database
        self.root = root
        self.learning_center = learning_center
        self.services = services
        self.state = DiscordStateRepository(database)
        self.journals = JournalService(database)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.channel_by_name: dict[str, Any] = {}
        self.channel_by_id: dict[str, Any] = {}
        self.reconciler: MessageReconciler | None = None
        self.ready = False
        self.ready_event = asyncio.Event()
        self._refresh_lock = asyncio.Lock()

    def _record_receipt(self, component: str, status: str, details: dict[str, Any]) -> None:
        receipt_id = f"{component}:{_utc_now()}"
        self.db.execute(
            "INSERT INTO discord_sync_receipts(id,component,status,details_json,observed_at) "
            "VALUES (?,?,?,?,?)",
            (receipt_id, component, status, json.dumps(details, sort_keys=True, default=str), _utc_now()),
        )

    def _service(self, name: str, *args, default: Any = None) -> Any:
        function = self.services.get(name)
        if function is None:
            return default
        try:
            return function(*args)
        except Exception as exc:  # publishing must not stop trading work
            return {"status": "DEGRADED", "error": f"{type(exc).__name__}: {exc}"}

    def _card_value(self, stable_id: str) -> Any:
        if stable_id == "system-health":
            return self._service("health", default={})
        if stable_id == "system-activity":
            return self.db.query(
                "SELECT level,component,event_type,message,observed_at "
                "FROM application_events ORDER BY observed_at DESC LIMIT 15"
            )
        if stable_id == "diagnostics":
            return self.db.query(
                "SELECT category,status,message,last_seen,count FROM diagnostics "
                "ORDER BY last_seen DESC LIMIT 20"
            )
        if stable_id == "update-status":
            return {
                "version": self._service("version", default="unknown"),
                "branch": "clean-rebuild",
                "paper_trading_only": True,
            }
        if stable_id == "active-universe":
            return self.db.query(
                "SELECT symbol,pinned,protected,score,reason,updated_at "
                "FROM universe_membership WHERE active=1 ORDER BY score DESC,symbol"
            )
        if stable_id == "market-regime":
            return self.db.query(
                "SELECT symbol,regime,confidence,observed_at FROM market_regimes "
                "ORDER BY observed_at DESC LIMIT 25"
            )
        if stable_id == "provider-status":
            health = self._service("health", default={})
            return health.get("provider_budget", health) if isinstance(health, dict) else health
        if stable_id == "latest-scan":
            return self.db.query(
                "SELECT id,trigger,source,status,started_at,completed_at,totals_json,errors_json "
                "FROM scan_cycles ORDER BY started_at DESC LIMIT 1"
            )
        if stable_id == "accepted-candidates":
            return self.db.query(
                "SELECT id,strategy_id,symbol,status,setup_score,maximum_risk,observed_at "
                "FROM candidates WHERE status IN ('ELIGIBLE','RANKED','SELECTED','OPENED') "
                "ORDER BY observed_at DESC LIMIT 20"
            )
        if stable_id == "rejected-candidates":
            return self.db.query(
                "SELECT c.id,c.strategy_id,c.symbol,c.observed_at,r.reason "
                "FROM candidates c JOIN candidate_rejections r ON r.candidate_id=c.id "
                "ORDER BY c.observed_at DESC LIMIT 20"
            )
        if stable_id == "shadow-candidates":
            return self.db.query(
                "SELECT candidate_id,source_status,outcome,opened_at,closed_at "
                "FROM shadow_candidates ORDER BY opened_at DESC LIMIT 20"
            )
        if stable_id == "open-positions":
            return self._service("open_positions", default=[])
        if stable_id == "recent-lifecycle-events":
            return self.db.query(
                "SELECT position_id,previous_state,new_state,reason,observed_at "
                "FROM lifecycle_events ORDER BY observed_at DESC LIMIT 20"
            )
        if stable_id == "daily-recap":
            return self._service("report", "daily-report", default={})
        if stable_id == "weekly-report":
            return self._service("report", "weekly-report", default={})
        if stable_id == "monthly-dashboard":
            return self._service("report", "monthly-report", default={})
        if stable_id == "ticker-results":
            return self._service("report", "ticker-report", default={})
        if stable_id == "strategy-breakdown":
            return self._service("report", "strategy-report", default={})
        if stable_id in {
            "regular-call",
            "regular-put",
            "swing-call",
            "swing-put",
            "bull-put-spread",
            "bear-call-spread",
        }:
            values = self._service("report", "strategy-report", default=[])
            if isinstance(values, list):
                return [row for row in values if row.get("strategy_id") == stable_id]
            return values
        if stable_id == "learning-results":
            return self._service("report", "learning-results", default={})
        if stable_id == "strategy-control":
            return self._service("strategies", default=[])
        if stable_id == "strategy-settings":
            return self.db.query(
                "SELECT strategy_id,version,hash,preset,active,created_at "
                "FROM strategy_versions ORDER BY strategy_id,created_at DESC"
            )
        if stable_id == "strategy-versions":
            return self.db.query(
                "SELECT strategy_id,version,hash,preset,owner_approved,active,created_at,retired_at "
                "FROM strategy_versions ORDER BY strategy_id,created_at DESC"
            )
        if stable_id == "strategy-recommendations":
            return self.db.query(
                "SELECT id,strategy_id,current_version,status,setting_path,owner_decision,updated_at "
                "FROM learning_recommendations ORDER BY updated_at DESC LIMIT 30"
            )
        return {"status": "NO DATA"}

    async def _publish(self, stable_id: str, channel_name: str, title: str, value: Any) -> str:
        if self.reconciler is None:
            raise RuntimeError("Discord publishing is not initialized")
        channel = self.channel_by_name.get(channel_name.casefold())
        if channel is None:
            raise KeyError(f"Required Discord channel was not resolved: {channel_name}")
        result = await asyncio.to_thread(
            self.reconciler.reconcile,
            stable_id,
            str(channel.id),
            _payload(title, value),
            "1",
        )
        return "unchanged" if result.get("signature") else "updated"

    async def _publish_bootstrap_cards(self) -> dict[str, int]:
        totals = {"created_or_updated": 0, "unchanged": 0, "failed": 0}
        for stable_id, channel_name, title in self.REQUIRED_BOOTSTRAP_CARDS:
            try:
                result = await self._publish(
                    stable_id,
                    channel_name,
                    title,
                    self._card_value(stable_id),
                )
                totals["unchanged" if result == "unchanged" else "created_or_updated"] += 1
            except Exception as exc:
                totals["failed"] += 1
                self._record_receipt(
                    f"card:{stable_id}",
                    "FAILED",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
        return totals

    async def _publish_learning_center(self) -> dict[str, int]:
        totals = {"reconciled": 0, "failed": 0}
        lessons = list(self.learning_center.lessons.values())
        index = [
            {"lesson_id": lesson["lesson_id"], "title": lesson["title"]}
            for lesson in lessons
        ]
        try:
            await self._publish(
                "learning-center:index",
                "learning-search",
                "Learning Center Index",
                index,
            )
            totals["reconciled"] += 1
        except Exception:
            totals["failed"] += 1
        for lesson in lessons:
            channel_name = str(lesson.get("channel_name") or lesson["lesson_id"]).casefold()
            value = {
                key: lesson.get(key)
                for key in (
                    "lesson_id",
                    "title",
                    "version",
                    "purpose",
                    "concept",
                    "scanner_application",
                    "risk_considerations",
                    "limitations",
                    "practice_drill",
                )
                if lesson.get(key) is not None
            }
            try:
                await self._publish(
                    f"learning-center:{lesson['lesson_id']}",
                    channel_name,
                    str(lesson["title"]),
                    value,
                )
                totals["reconciled"] += 1
            except Exception as exc:
                totals["failed"] += 1
                self._record_receipt(
                    f"lesson:{lesson['lesson_id']}",
                    "FAILED",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
        return totals

    async def _publish_journals(self) -> dict[str, int]:
        totals = {"reconciled": 0, "failed": 0}
        positions = self.db.query(
            "SELECT id FROM paper_positions ORDER BY opened_at DESC LIMIT 100"
        )
        for row in positions:
            position_id = row["id"]
            try:
                chunks = self.journals.render(position_id)
                for index, chunk in enumerate(chunks):
                    stable_id = (
                        f"trade-journal:{position_id}"
                        if index == 0
                        else f"trade-journal:{position_id}:{index + 1}"
                    )
                    await self._publish(
                        stable_id,
                        "trade-journal",
                        f"Trade Journal {position_id}",
                        {"part": index + 1, "content": chunk},
                    )
                    totals["reconciled"] += 1
            except Exception as exc:
                totals["failed"] += 1
                self._record_receipt(
                    f"journal:{position_id}",
                    "FAILED",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
        return totals

    async def bootstrap(self, guild: Any, channel_map: dict[str, Any]) -> dict[str, Any]:
        async with self._refresh_lock:
            self.loop = asyncio.get_running_loop()
            self.channel_by_name = {
                name.casefold(): channel for name, channel in channel_map.items()
            }
            self.channel_by_id = {
                str(channel.id): channel for channel in self.channel_by_name.values()
            }
            self.reconciler = MessageReconciler(
                DiscordChannelApi(self.loop, self.channel_by_id), self.state
            )
            cards = await self._publish_bootstrap_cards()
            learning = await self._publish_learning_center()
            journals = await self._publish_journals()
            mandatory_failures = cards["failed"]
            status = "PASS" if mandatory_failures == 0 else "FAILED"
            receipt = {
                "status": status,
                "guild_id": str(guild.id),
                "channels_resolved": len(self.channel_by_name),
                "persistent_cards": cards,
                "learning_center": learning,
                "journals": journals,
                "completed_at": _utc_now(),
                "secret_values_written": False,
            }
            state_path = self.root / "state" / "discord-publishing-bootstrap.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
            self._record_receipt("publishing-bootstrap", status, receipt)
            if status != "PASS":
                raise RuntimeError(
                    f"Discord publishing bootstrap failed for {mandatory_failures} mandatory cards"
                )
            self.ready = True
            self.ready_event.set()
            return receipt

    async def refresh(self, event: str = "all") -> None:
        if not self.ready or self.reconciler is None:
            return
        async with self._refresh_lock:
            event_cards = {
                "universe": {"active-universe", "provider-status", "system-health"},
                "scan": {
                    "latest-scan",
                    "accepted-candidates",
                    "rejected-candidates",
                    "shadow-candidates",
                    "market-regime",
                    "system-activity",
                },
                "paper": {
                    "open-positions",
                    "recent-lifecycle-events",
                    "daily-recap",
                    "weekly-report",
                    "monthly-dashboard",
                    "ticker-results",
                    "strategy-breakdown",
                    "learning-results",
                },
                "strategy": {
                    "strategy-control",
                    "strategy-settings",
                    "strategy-versions",
                    "strategy-recommendations",
                },
                "diagnostics": {"system-health", "diagnostics", "provider-status"},
                "reports": {
                    "daily-recap",
                    "weekly-report",
                    "monthly-dashboard",
                    "ticker-results",
                    "strategy-breakdown",
                    "learning-results",
                },
            }
            selected = event_cards.get(event)
            for stable_id, channel_name, title in self.REQUIRED_BOOTSTRAP_CARDS:
                if selected is not None and stable_id not in selected:
                    continue
                try:
                    await self._publish(
                        stable_id,
                        channel_name,
                        title,
                        self._card_value(stable_id),
                    )
                except Exception as exc:
                    self._record_receipt(
                        f"refresh:{stable_id}",
                        "FAILED",
                        {"event": event, "error": f"{type(exc).__name__}: {exc}"},
                    )
            if event == "paper":
                await self._publish_journals()
            if event in {"strategy", "reports", "all"}:
                await self._publish_learning_center()

    def notify(self, event: str) -> None:
        if self.loop is None or not self.ready:
            return
        asyncio.run_coroutine_threadsafe(self.refresh(event), self.loop)
