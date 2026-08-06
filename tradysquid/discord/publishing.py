from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import discord
except ImportError:  # pragma: no cover - installation verification handles this
    discord = None

from .contracts import signature
from .journals import JournalService
from .layout import CARD_ROUTES, CARD_TITLES, LESSON_ROUTES, route_for
from .reconciliation import MessageReconciler
from .state import DiscordStateRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freshness(value: Any) -> str:
    timestamps: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key).casefold()
                if (
                    key_text.endswith("_at")
                    or key_text in {"timestamp", "observed", "updated", "completed"}
                ) and isinstance(child, str) and child:
                    timestamps.append(child)
                else:
                    collect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                collect(child)

    collect(value)
    return max(timestamps) if timestamps else "Waiting for source data"


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return value


def _clean(value: Any) -> Any:
    hidden = {
        "id",
        "candidate_id",
        "position_id",
        "scan_cycle_id",
        "trade_cycle_id",
        "configuration_hash",
        "strategy_hash",
        "hash",
        "config_json",
        "details_json",
        "errors_json",
        "totals_json",
        "value_json",
        "patch_json",
    }
    value = _parse_json(value)
    if value is None:
        return None
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).casefold() in hidden:
                continue
            cleaned = _clean(item)
            if cleaned in (None, "", [], {}):
                continue
            output[str(key)] = cleaned
        return output
    if isinstance(value, (list, tuple)):
        output = [_clean(item) for item in value]
        return [item for item in output if item not in (None, "", [], {})]
    return value


