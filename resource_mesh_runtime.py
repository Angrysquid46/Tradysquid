"""Integrate the optional free-data worker mesh with the information engine.

The production process submits sanitized enrichment tasks, consumes completed
results, stores durable observations, and starts a low-priority local fallback
when no remote worker heartbeat is present. Missing optional API keys never
block scanning, position management, Discord, or deployment.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import resource_mesh
import resource_mesh_worker

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATUS_PATH = STATE_DIR / "resource-mesh-status.json"
EVENT_RISK_PATH = STATE_DIR / "event-risk.json"
MACRO_PATH = STATE_DIR / "macro-context.json"
ENRICHMENT_DIR = STATE_DIR / "resource-enrichment"
DISPATCH_MINUTES = max(
    15, int(os.environ.get("RESOURCE_MESH_DISPATCH_MINUTES", "60"))
)
LOCAL_FALLBACK = (
    os.environ.get("RESOURCE_MESH_LOCAL_FALLBACK", "true").casefold()
    == "true"
)
EVENT_LOOKAHEAD_DAYS = max(
    1, int(os.environ.get("EVENT_RISK_LOOKAHEAD_DAYS", "45"))
)
_INSTALLED = False
_FALLBACK_STARTED = False


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _event_date(value: Any) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _extract_earnings(
    symbol: str, result: dict[str, Any]
) -> list[dict[str, Any]]:
    providers = result.get("providers") or {}
    finnhub = providers.get("finnhub") or {}
    data = finnhub.get("data") or {}
    calendar = data.get("earnings_calendar") or {}
    rows = (
        calendar.get("earningsCalendar")
        if isinstance(calendar, dict)
        else []
    )
    output: list[dict[str, Any]] = []
    today = date.today()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        event_day = _event_date(row.get("date"))
        if event_day is None:
            continue
        days = (event_day - today).days
        if days < -2 or days > EVENT_LOOKAHEAD_DAYS:
            continue
        output.append(
            {
                "symbol": symbol,
                "type": "earnings",
                "date": event_day.isoformat(),
                "days_until": days,
                "hour": row.get("hour") or "",
                "eps_estimate": row.get("epsEstimate"),
                "revenue_estimate": row.get("revenueEstimate"),
                "source": "Finnhub free earnings calendar",
                "observed_at": result.get("observed_at") or now_iso(),
            }
        )
    return output


def _merge_event_risk(
    symbol: str, events: list[dict[str, Any]]
) -> None:
    payload = _read_json(
        EVENT_RISK_PATH, {"version": 1, "symbols": {}}
    )
    symbols = payload.setdefault("symbols", {})
    symbols[symbol] = {
        "updated_at": now_iso(),
        "events": sorted(
            events,
            key=lambda item: (
                item.get("date") or "",
                item.get("type") or "",
            ),
        ),
    }
    payload["updated_at"] = now_iso()
    _atomic_json(EVENT_RISK_PATH, payload)


def event_risk_for(
    symbol: str, *, days: int = 14
) -> list[dict[str, Any]]:
    payload = _read_json(EVENT_RISK_PATH, {"symbols": {}})
    rows = (
        ((payload.get("symbols") or {}).get(symbol.upper()) or {}).get(
            "events"
        )
        or []
    )
    return [
        dict(item)
        for item in rows
        if -1
        <= int(item.get("days_until") or 9999)
        <= max(1, days)
    ]


def _store_research_sources(
    trade_intelligence: Any, result: dict[str, Any]
) -> int:
    symbol = str(result.get("symbol") or "").upper()
    providers = result.get("providers") or {}
    count = 0

    sec_data = (providers.get("sec") or {}).get("data") or {}
    for filing in sec_data.get("filings") or []:
        url = str(filing.get("url") or "")
        if not url:
            continue
        trade_intelligence.store_research_source(
            {
                "source_name": "SEC EDGAR via resource worker",
                "source_url": url,
                "published_at": filing.get("filing_date", ""),
                "ticker": symbol,
                "claim": (
                    f"{filing.get('form', 'filing')} filed "
                    f"{filing.get('filing_date', '')}"
                ),
                "confidence": "PRIMARY-SOURCE",
                "quality": "REGULATORY-FILING",
                "learning_concepts": [
                    "sec-filings",
                    "fundamental-research",
                ],
                "usage_terms": (
                    "Public SEC filing; retain original citation."
                ),
                "status": "REVIEW",
            }
        )
        count += 1

    finnhub_data = (providers.get("finnhub") or {}).get("data") or {}
    for item in finnhub_data.get("news") or []:
        url = str(item.get("url") or "")
        headline = str(item.get("headline") or "").strip()
        if not url or not headline:
            continue
        published = item.get("datetime")
        if isinstance(published, (int, float)):
            published = datetime.fromtimestamp(
                published, tz=now().tzinfo
            ).isoformat()
        trade_intelligence.store_research_source(
            {
                "source_name": str(
                    item.get("source") or "Finnhub news discovery"
                ),
                "source_url": url,
                "published_at": str(published or ""),
                "ticker": symbol,
                "claim": headline,
                "confidence": "AGGREGATED-HEADLINE",
                "quality": "REQUIRES-ORIGINAL-SOURCE",
                "learning_concepts": [
                    "news-events",
                    "research-verification",
                ],
                "usage_terms": (
                    "Headline discovery; verify the original publisher."
                ),
                "status": "REVIEW",
            }
        )
        count += 1
    return count


def _process_result(
    engine: Any,
    trade_intelligence: Any,
    item: dict[str, Any],
) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    result = dict(item.get("result") or {})
    if kind == "ticker-enrichment":
        symbol = str(
            result.get("symbol")
            or (item.get("payload") or {}).get("symbol")
            or ""
        ).upper()
        if not symbol:
            raise ValueError("ticker enrichment result has no symbol")
        ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_json(ENRICHMENT_DIR / f"{symbol}.json", item)
        events = _extract_earnings(symbol, result)
        _merge_event_risk(symbol, events)
        research = _store_research_sources(
            trade_intelligence, result
        )
        return {
            "kind": kind,
            "symbol": symbol,
            "events": len(events),
            "research": research,
        }
    if kind == "macro-refresh":
        _atomic_json(MACRO_PATH, item)
        return {
            "kind": kind,
            "providers": len(result.get("providers") or {}),
        }
    if kind == "compute-statistics":
        return {"kind": kind, "count": result.get("count", 0)}
    return {"kind": kind, "status": "stored"}


def install(
    engine: Any,
    dynamic_universe: Any,
    ford_scan: Any,
    trade_intelligence: Any,
) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def collect_job(connection: Any) -> str:
        results = resource_mesh.collect_results(limit=200)
        processed: list[dict[str, Any]] = []
        failed: list[str] = []
        for item in results:
            try:
                processed.append(
                    _process_result(engine, trade_intelligence, item)
                )
                engine.store_observation(
                    connection,
                    f"resource-mesh:{item.get('kind')}",
                    {
                        "task_id": item.get("task_id"),
                        "worker": item.get("worker"),
                        "result": item.get("result"),
                        "completed_at": item.get("completed_at"),
                    },
                )
            except Exception as exc:
                failed.append(
                    f"{item.get('task_id')}:"
                    f"{type(exc).__name__}:{exc}"
                )
        status_payload = {
            "updated_at": now_iso(),
            "worker": resource_mesh.read_heartbeat(),
            "worker_available": resource_mesh.worker_available(),
            "queues": resource_mesh.task_counts(),
            "processed": processed[-30:],
            "failed_results": failed[-20:],
        }
        _atomic_json(STATUS_PATH, status_payload)
        if failed:
            raise RuntimeError(
                "resource result processing failed: "
                + "; ".join(failed[:5])
            )
        return (
            f"collected {len(processed)} result(s); worker "
            f"{'online' if status_payload['worker_available'] else 'offline'}"
        )

    def dispatch_job(connection: Any) -> str:
        symbols = dynamic_universe.active_symbols()
        created = 0
        for symbol in symbols:
            result = resource_mesh.submit_task(
                "ticker-enrichment",
                {"symbol": symbol, "news_days": 5},
                priority=60,
                dedupe_key=(
                    f"ticker-enrichment:{symbol}:"
                    f"{now().strftime('%Y%m%d%H')}"
                ),
                dedupe_seconds=DISPATCH_MINUTES * 60,
                expires_seconds=6 * 3600,
            )
            created += int(bool(result.get("created")))
        macro = resource_mesh.submit_task(
            "macro-refresh",
            {"requested_at": now_iso()},
            priority=35,
            dedupe_key=f"macro:{now().strftime('%Y%m%d%H')}",
            dedupe_seconds=3 * 3600,
            expires_seconds=12 * 3600,
        )
        created += int(bool(macro.get("created")))
        engine.store_observation(
            connection,
            "resource-mesh-dispatch",
            {
                "active_symbols": symbols,
                "created": created,
                "queues": resource_mesh.task_counts(),
                "worker_available": resource_mesh.worker_available(),
                "at": now_iso(),
            },
        )
        return (
            f"queued {created} new task(s) for "
            f"{len(symbols)} symbols"
        )

    def health_job(connection: Any) -> str:
        payload = {
            "updated_at": now_iso(),
            "root": str(resource_mesh.mesh_root()),
            "worker_available": resource_mesh.worker_available(),
            "worker": resource_mesh.read_heartbeat(),
            "queues": resource_mesh.task_counts(),
            "failed": resource_mesh.list_failed(limit=10),
            "local_fallback_enabled": LOCAL_FALLBACK,
        }
        _atomic_json(STATUS_PATH, payload)
        engine.store_observation(
            connection, "resource-mesh-health", payload
        )
        return (
            f"worker {'online' if payload['worker_available'] else 'offline'}; "
            f"inbox {payload['queues']['inbox']}; "
            f"failed {payload['queues']['failed']}"
        )

    jobs = [
        engine.Job(
            "resource-mesh-collect",
            timedelta(seconds=30),
            collect_job,
            retry_interval=timedelta(seconds=30),
        ),
        engine.Job(
            "resource-mesh-dispatch",
            timedelta(minutes=DISPATCH_MINUTES),
            dispatch_job,
            background=True,
            retry_interval=timedelta(minutes=5),
        ),
        engine.Job(
            "resource-mesh-health",
            timedelta(minutes=5),
            health_job,
        ),
    ]
    existing = {job.name for job in engine.JOBS}
    for job in jobs:
        if job.name not in existing:
            engine.JOBS.append(job)

    original_candidate_to_row = ford_scan.candidate_to_row

    def candidate_to_row(
        candidate: dict[str, Any],
        rows: list[dict[str, str]],
        timestamp: datetime,
    ):
        row = original_candidate_to_row(candidate, rows, timestamp)
        risks = event_risk_for(
            str(row.get("ticker") or ford_scan.TICKER), days=14
        )
        if risks:
            summary = "; ".join(
                f"{item.get('type')} {item.get('date')} "
                f"({item.get('days_until')}d)"
                for item in risks[:3]
            )
            row["setup_reason"] = (
                str(row.get("setup_reason") or "")
                + f"; BINARY EVENT WARNING: {summary}"
            ).strip("; ")
            row["evidence_limitations"] = (
                str(row.get("evidence_limitations") or "")
                + " Upcoming event data can change or be incomplete; "
                "verify the issuer and broker calendar before execution."
            ).strip()
        return row

    ford_scan.candidate_to_row = candidate_to_row
    engine.RESOURCE_MESH_RUNTIME = "free-resource-mesh-v1"
    _INSTALLED = True


def start_local_fallback() -> threading.Thread | None:
    global _FALLBACK_STARTED
    if not LOCAL_FALLBACK or _FALLBACK_STARTED:
        return None
    _FALLBACK_STARTED = True
    thread = threading.Thread(
        target=resource_mesh_worker.run_forever,
        kwargs={"local_fallback": True},
        name="resource-mesh-local-fallback",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = ["event_risk_for", "install", "start_local_fallback"]
