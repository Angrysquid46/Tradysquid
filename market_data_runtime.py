"""Shared Tradier request budgeting and cross-process market-data caching.

The production computer remains the only process allowed to use the Tradier
credential. All Tradier callers share one SQLite ledger so the command bot,
information engine, targeted scanner, and manual tools observe the same rolling
request budget. Actual response headers override the configured allowance.

Only data that is safe to reuse is cached. Live execution quotes never use a
stale fallback. Daily history and expiration metadata may use a bounded stale
copy during a provider interruption so a temporary outage does not erase the
entire research context.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import requests

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
DB_PATH = STATE_DIR / "provider-resource-ledger.db"
STATUS_PATH = STATE_DIR / "tradier-resource-status.json"
DEFAULT_ALLOWED = max(30, int(os.environ.get("TRADIER_REQUESTS_PER_MINUTE", "125")))
SAFETY_RESERVE = max(2, int(os.environ.get("TRADIER_RATE_SAFETY_RESERVE", "8")))
MAX_WAIT_SECONDS = max(5, int(os.environ.get("TRADIER_RATE_MAX_WAIT_SECONDS", "70")))
_INSTALLED = False
_INSTALL_LOCK = threading.RLock()


class ProviderBudgetError(RuntimeError):
    """Raised when a provider budget cannot be reserved safely."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS provider_budget (
            provider TEXT PRIMARY KEY,
            allowed INTEGER NOT NULL,
            used INTEGER NOT NULL,
            available INTEGER NOT NULL,
            window_started_ms INTEGER NOT NULL,
            expires_ms INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'configured'
        );
        CREATE TABLE IF NOT EXISTS response_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_ms INTEGER NOT NULL,
            expires_ms INTEGER NOT NULL,
            stale_until_ms INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS response_cache_expiry
            ON response_cache(provider, expires_ms);
        CREATE TABLE IF NOT EXISTS provider_request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            status_code INTEGER,
            elapsed_ms INTEGER,
            cache_status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS provider_request_log_time
            ON provider_request_log(provider, id DESC);
        """
    )
    connection.commit()
    return connection


def _initial_budget(now_ms: int) -> tuple[int, int, int, int, int]:
    expires = now_ms + 60_000
    return DEFAULT_ALLOWED, 0, DEFAULT_ALLOWED, now_ms, expires


def _normalize_expiry(value: Any, now_ms: int) -> int:
    try:
        expiry = int(float(value))
    except (TypeError, ValueError):
        return now_ms + 60_000
    if expiry < 10_000_000_000:
        expiry *= 1000
    if expiry <= now_ms:
        return now_ms + 60_000
    return expiry


def _write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, STATUS_PATH)


def budget_snapshot(provider: str = "tradier") -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM provider_budget WHERE provider=?", (provider,)
        ).fetchone()
        if row is None:
            allowed, used, available, started, expires = _initial_budget(now_ms)
            return {
                "provider": provider,
                "allowed": allowed,
                "used": used,
                "available": available,
                "window_started_ms": started,
                "expires_ms": expires,
                "seconds_until_reset": max(0.0, (expires - now_ms) / 1000),
                "source": "configured",
                "updated_at": now_iso(),
            }
        payload = dict(row)
        if now_ms >= int(payload["expires_ms"]):
            payload.update(
                used=0,
                available=int(payload["allowed"]),
                window_started_ms=now_ms,
                expires_ms=now_ms + 60_000,
                source="local-reset",
                updated_at=now_iso(),
            )
        payload["seconds_until_reset"] = max(
            0.0, (int(payload["expires_ms"]) - now_ms) / 1000
        )
        return payload
    finally:
        connection.close()


def reserve(provider: str = "tradier", *, cost: int = 1) -> dict[str, Any]:
    """Reserve request capacity across every local Tradysquid process."""
    cost = max(1, int(cost))
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while True:
        now_ms = int(time.time() * 1000)
        connection = _connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM provider_budget WHERE provider=?", (provider,)
            ).fetchone()
            if row is None:
                allowed, used, available, started, expires = _initial_budget(now_ms)
                source = "configured"
            else:
                allowed = max(1, int(row["allowed"]))
                used = max(0, int(row["used"]))
                available = max(0, int(row["available"]))
                started = int(row["window_started_ms"])
                expires = int(row["expires_ms"])
                source = str(row["source"] or "ledger")
                if now_ms >= expires:
                    used = 0
                    available = allowed
                    started = now_ms
                    expires = now_ms + 60_000
                    source = "local-reset"
            usable = max(1, allowed - min(SAFETY_RESERVE, max(allowed - 1, 0)))
            if used + cost <= usable and available >= cost:
                used += cost
                available = max(0, min(available - cost, allowed - used))
                connection.execute(
                    """
                    INSERT INTO provider_budget(
                        provider, allowed, used, available, window_started_ms,
                        expires_ms, updated_at, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        allowed=excluded.allowed,
                        used=excluded.used,
                        available=excluded.available,
                        window_started_ms=excluded.window_started_ms,
                        expires_ms=excluded.expires_ms,
                        updated_at=excluded.updated_at,
                        source=excluded.source
                    """,
                    (
                        provider,
                        allowed,
                        used,
                        available,
                        started,
                        expires,
                        now_iso(),
                        source,
                    ),
                )
                connection.commit()
                snapshot = {
                    "provider": provider,
                    "allowed": allowed,
                    "used": used,
                    "available": available,
                    "window_started_ms": started,
                    "expires_ms": expires,
                    "seconds_until_reset": max(0.0, (expires - now_ms) / 1000),
                    "source": source,
                    "updated_at": now_iso(),
                }
                _write_status(snapshot)
                return snapshot
            connection.rollback()
            wait_seconds = max(
                0.05, min((expires - now_ms) / 1000 + 0.05, 5.0)
            )
        finally:
            connection.close()
        if time.monotonic() + wait_seconds > deadline:
            raise ProviderBudgetError(
                f"{provider} request budget stayed exhausted for {MAX_WAIT_SECONDS}s"
            )
        time.sleep(wait_seconds)


def record_headers(headers: Mapping[str, Any], provider: str = "tradier") -> None:
    lower = {str(key).casefold(): value for key, value in headers.items()}
    allowed_raw = lower.get("x-ratelimit-allowed")
    used_raw = lower.get("x-ratelimit-used")
    available_raw = lower.get("x-ratelimit-available")
    expiry_raw = lower.get("x-ratelimit-expiry")
    if allowed_raw is None and used_raw is None and available_raw is None:
        return
    now_ms = int(time.time() * 1000)
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM provider_budget WHERE provider=?", (provider,)
        ).fetchone()
        allowed = (
            int(float(allowed_raw))
            if allowed_raw is not None
            else int(row["allowed"] if row else DEFAULT_ALLOWED)
        )
        used = (
            int(float(used_raw))
            if used_raw is not None
            else int(row["used"] if row else 0)
        )
        available = (
            int(float(available_raw))
            if available_raw is not None
            else max(0, allowed - used)
        )
        expires = _normalize_expiry(
            expiry_raw
            if expiry_raw is not None
            else (row["expires_ms"] if row else None),
            now_ms,
        )
        started = int(row["window_started_ms"] if row else now_ms)
        if now_ms >= expires:
            started = now_ms
        connection.execute(
            """
            INSERT INTO provider_budget(
                provider, allowed, used, available, window_started_ms,
                expires_ms, updated_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'response-headers')
            ON CONFLICT(provider) DO UPDATE SET
                allowed=excluded.allowed,
                used=excluded.used,
                available=excluded.available,
                window_started_ms=excluded.window_started_ms,
                expires_ms=excluded.expires_ms,
                updated_at=excluded.updated_at,
                source=excluded.source
            """,
            (
                provider,
                max(1, allowed),
                max(0, used),
                max(0, available),
                started,
                expires,
                now_iso(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    _write_status(budget_snapshot(provider))


def _cache_key(provider: str, endpoint: str, params: Mapping[str, Any]) -> str:
    normalized = json.dumps(
        {
            "provider": provider,
            "endpoint": endpoint,
            "params": dict(sorted(params.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cache_policy(path: str, params: Mapping[str, Any]) -> tuple[int, int]:
    """Return fresh TTL and stale-if-error TTL in seconds."""
    if path == "/markets/history":
        interval = str(params.get("interval") or "daily")
        return (900, 86_400) if interval == "daily" else (300, 3_600)
    if path == "/markets/options/expirations":
        return 1_800, 21_600
    if path == "/markets/options/chains":
        return 8, 0
    if path == "/markets/timesales":
        return 25, 0
    if path == "/markets/calendar":
        return 21_600, 86_400
    if path == "/markets/quotes":
        return 1, 0
    return 0, 0


def cache_get(
    provider: str,
    endpoint: str,
    params: Mapping[str, Any],
    *,
    allow_stale: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    fresh_ttl, _ = _cache_policy(endpoint, params)
    if fresh_ttl <= 0:
        return None, "disabled"
    key = _cache_key(provider, endpoint, params)
    now_ms = int(time.time() * 1000)
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM response_cache WHERE cache_key=?", (key,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None, "miss"
    limit = int(row["stale_until_ms"] if allow_stale else row["expires_ms"])
    if now_ms > limit:
        return None, "expired"
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "invalid"
    status = "stale" if now_ms > int(row["expires_ms"]) else "hit"
    return payload if isinstance(payload, dict) else None, status


def cache_put(
    provider: str,
    endpoint: str,
    params: Mapping[str, Any],
    payload: dict[str, Any],
) -> None:
    fresh_ttl, stale_ttl = _cache_policy(endpoint, params)
    if fresh_ttl <= 0:
        return
    key = _cache_key(provider, endpoint, params)
    now_ms = int(time.time() * 1000)
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO response_cache(
                cache_key, provider, endpoint, payload_json, created_ms,
                expires_ms, stale_until_ms, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json=excluded.payload_json,
                created_ms=excluded.created_ms,
                expires_ms=excluded.expires_ms,
                stale_until_ms=excluded.stale_until_ms,
                updated_at=excluded.updated_at
            """,
            (
                key,
                provider,
                endpoint,
                json.dumps(payload, separators=(",", ":"), default=str),
                now_ms,
                now_ms + fresh_ttl * 1000,
                now_ms + max(fresh_ttl, stale_ttl) * 1000,
                now_iso(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _log_request(
    endpoint: str,
    *,
    status_code: int | None,
    elapsed_ms: int | None,
    cache_status: str,
    error: str = "",
) -> None:
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO provider_request_log(
                provider, endpoint, requested_at, status_code,
                elapsed_ms, cache_status, error
            ) VALUES ('tradier', ?, ?, ?, ?, ?, ?)
            """,
            (
                endpoint,
                now_iso(),
                status_code,
                elapsed_ms,
                cache_status,
                error[:500],
            ),
        )
        connection.execute(
            """
            DELETE FROM provider_request_log
            WHERE id IN (
                SELECT id FROM provider_request_log
                ORDER BY id DESC LIMIT -1 OFFSET 5000
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def recent_metrics(limit: int = 300) -> dict[str, Any]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT status_code, elapsed_ms, cache_status, error
            FROM provider_request_log ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
    finally:
        connection.close()
    network = [
        row for row in rows if row["cache_status"] in {"network", "error"}
    ]
    elapsed = [
        int(row["elapsed_ms"])
        for row in network
        if row["elapsed_ms"] is not None
    ]
    return {
        "samples": len(rows),
        "network_requests": len(network),
        "cache_hits": sum(row["cache_status"] == "hit" for row in rows),
        "stale_fallbacks": sum(
            row["cache_status"] == "stale-fallback" for row in rows
        ),
        "errors": sum(bool(row["error"]) for row in rows),
        "average_network_ms": (
            round(sum(elapsed) / len(elapsed), 1) if elapsed else None
        ),
        "budget": budget_snapshot(),
    }


def _install_tradier_get(ford_scan: Any) -> None:
    original_error = ford_scan.TradierError

    def tradier_get(
        path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not ford_scan.TRADIER_TOKEN:
            raise original_error("TRADIER_TOKEN is not configured")
        request_params = params or {}
        cached, cache_status = cache_get("tradier", path, request_params)
        if cached is not None:
            _log_request(
                path, status_code=200, elapsed_ms=0, cache_status=cache_status
            )
            return cached

        reserve("tradier")
        started = time.monotonic()
        response: requests.Response | None = None
        try:
            response = ford_scan.SESSION.get(
                f"{ford_scan.TRADIER_BASE_URL}{path}",
                params=request_params,
                headers={
                    "Authorization": f"Bearer {ford_scan.TRADIER_TOKEN}",
                    "Accept": "application/json",
                },
                timeout=25,
            )
            record_headers(response.headers, "tradier")
            elapsed_ms = round((time.monotonic() - started) * 1000)
            if not response.ok:
                body = response.text[:500].replace(
                    ford_scan.TRADIER_TOKEN, "[REDACTED]"
                )
                raise original_error(
                    f"Tradier HTTP {response.status_code} for {path}: {body}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise original_error(
                    f"Tradier returned invalid JSON for {path}"
                ) from exc
            if not isinstance(payload, dict):
                raise original_error(
                    f"Tradier returned an unexpected payload for {path}"
                )
            cache_put("tradier", path, request_params, payload)
            _log_request(
                path,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                cache_status="network",
            )
            return payload
        except (requests.RequestException, original_error) as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            stale, stale_status = cache_get(
                "tradier", path, request_params, allow_stale=True
            )
            if stale is not None and stale_status == "stale":
                _log_request(
                    path,
                    status_code=(
                        response.status_code if response is not None else None
                    ),
                    elapsed_ms=elapsed_ms,
                    cache_status="stale-fallback",
                    error=f"{type(exc).__name__}: {exc}",
                )
                return stale
            _log_request(
                path,
                status_code=(response.status_code if response is not None else None),
                elapsed_ms=elapsed_ms,
                cache_status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            if isinstance(exc, original_error):
                raise
            raise original_error(f"Tradier request failed: {exc}") from exc

    ford_scan.tradier_get = tradier_get


def _install_chain_derived_strikes(ford_scan: Any) -> None:
    def get_strikes(symbol: str, expiration: str) -> list[float]:
        values: list[float] = []
        for option in ford_scan.get_chain(symbol, expiration):
            strike = ford_scan.as_float(option.get("strike"))
            if strike is not None:
                values.append(float(strike))
        return sorted(set(values))

    ford_scan.get_strikes = get_strikes


def install(ford_scan_module: Any | None = None) -> None:
    """Install rate-aware Tradier access once per process."""
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        if ford_scan_module is None:
            import ford_scan as ford_scan_module

        _install_tradier_get(ford_scan_module)
        _install_chain_derived_strikes(ford_scan_module)
        ford_scan_module.TRADIER_RESOURCE_RUNTIME = "shared-budget-cache-v1"
        _INSTALLED = True


__all__ = [
    "ProviderBudgetError",
    "budget_snapshot",
    "cache_get",
    "cache_put",
    "install",
    "recent_metrics",
    "record_headers",
    "reserve",
]