def _label(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").strip().title()


def _line_value(value: Any) -> str:
    value = _parse_json(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if abs(value) < 1:
            return f"{value:.2%}"
        return f"{value:,.2f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _generic_lines(value: Any, *, limit: int = 18) -> list[str]:
    cleaned = _clean(value)
    if cleaned in (None, "", [], {}):
        return ["No records yet. This card will update when data arrives."]
    if isinstance(cleaned, dict):
        lines: list[str] = []
        for key, item in cleaned.items():
            if len(lines) >= limit:
                break
            if isinstance(item, dict):
                lines.append(f"**{_label(key)}**")
                for child_key, child_value in list(item.items())[:5]:
                    lines.append(f"• {_label(child_key)}: {_line_value(child_value)}")
            elif isinstance(item, list):
                lines.append(f"**{_label(key)}:** {len(item)} records")
                for row in item[:4]:
                    if isinstance(row, dict):
                        summary = " • ".join(
                            f"{_label(child_key)}: {_line_value(child_value)}"
                            for child_key, child_value in list(row.items())[:4]
                        )
                        lines.append(f"• {summary}")
                    else:
                        lines.append(f"• {_line_value(row)}")
            else:
                lines.append(f"**{_label(key)}:** {_line_value(item)}")
        return lines or ["No useful fields were present."]
    if isinstance(cleaned, list):
        lines = [f"**Total:** {len(cleaned)}"]
        for row in cleaned[: min(limit - 1, 10)]:
            if isinstance(row, dict):
                lines.append(
                    "• "
                    + " • ".join(
                        f"{_label(key)}: {_line_value(item)}"
                        for key, item in list(row.items())[:5]
                    )
                )
            else:
                lines.append(f"• {_line_value(row)}")
        return lines
    return [_line_value(cleaned)]


def _render_card(stable_id: str | None, value: Any) -> list[str]:
    cleaned = _clean(value)
    if stable_id in {"rejected-candidates", "learning-results"}:
        rows: list[dict[str, Any]] = []
        if isinstance(cleaned, list):
            rows = [row for row in cleaned if isinstance(row, dict)]
        elif isinstance(cleaned, dict):
            raw = cleaned.get("rejections", [])
            if isinstance(raw, list):
                rows = [row for row in raw if isinstance(row, dict)]
        if rows:
            counts: Counter[str] = Counter()
            total = 0
            for row in rows:
                reason = str(row.get("reason") or "Unspecified rejection")
                count = int(row.get("rejected", 1) or 1)
                counts[reason] += count
                total += count
            lines = [f"**Total rejected observations:** {total}"]
            lines.extend(
                f"• {reason}: **{count}**"
                for reason, count in counts.most_common(10)
            )
            return lines
    if stable_id in {
        "accepted-candidates",
        "open-positions",
        "new-positions",
    } and isinstance(cleaned, list):
        lines = [f"**Total:** {len(cleaned)}"]
        for row in cleaned[:10]:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol", "Unknown")
            strategy = row.get("strategy_id", "Unknown strategy")
            status = row.get("status") or row.get("state") or "Unknown"
            details = [f"**{symbol}**", str(strategy), str(status)]
            if row.get("setup_score") is not None:
                details.append(f"score {float(row['setup_score']):.1f}")
            if row.get("pnl_dollars") is not None:
                details.append(f"P/L ${float(row['pnl_dollars']):.2f}")
            lines.append(" • ".join(details))
        return lines
    if stable_id in {"wins", "losses"} and isinstance(cleaned, list):
        total = sum(
            float(row.get("pnl_dollars", 0) or 0)
            for row in cleaned
            if isinstance(row, dict)
        )
        lines = [f"**Trades:** {len(cleaned)}", f"**Recorded P/L:** ${total:,.2f}"]
        for row in cleaned[:8]:
            if isinstance(row, dict):
                lines.append(
                    f"• **{row.get('symbol', 'Unknown')}** • "
                    f"{row.get('strategy_id', '')} • "
                    f"${float(row.get('pnl_dollars', 0) or 0):.2f} • "
                    f"{row.get('exit_reason', 'No exit reason')}"
                )
        return lines
    if stable_id == "active-universe" and isinstance(cleaned, list):
        symbols = [
            str(row.get("symbol"))
            for row in cleaned
            if isinstance(row, dict) and row.get("symbol")
        ]
        return [
            f"**Active symbols:** {len(symbols)}",
            ", ".join(symbols[:25]) if symbols else "No active symbols yet.",
        ]
    if stable_id == "latest-scan" and isinstance(cleaned, list) and cleaned:
        row = cleaned[0]
        return [
            f"**Status:** {row.get('status', 'Unknown')}",
            f"**Trigger:** {row.get('trigger', 'Unknown')}",
            f"**Source:** {row.get('source', 'Unknown')}",
            f"**Started:** {row.get('started_at', 'Unknown')}",
            f"**Completed:** {row.get('completed_at') or 'Still running'}",
        ]
    return _generic_lines(cleaned)


def _payload(
    title: str,
    value: Any,
    *,
    stable_id: str | None = None,
) -> dict[str, Any]:
    lines = [
        f"**{title}**",
        f"Source freshness: `{_freshness(value)}`",
        *_render_card(stable_id, value),
    ]
    content = "\n".join(lines)
    if len(content) > 1990:
        content = content[:1940].rstrip() + "\n… additional details omitted"
    return {"content": content}


class DiscordChannelApi:
    """Synchronous adapter used by MessageReconciler from a worker thread."""

    def __init__(self, loop: asyncio.AbstractEventLoop, channels: dict[str, Any]):
        self.loop = loop
        self.channels = channels

    def _wait(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=45)

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
    """Publish all Tradysquid state into the established Discord dashboard."""

    REQUIRED_BOOTSTRAP_CARDS = tuple(
        (
            stable_id,
            str(route["channel"]),
            CARD_TITLES.get(stable_id, stable_id.replace("-", " ").title()),
        )
        for stable_id, route in CARD_ROUTES.items()
    )

    CORE_BOOTSTRAP_IDS = frozenset(
        stable_id
        for stable_id, route in CARD_ROUTES.items()
        if bool(route.get("mandatory", False))
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
        self.guild: Any | None = None
        self.channel_by_name: dict[str, Any] = {}
        self.channel_by_id: dict[str, Any] = {}
        self.reconciler: MessageReconciler | None = None
        self.ready = False
        self.ready_event = asyncio.Event()
        self._refresh_lock = asyncio.Lock()
        self._pending_events: set[str] = set()

    def _record_receipt(self, component: str, status: str, details: dict[str, Any]) -> None:
        observed = _utc_now()
        self.db.execute(
            "INSERT INTO discord_sync_receipts(id,component,status,details_json,observed_at) "
            "VALUES (?,?,?,?,?)",
            (
                f"{component}:{observed}",
                component,
                status,
                json.dumps(details, sort_keys=True, default=str),
                observed,
            ),
        )

    def _service(self, name: str, *args, default: Any = None) -> Any:
        function = self.services.get(name)
        if function is None:
            return default
        try:
            return function(*args)
        except Exception as exc:
            return {"status": "DEGRADED", "error": f"{type(exc).__name__}: {exc}"}

    def _card_value(self, stable_id: str) -> Any:
        if stable_id == "system-health":
            return self._service("health", default={})
        if stable_id == "scanner-status":
            return {
                "health": self._service("health", default={}),
                "recent_scans": self.db.query(
                    "SELECT trigger,source,status,started_at,completed_at "
                    "FROM scan_cycles ORDER BY started_at DESC LIMIT 10"
                ),
            }
        if stable_id == "api-errors":
            return self.db.query(
                "SELECT provider,category,message,observed_at FROM provider_failures "
                "ORDER BY observed_at DESC LIMIT 25"
            )
        if stable_id == "system-activity":
            return self.db.query(
                "SELECT level,component,event_type,message,observed_at "
                "FROM application_events ORDER BY observed_at DESC LIMIT 20"
            )
        if stable_id == "diagnostics":
            return self.db.query(
                "SELECT category,status,message,last_seen,count FROM diagnostics "
                "ORDER BY last_seen DESC LIMIT 25"
            )
        if stable_id == "update-status":
            return {
                "version": self._service("version", default="unknown"),
                "branch": "clean-rebuild",
                "paper_trading_only": True,
            }
        if stable_id == "provider-status":
            health = self._service("health", default={})
            budget = health.get("provider_budget", health) if isinstance(health, dict) else health
            return {
                "budget": budget,
                "recent_failures": self.db.query(
                    "SELECT provider,category,message,observed_at FROM provider_failures "
                    "ORDER BY observed_at DESC LIMIT 10"
                ),
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
        if stable_id == "session-preparation":
            return {
                "active_universe": self._card_value("active-universe"),
                "market_regime": self._card_value("market-regime"),
                "latest_scan": self._card_value("latest-scan"),
            }
        if stable_id == "breaking-events":
            return self.db.query(
                "SELECT level,component,event_type,message,observed_at "
                "FROM application_events WHERE level IN ('WARNING','ERROR','CRITICAL') "
                "OR event_type LIKE '%alert%' OR event_type LIKE '%event%' "
                "ORDER BY observed_at DESC LIMIT 25"
            )
        if stable_id == "ticker-intelligence":
            return {
                "recent_provider_requests": self.db.query(
                    "SELECT provider,endpoint,status,cached,requested_at,completed_at "
                    "FROM provider_requests ORDER BY requested_at DESC LIMIT 25"
                ),
                "cache_freshness": self.db.query(
                    "SELECT cache_key,source,observed_at,expires_at "
                    "FROM provider_cache_metadata ORDER BY observed_at DESC LIMIT 25"
                ),
            }
        if stable_id == "charts-and-levels":
            return self.db.query(
                "SELECT symbol,support,resistance,channel_position,observed_at "
                "FROM levels ORDER BY observed_at DESC LIMIT 25"
            )
        if stable_id == "latest-scan":
            return self.db.query(
                "SELECT trigger,source,status,started_at,completed_at "
                "FROM scan_cycles ORDER BY started_at DESC LIMIT 1"
            )
        if stable_id == "accepted-candidates":
            return self.db.query(
                "SELECT strategy_id,symbol,status,setup_score,maximum_risk,observed_at "
                "FROM candidates WHERE status IN ('ELIGIBLE','RANKED','SELECTED','OPENED') "
                "ORDER BY observed_at DESC LIMIT 20"
            )
        if stable_id == "rejected-candidates":
            return self.db.query(
                "SELECT r.reason,COUNT(*) AS rejected "
                "FROM candidate_rejections r GROUP BY r.reason "
                "ORDER BY rejected DESC LIMIT 20"
            )
        if stable_id == "new-positions":
            return self.db.query(
                "SELECT symbol,strategy_id,state,opened_at,entry_value,maximum_risk "
                "FROM paper_positions ORDER BY opened_at DESC LIMIT 20"
            )
        if stable_id == "open-positions":
            return self._service("open_positions", default=[])
        if stable_id == "recent-lifecycle-events":
            return self.db.query(
                "SELECT previous_state,new_state,reason,observed_at "
                "FROM lifecycle_events ORDER BY observed_at DESC LIMIT 25"
            )
        if stable_id in {"wins", "losses"}:
            comparison = "> 0" if stable_id == "wins" else "< 0"
            return self.db.query(
                "SELECT p.symbol,p.strategy_id,o.outcome,o.exit_reason,o.pnl_dollars,"
                "o.pnl_pct,o.closed_at FROM closed_outcomes o "
                "JOIN paper_positions p ON p.id=o.position_id "
                f"WHERE o.pnl_dollars {comparison} "
                "ORDER BY o.closed_at DESC LIMIT 50"
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
            if isinstance(values, dict):
                return {
                    key: value
                    for key, value in values.items()
                    if key == stable_id or str(key).startswith(f"{stable_id}@")
                }
            return values
        if stable_id == "learning-results":
            return self._service("report", "learning-results", default={})
        if stable_id == "strategy-control":
            return self._service("strategies", default=[])
        if stable_id == "strategy-settings":
            return self.db.query(
                "SELECT strategy_id,version,preset,active,created_at "
                "FROM strategy_versions ORDER BY strategy_id,created_at DESC"
            )
        if stable_id == "strategy-versions":
            return self.db.query(
                "SELECT strategy_id,version,preset,owner_approved,active,created_at,retired_at "
                "FROM strategy_versions ORDER BY strategy_id,created_at DESC"
            )
        if stable_id == "trade-overrides":
            return self.db.query(
                "SELECT strategy_id,scope,scope_value,enabled,created_at "
                "FROM overrides ORDER BY created_at DESC LIMIT 50"
            )
        if stable_id == "strategy-change-log":
            return {
                "versions": self.db.query(
                    "SELECT strategy_id,version,preset,owner_approved,active,created_at,retired_at "
                    "FROM strategy_versions ORDER BY created_at DESC LIMIT 50"
                ),
                "acknowledgements": self.db.query(
                    "SELECT strategy_id,version,component,acknowledged_at "
                    "FROM strategy_acknowledgements ORDER BY acknowledged_at DESC LIMIT 50"
                ),
            }
        if stable_id == "strategy-recommendations":
            return self.db.query(
                "SELECT strategy_id,current_version,status,setting_path,owner_decision,updated_at "
                "FROM learning_recommendations ORDER BY updated_at DESC LIMIT 50"
            )
        if stable_id == "workflow-log":
            return self.db.query(
                "SELECT version,commit_sha,status,observed_at FROM deployment_receipts "
                "ORDER BY observed_at DESC LIMIT 30"
            )
        if stable_id == "automation-diagnostics":
            return self.db.query(
                "SELECT job_id,status,started_at,completed_at FROM scheduler_runs "
                "ORDER BY started_at DESC LIMIT 40"
            )
        if stable_id == "applied-upgrades":
            return self.db.query(
                "SELECT version,commit_sha,status,observed_at FROM deployment_receipts "
                "WHERE status='PASS' ORDER BY observed_at DESC LIMIT 30"
            )
        if stable_id == "upgrade-review":
            return self.db.query(
                "SELECT strategy_id,current_version,status,setting_path,owner_decision,updated_at "
                "FROM learning_recommendations WHERE status NOT IN ('APPLIED','REJECTED') "
                "ORDER BY updated_at DESC LIMIT 50"
            )
        return {"status": "NO DATA"}

    async def _publish(
        self, stable_id: str, channel_name: str, title: str, value: Any
    ) -> str:
        if self.reconciler is None:
            raise RuntimeError("Discord publishing is not initialized")
        channel = self.channel_by_name.get(channel_name.casefold())
        if channel is None:
            raise KeyError(f"Original Discord channel was not resolved: {channel_name}")
        result = await asyncio.to_thread(
            self.reconciler.reconcile,
            stable_id,
            str(channel.id),
            _payload(title, value, stable_id=stable_id),
            "3",
        )
        return str(result.get("action", "updated"))

    async def _publish_bootstrap_cards(
        self,
        *,
        stable_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        totals: dict[str, Any] = {
            "created": 0,
            "updated": 0,
            "rebound": 0,
            "unchanged": 0,
            "failed": 0,
            "mandatory_failed": 0,
            "failures": [],
        }
        for stable_id, channel_name, title in self.REQUIRED_BOOTSTRAP_CARDS:
            if stable_ids is not None and stable_id not in stable_ids:
                continue
            try:
                action = await self._publish(
                    stable_id,
                    channel_name,
                    title,
                    self._card_value(stable_id),
                )
                totals[action if action in totals else "updated"] += 1
            except Exception as exc:
                route = CARD_ROUTES[stable_id]
                failure = {
                    "stable_id": stable_id,
                    "channel": channel_name,
                    "mandatory": bool(route.get("mandatory", False)),
                    "error": f"{type(exc).__name__}: {exc}",
                }
                totals["failed"] += 1
                totals["mandatory_failed"] += int(failure["mandatory"])
                totals["failures"].append(failure)
                self._record_receipt(f"card:{stable_id}", "FAILED", failure)
        return totals

    def _manifest(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for stable_id in CARD_ROUTES:
            route = route_for(stable_id)
            channel = self.channel_by_name.get(route["channel"].casefold())
            state = self.state.get(stable_id)
            output.append(
                {
                    **route,
                    "destination_channel_id": str(channel.id) if channel else None,
                    "message_id": state.get("message_id") if state else None,
                    "migration_status": "BOUND" if channel else "MISSING",
                }
            )
        output.append(
            {
                "stable_id": "trade-journal:<position-id>",
                "category": "LIVE TRADING DESK",
                "channel": "trade-journal",
                "destination_channel_id": (
                    str(self.channel_by_name["trade-journal"].id)
                    if "trade-journal" in self.channel_by_name
                    else None
                ),
                "mandatory": True,
                "owner_only": False,
                "updates_in_place": True,
                "migration_status": (
                    "BOUND" if "trade-journal" in self.channel_by_name else "MISSING"
                ),
            }
        )
        for lesson in self.learning_center.lessons.values():
            lesson_id = str(lesson["lesson_id"])
            channel_name = str(
                LESSON_ROUTES.get(
                    lesson_id,
                    lesson.get("channel_name") or lesson_id,
                )
            )
            channel = self.channel_by_name.get(channel_name.casefold())
            output.append(
                {
                    "stable_id": f"learning-center:{lesson_id}",
                    "category": "LEARNING CENTER",
                    "channel": channel_name,
                    "destination_channel_id": str(channel.id) if channel else None,
                    "mandatory": True,
                    "owner_only": False,
                    "updates_in_place": True,
                    "migration_status": "BOUND" if channel else "MISSING",
                }
            )
        return output

    async def _publish_learning_center(self) -> dict[str, Any]:
        totals: dict[str, Any] = {"reconciled": 0, "failed": 0, "failures": []}
        lessons = list(self.learning_center.lessons.values())
        index = [
            {
                "lesson": index + 1,
                "title": lesson["title"],
                "channel": LESSON_ROUTES.get(
                    str(lesson["lesson_id"]),
                    str(lesson.get("channel_name") or lesson["lesson_id"]),
                ),
            }
            for index, lesson in enumerate(lessons)
        ]
        try:
            await self._publish(
                "learning-center:index",
                "learning-index",
                "Learning Center • Lessons 1–27",
                index,
            )
            totals["reconciled"] += 1
        except Exception as exc:
            totals["failed"] += 1
            totals["failures"].append(
                {
                    "stable_id": "learning-center:index",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        for lesson in lessons:
            lesson_id = str(lesson["lesson_id"])
            channel_name = str(
                LESSON_ROUTES.get(
                    lesson_id,
                    lesson.get("channel_name") or lesson_id,
                )
            )
            value = {
                key: lesson.get(key)
                for key in (
                    "title",
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
                    f"learning-center:{lesson_id}",
                    channel_name,
                    str(lesson["title"]),
                    value,
                )
                totals["reconciled"] += 1
            except Exception as exc:
                totals["failed"] += 1
                failure = {
                    "stable_id": f"learning-center:{lesson_id}",
                    "channel": channel_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                totals["failures"].append(failure)
                self._record_receipt(f"lesson:{lesson_id}", "FAILED", failure)
        return totals

    def _journal_thread_id(self, position_id: str) -> str | None:
        rows = self.db.query(
            "SELECT message_id FROM journal_state WHERE position_id=?",
            (position_id,),
        )
        if not rows or not rows[0].get("message_id"):
            return None
        return str(rows[0]["message_id"])

    def _put_journal_thread(
        self,
        position_id: str,
        thread_id: str,
        chunks: list[str],
    ) -> None:
        digest = hashlib.sha256(
            json.dumps(chunks, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.db.execute(
            "INSERT OR REPLACE INTO journal_state(position_id,message_id,version,signature,updated_at) "
            "VALUES (?,?,?,?,?)",
            (position_id, thread_id, "3", digest, _utc_now()),
        )

    async def _resolve_journal_thread(self, thread_id: str) -> Any | None:
        if self.guild is None:
            return None
        getter = getattr(self.guild, "get_thread", None)
        if getter is not None:
            thread = getter(int(thread_id))
            if thread is not None:
                return thread
        fetch = getattr(self.guild, "fetch_channel", None)
        if fetch is not None:
            try:
                return await fetch(int(thread_id))
            except Exception:
                return None
        return None

    @staticmethod
    def _thread_result(result: Any) -> tuple[Any, Any | None]:
        thread = getattr(result, "thread", None)
        message = getattr(result, "message", None)
        if thread is not None:
            return thread, message
        if isinstance(result, tuple):
            return result[0], result[1] if len(result) > 1 else None
        return result, None

    async def _create_journal_thread(
        self,
        forum: Any,
        position_id: str,
        first_chunk: str,
    ) -> tuple[Any, Any]:
        rows = self.db.query(
            "SELECT symbol,strategy_id FROM paper_positions WHERE id=?",
            (position_id,),
        )
        row = rows[0] if rows else {}
        name = (
            f"{row.get('symbol', 'Trade')} • {row.get('strategy_id', 'journal')} • "
            f"{position_id[:8]}"
        )[:100]
        result = await forum.create_thread(name=name, content=first_chunk)
        thread, starter = self._thread_result(result)
        if starter is None:
            fetch = getattr(thread, "fetch_message", None)
            if fetch is not None:
                starter = await fetch(int(thread.id))
        if starter is None:
            raise RuntimeError("Discord forum did not return a starter message")
        return thread, starter

    async def _publish_forum_journal(
        self,
        forum: Any,
        position_id: str,
        chunks: list[str],
    ) -> int:
        thread_id = self._journal_thread_id(position_id)
        thread = await self._resolve_journal_thread(thread_id) if thread_id else None
        starter = None

        if thread is None:
            thread, starter = await self._create_journal_thread(
                forum,
                position_id,
                chunks[0],
            )
            thread_id = str(thread.id)
            self.channel_by_id[thread_id] = thread
            first_payload = {"content": chunks[0]}
            self.state.put(
                f"trade-journal:{position_id}",
                {
                    "channel_id": thread_id,
                    "message_id": str(starter.id),
                    "version": "3",
                    "signature": signature(first_payload),
                    "acknowledged": True,
                },
            )
        else:
            self.channel_by_id[str(thread.id)] = thread

        reconciler = MessageReconciler(
            DiscordChannelApi(self.loop, self.channel_by_id),
            self.state,
        )
        for index, chunk in enumerate(chunks):
            stable_id = (
                f"trade-journal:{position_id}"
                if index == 0
                else f"trade-journal:{position_id}:part:{index + 1}"
            )
            await asyncio.to_thread(
                reconciler.reconcile,
                stable_id,
                str(thread.id),
                {"content": chunk},
                "3",
            )
        self._put_journal_thread(position_id, str(thread.id), chunks)
        return len(chunks)

    async def _publish_journals(self) -> dict[str, Any]:
        totals: dict[str, Any] = {"reconciled": 0, "failed": 0, "failures": []}
        destination = self.channel_by_name.get("trade-journal")
        if destination is None:
            return {
                "reconciled": 0,
                "failed": 1,
                "failures": [{"error": "Original trade-journal destination is missing"}],
            }

        positions = self.db.query(
            "SELECT id FROM paper_positions ORDER BY opened_at DESC"
        )
        is_forum = (
            "forum" in str(getattr(destination, "type", "")).casefold()
            or destination.__class__.__name__.casefold().endswith("forumchannel")
            or hasattr(destination, "create_thread")
        )

        for row in positions:
            position_id = str(row["id"])
            try:
                chunks = self.journals.render(position_id)
                if is_forum:
                    totals["reconciled"] += await self._publish_forum_journal(
                        destination,
                        position_id,
                        chunks,
                    )
                else:
                    for index, chunk in enumerate(chunks):
                        stable_id = (
                            f"trade-journal:{position_id}"
                            if index == 0
                            else f"trade-journal:{position_id}:part:{index + 1}"
                        )
                        await self._publish(
                            stable_id,
                            "trade-journal",
                            f"Trade Journal • {position_id}",
                            {"part": index + 1, "content": chunk},
                        )
                        totals["reconciled"] += 1
            except Exception as exc:
                failure = {
                    "position_id": position_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                totals["failed"] += 1
                totals["failures"].append(failure)
                self._record_receipt(f"journal:{position_id}", "FAILED", failure)
        return totals

    async def bootstrap(self, guild: Any, channel_map: dict[str, Any]) -> dict[str, Any]:
        async with self._refresh_lock:
            self.loop = asyncio.get_running_loop()
            self.guild = guild
            self.channel_by_name = {
                name.casefold(): channel for name, channel in channel_map.items()
            }
            self.channel_by_id = {
                str(channel.id): channel
                for channel in self.channel_by_name.values()
                if getattr(channel, "id", None) is not None
            }
            self.reconciler = MessageReconciler(
                DiscordChannelApi(self.loop, self.channel_by_id),
                self.state,
            )

            manifest_before = self._manifest()
            missing_routes = [
                row["stable_id"]
                for row in manifest_before
                if row["migration_status"] == "MISSING" and row["mandatory"]
            ]
            cards = await self._publish_bootstrap_cards(
                stable_ids=set(self.CORE_BOOTSTRAP_IDS)
            )
            learning = {
                "status": "PENDING",
                "reconciled": 0,
                "failed": 0,
                "failures": [],
            }
            journals = {
                "status": "PENDING",
                "reconciled": 0,
                "failed": 0,
                "failures": [],
            }
            manifest = self._manifest()
            state_directory = self.root / "state"
            state_directory.mkdir(parents=True, exist_ok=True)
            manifest_path = state_directory / "discord-routing-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            failures = int(cards["mandatory_failed"]) + len(missing_routes)
            status = "PASS" if failures == 0 else "FAILED"
            receipt = {
                "status": status,
                "guild_id": str(guild.id),
                "channels_resolved": len(
                    {str(channel.id) for channel in self.channel_by_name.values()}
                ),
                "routes_total": len(manifest),
                "routes_missing": missing_routes,
                "persistent_cards": cards,
                "learning_center": learning,
                "journals": journals,
                "extended_backfill": {"status": "PENDING"},
                "routing_manifest": str(manifest_path),
                "pending_events_captured": sorted(self._pending_events),
                "completed_at": _utc_now(),
                "secret_values_written": False,
            }
            (state_directory / "discord-publishing-bootstrap.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._record_receipt("publishing-bootstrap", status, receipt)
            if status != "PASS":
                raise RuntimeError(
                    "Discord publishing bootstrap failed: "
                    f"missing routes={len(missing_routes)}, "
                    f"mandatory cards={cards['mandatory_failed']}"
                )
            self.ready = True
            self.ready_event.set()
            pending = tuple(sorted(self._pending_events))
            self._pending_events.clear()
            for event in pending:
                asyncio.create_task(self.refresh(event))
            return receipt

    async def complete_backfill(self) -> dict[str, Any]:
        """Populate non-core cards, all lessons, and all historical journals.

        This runs after core readiness so Discord history reconciliation cannot
        roll back an otherwise healthy scanner and paper-trading runtime.
        """

        async with self._refresh_lock:
            cards = await self._publish_bootstrap_cards()
            learning = await self._publish_learning_center()
            journals = await self._publish_journals()
            failures = (
                int(cards["failed"])
                + int(learning["failed"])
                + int(journals["failed"])
            )
            status = "PASS" if failures == 0 else "DEGRADED"
            receipt = {
                "status": status,
                "persistent_cards": cards,
                "learning_center": learning,
                "journals": journals,
                "completed_at": _utc_now(),
                "secret_values_written": False,
            }
            state_directory = self.root / "state"
            state_directory.mkdir(parents=True, exist_ok=True)
            (state_directory / "discord-extended-backfill.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._record_receipt("publishing-extended-backfill", status, receipt)
            return receipt

    async def refresh(self, event: str = "all") -> None:
        if not self.ready or self.reconciler is None:
            self._pending_events.add(event)
            return
        async with self._refresh_lock:
            event_cards = {
                "universe": {
                    "active-universe",
                    "market-regime",
                    "session-preparation",
                    "provider-status",
                    "system-health",
                },
                "scan": {
                    "latest-scan",
                    "accepted-candidates",
                    "rejected-candidates",
                    "market-regime",
                    "charts-and-levels",
                    "ticker-intelligence",
                    "scanner-status",
                    "system-activity",
                },
                "paper": {
                    "new-positions",
                    "open-positions",
                    "recent-lifecycle-events",
                    "wins",
                    "losses",
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
                    "trade-overrides",
                    "strategy-change-log",
                    "strategy-recommendations",
                    "upgrade-review",
                },
                "diagnostics": {
                    "system-health",
                    "scanner-status",
                    "api-errors",
                    "system-activity",
                    "diagnostics",
                    "provider-status",
                    "workflow-log",
                    "automation-diagnostics",
                    "applied-upgrades",
                },
                "reports": {
                    "daily-recap",
                    "weekly-report",
                    "monthly-dashboard",
                    "ticker-results",
                    "strategy-breakdown",
                    "regular-call",
                    "regular-put",
                    "swing-call",
                    "swing-put",
                    "bull-put-spread",
                    "bear-call-spread",
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
                        {
                            "event": event,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
            if event == "paper":
                await self._publish_journals()
            if event in {"strategy", "reports", "all"}:
                await self._publish_learning_center()

    def notify(self, event: str) -> None:
        if not self.ready or self.loop is None:
            self._pending_events.add(event)
            return
        asyncio.run_coroutine_threadsafe(self.refresh(event), self.loop)
