"""Optional second-PC worker for Tradysquid's free resource mesh.

The worker never reads or needs the Tradier token, Discord bot token, ngrok
credential, or production trade files. It consumes sanitized JSON tasks from a
shared folder and returns enrichment results. All providers are optional: the
worker automatically uses the free keys that are configured and records why a
provider was skipped when a key is absent or its quota is exhausted.
"""

from __future__ import annotations

import csv
import io
import os
import socket
import sqlite3
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

import resource_mesh

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
QUOTA_DB = STATE_DIR / "free-provider-quotas.db"
WORKER_ID = os.environ.get("RESOURCE_WORKER_ID", "").strip() or (
    f"resource-worker-{socket.gethostname().casefold()}"
)
POLL_SECONDS = max(
    1, int(os.environ.get("RESOURCE_WORKER_POLL_SECONDS", "3"))
)
HTTP_TIMEOUT = max(
    5, int(os.environ.get("RESOURCE_WORKER_HTTP_TIMEOUT", "25"))
)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Tradysquid-Resource-Worker/1.0"})


class WorkerProviderError(RuntimeError):
    pass


def load_worker_env() -> None:
    """Load worker-only settings without requiring production credentials."""
    global WORKER_ID, POLL_SECONDS, HTTP_TIMEOUT
    for path in (ROOT / ".env.worker", ROOT / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip())
    WORKER_ID = os.environ.get("RESOURCE_WORKER_ID", "").strip() or (
        f"resource-worker-{socket.gethostname().casefold()}"
    )
    POLL_SECONDS = max(
        1, int(os.environ.get("RESOURCE_WORKER_POLL_SECONDS", "3"))
    )
    HTTP_TIMEOUT = max(
        5, int(os.environ.get("RESOURCE_WORKER_HTTP_TIMEOUT", "25"))
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _quota_connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(QUOTA_DB, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS quotas (
            bucket TEXT PRIMARY KEY,
            window_start INTEGER NOT NULL,
            window_seconds INTEGER NOT NULL,
            used INTEGER NOT NULL,
            limit_value INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    return connection


def reserve_quota(
    bucket: str,
    *,
    limit: int,
    window_seconds: int,
    cost: int = 1,
) -> bool:
    current = int(time.time())
    connection = _quota_connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM quotas WHERE bucket=?", (bucket,)
        ).fetchone()
        if row is None or current - int(row["window_start"]) >= int(
            row["window_seconds"]
        ):
            window_start = current
            used = 0
        else:
            window_start = int(row["window_start"])
            used = int(row["used"])
        if used + cost > limit:
            connection.rollback()
            return False
        used += cost
        connection.execute(
            """
            INSERT INTO quotas(
                bucket, window_start, window_seconds, used,
                limit_value, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(bucket) DO UPDATE SET
                window_start=excluded.window_start,
                window_seconds=excluded.window_seconds,
                used=excluded.used,
                limit_value=excluded.limit_value,
                updated_at=excluded.updated_at
            """,
            (bucket, window_start, window_seconds, used, limit, now_iso()),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def wait_quota(
    bucket: str,
    *,
    limit: int,
    window_seconds: int,
    cost: int = 1,
    max_wait_seconds: int = 75,
) -> bool:
    deadline = time.monotonic() + max(1, max_wait_seconds)
    while True:
        if reserve_quota(
            bucket,
            limit=limit,
            window_seconds=window_seconds,
            cost=cost,
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(
            min(max(window_seconds / max(limit, 1), 0.1), 1.0)
        )


def _redact(text: str) -> str:
    output = str(text)
    for name in (
        "FINNHUB_API_KEY",
        "TWELVE_DATA_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "FRED_API_KEY",
        "BLS_API_KEY",
        "EIA_API_KEY",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            output = output.replace(value, "[REDACTED]")
    return output


def request_json(
    method: str,
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    for attempt in range(4):
        try:
            response = SESSION.request(
                method,
                url,
                params=params,
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            if attempt == 3:
                raise WorkerProviderError(
                    f"{provider} request failed: {exc}"
                ) from exc
            time.sleep(2**attempt)
            continue
        if response.status_code == 429 and attempt < 3:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = max(1.0, min(float(retry_after), 60.0))
            except (TypeError, ValueError):
                delay = 2**attempt
            time.sleep(delay)
            continue
        if response.status_code >= 500 and attempt < 3:
            time.sleep(2**attempt)
            continue
        if not response.ok:
            raise WorkerProviderError(
                _redact(
                    f"{provider} HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            )
        try:
            return response.json()
        except ValueError as exc:
            raise WorkerProviderError(
                f"{provider} returned invalid JSON"
            ) from exc
    raise WorkerProviderError(f"{provider} retries exhausted")


def request_text(url: str, *, provider: str) -> str:
    for attempt in range(4):
        try:
            response = SESSION.get(url, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == 3:
                raise WorkerProviderError(
                    f"{provider} request failed: {exc}"
                ) from exc
            time.sleep(2**attempt)
            continue
        if response.status_code >= 500 and attempt < 3:
            time.sleep(2**attempt)
            continue
        if not response.ok:
            raise WorkerProviderError(
                f"{provider} HTTP {response.status_code}"
            )
        return response.text
    raise WorkerProviderError(f"{provider} retries exhausted")


def _provider_result(callback: Callable[[], Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        data = callback()
        return {
            "status": "OK",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": _redact(f"{type(exc).__name__}: {exc}")[:1000],
        }


def _skip(reason: str) -> dict[str, Any]:
    return {"status": "SKIPPED", "reason": reason}


def finnhub_enrichment(
    symbol: str, start: date, end: date
) -> dict[str, Any]:
    token = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not token:
        raise WorkerProviderError("FINNHUB_API_KEY is not configured")
    if not wait_quota(
        "finnhub-minute", limit=55, window_seconds=60, cost=4
    ):
        raise WorkerProviderError(
            "Finnhub free minute quota did not reset in time"
        )
    base = "https://finnhub.io/api/v1"
    common = {"token": token}
    return {
        "profile": request_json(
            "GET",
            f"{base}/stock/profile2",
            provider="Finnhub",
            params={**common, "symbol": symbol},
        ),
        "quote": request_json(
            "GET",
            f"{base}/quote",
            provider="Finnhub",
            params={**common, "symbol": symbol},
        ),
        "news": request_json(
            "GET",
            f"{base}/company-news",
            provider="Finnhub",
            params={
                **common,
                "symbol": symbol,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        )[:20],
        "earnings_calendar": request_json(
            "GET",
            f"{base}/calendar/earnings",
            provider="Finnhub",
            params={
                **common,
                "symbol": symbol,
                "from": start.isoformat(),
                "to": (end + timedelta(days=45)).isoformat(),
            },
        ),
    }


def _sec_headers() -> dict[str, str]:
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise WorkerProviderError("SEC_USER_AGENT is not configured")
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


def sec_ticker_map() -> dict[str, int]:
    cached = resource_mesh.load_cache(
        "sec-company-tickers.json", max_age_seconds=86_400
    )
    if cached and isinstance(cached.get("symbols"), dict):
        return {
            str(key): int(value)
            for key, value in cached["symbols"].items()
        }
    wait_quota(
        "sec-second", limit=8, window_seconds=1, max_wait_seconds=5
    )
    payload = request_json(
        "GET",
        "https://www.sec.gov/files/company_tickers.json",
        provider="SEC",
        headers=_sec_headers(),
    )
    symbols = {
        str(item.get("ticker") or "").upper(): int(
            item.get("cik_str") or 0
        )
        for item in payload.values()
        if isinstance(item, dict)
        and item.get("ticker")
        and item.get("cik_str")
    }
    resource_mesh.save_cache(
        "sec-company-tickers.json",
        {"updated_at": now_iso(), "symbols": symbols},
    )
    return symbols


def _latest_fact(
    facts: dict[str, Any], names: tuple[str, ...]
) -> dict[str, Any] | None:
    us_gaap = facts.get("us-gaap") or {}
    for name in names:
        fact = us_gaap.get(name) or {}
        units = fact.get("units") or {}
        rows: list[dict[str, Any]] = []
        for values in units.values():
            if isinstance(values, list):
                rows.extend(
                    item for item in values if isinstance(item, dict)
                )
        rows = [
            item
            for item in rows
            if item.get("val") is not None and item.get("end")
        ]
        if not rows:
            continue
        rows.sort(
            key=lambda item: (
                str(item.get("end")),
                str(item.get("filed")),
            ),
            reverse=True,
        )
        item = rows[0]
        unit = ""
        for candidate_unit, values in units.items():
            if item in values:
                unit = candidate_unit
                break
        return {
            "concept": name,
            "value": item.get("val"),
            "unit": unit,
            "period_end": item.get("end"),
            "filed": item.get("filed"),
            "form": item.get("form"),
            "frame": item.get("frame"),
        }
    return None


def sec_enrichment(symbol: str) -> dict[str, Any]:
    cik = sec_ticker_map().get(symbol)
    if not cik:
        raise WorkerProviderError(f"SEC CIK was not found for {symbol}")
    wait_quota(
        "sec-second",
        limit=8,
        window_seconds=1,
        cost=2,
        max_wait_seconds=5,
    )
    headers = _sec_headers()
    submissions = request_json(
        "GET",
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
        provider="SEC",
        headers=headers,
    )
    companyfacts = request_json(
        "GET",
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        provider="SEC",
        headers=headers,
    )
    recent = (submissions.get("filings") or {}).get("recent") or {}
    filings: list[dict[str, Any]] = []
    forms = recent.get("form") or []
    accession = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    primary_documents = recent.get("primaryDocument") or []
    for index, form in enumerate(forms[:40]):
        if form not in {
            "8-K",
            "10-Q",
            "10-K",
            "6-K",
            "20-F",
            "DEF 14A",
        }:
            continue
        number = str(accession[index]) if index < len(accession) else ""
        document = (
            str(primary_documents[index])
            if index < len(primary_documents)
            else ""
        )
        compact = number.replace("-", "")
        filings.append(
            {
                "form": form,
                "filing_date": (
                    filing_dates[index]
                    if index < len(filing_dates)
                    else ""
                ),
                "accession": number,
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{compact}/{document}"
                    if number and document
                    else ""
                ),
            }
        )
        if len(filings) >= 12:
            break
    facts = companyfacts.get("facts") or {}
    selected = {
        "revenue": _latest_fact(
            facts,
            (
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues",
                "SalesRevenueNet",
            ),
        ),
        "net_income": _latest_fact(
            facts, ("NetIncomeLoss", "ProfitLoss")
        ),
        "assets": _latest_fact(facts, ("Assets",)),
        "liabilities": _latest_fact(
            facts, ("Liabilities", "LiabilitiesCurrent")
        ),
        "cash": _latest_fact(
            facts,
            (
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            ),
        ),
        "eps_diluted": _latest_fact(
            facts, ("EarningsPerShareDiluted",)
        ),
        "operating_cash_flow": _latest_fact(
            facts, ("NetCashProvidedByUsedInOperatingActivities",)
        ),
    }
    return {
        "cik": cik,
        "entity_name": companyfacts.get("entityName")
        or submissions.get("name"),
        "sic": submissions.get("sic"),
        "sic_description": submissions.get("sicDescription"),
        "filings": filings,
        "facts": {
            key: value for key, value in selected.items() if value is not None
        },
    }


def alpha_vantage_overview(symbol: str) -> dict[str, Any]:
    token = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not token:
        raise WorkerProviderError(
            "ALPHA_VANTAGE_API_KEY is not configured"
        )
    if not reserve_quota(
        "alpha-vantage-day", limit=25, window_seconds=86_400
    ):
        raise WorkerProviderError(
            "Alpha Vantage free daily quota is exhausted"
        )
    payload = request_json(
        "GET",
        "https://www.alphavantage.co/query",
        provider="Alpha Vantage",
        params={
            "function": "OVERVIEW",
            "symbol": symbol,
            "apikey": token,
        },
    )
    if payload.get("Information") or payload.get("Note"):
        raise WorkerProviderError(
            str(payload.get("Information") or payload.get("Note"))
        )
    return payload


def twelve_data_enrichment(symbol: str) -> dict[str, Any]:
    token = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
    if not token:
        raise WorkerProviderError("TWELVE_DATA_API_KEY is not configured")
    if not wait_quota(
        "twelve-data-minute", limit=7, window_seconds=60
    ):
        raise WorkerProviderError(
            "Twelve Data minute quota did not reset in time"
        )
    if not reserve_quota(
        "twelve-data-day", limit=780, window_seconds=86_400
    ):
        raise WorkerProviderError("Twelve Data daily credits are exhausted")
    return request_json(
        "GET",
        "https://api.twelvedata.com/press_releases",
        provider="Twelve Data",
        params={
            "symbol": symbol,
            "apikey": token,
            "outputsize": 10,
        },
    )


def cboe_market_context() -> dict[str, Any]:
    urls = {
        "vix": (
            "https://cdn.cboe.com/api/global/us_indices/"
            "daily_prices/VIX_History.csv"
        ),
        "vvix": (
            "https://cdn.cboe.com/api/global/us_indices/"
            "daily_prices/VVIX_History.csv"
        ),
    }
    output: dict[str, Any] = {}
    for key, url in urls.items():
        text = request_text(url, provider="Cboe")
        rows = list(csv.DictReader(io.StringIO(text)))
        if rows:
            output[key] = rows[-1]
    return output


def fred_macro() -> dict[str, Any]:
    token = os.environ.get("FRED_API_KEY", "").strip()
    if not token:
        raise WorkerProviderError("FRED_API_KEY is not configured")
    series = [
        item.strip()
        for item in os.environ.get(
            "FRED_SERIES",
            (
                "DGS10,DGS2,T10Y2,VIXCLS,BAMLH0A0HYM2,"
                "DFII10,FEDFUNDS,UNRATE,CPIAUCSL"
            ),
        ).split(",")
        if item.strip()
    ]
    output: dict[str, Any] = {}
    for series_id in series:
        if not wait_quota(
            "fred-second", limit=2, window_seconds=1, max_wait_seconds=5
        ):
            raise WorkerProviderError(
                "FRED request quota did not reset in time"
            )
        payload = request_json(
            "GET",
            "https://api.stlouisfed.org/fred/series/observations",
            provider="FRED",
            params={
                "series_id": series_id,
                "api_key": token,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            },
        )
        output[series_id] = (payload.get("observations") or [])[:5]
    return output


def bls_macro() -> dict[str, Any]:
    series = [
        item.strip()
        for item in os.environ.get(
            "BLS_SERIES", "LNS14000000,CES0000000001,CUUR0000SA0"
        ).split(",")
        if item.strip()
    ]
    key = os.environ.get("BLS_API_KEY", "").strip()
    daily_limit = 450 if key else 20
    if not reserve_quota(
        "bls-day", limit=daily_limit, window_seconds=86_400
    ):
        raise WorkerProviderError("BLS daily quota is exhausted")
    end_year = date.today().year
    payload: dict[str, Any] = {
        "seriesid": series[:50],
        "startyear": str(max(2000, end_year - 2)),
        "endyear": str(end_year),
    }
    if key:
        payload["registrationkey"] = key
    return request_json(
        "POST",
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        provider="BLS",
        payload=payload,
    )


def eia_macro() -> dict[str, Any]:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise WorkerProviderError("EIA_API_KEY is not configured")
    series = [
        item.strip()
        for item in os.environ.get(
            "EIA_SERIES_IDS",
            "PET.RWTC.D,NG.RNGWHHD.D,STEO.RGDPQ_NONOECD.M",
        ).split(",")
        if item.strip()
    ]
    output: dict[str, Any] = {}
    for series_id in series:
        if not wait_quota(
            "eia-second", limit=4, window_seconds=1, max_wait_seconds=5
        ):
            raise WorkerProviderError(
                "EIA request quota did not reset in time"
            )
        output[series_id] = request_json(
            "GET",
            f"https://api.eia.gov/v2/seriesid/{series_id}",
            provider="EIA",
            params={"api_key": key, "length": 10},
        )
    return output


def ticker_enrichment(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("ticker-enrichment task is missing symbol")
    end = date.today()
    start = end - timedelta(
        days=max(1, int(payload.get("news_days") or 5))
    )
    providers: dict[str, Any] = {}
    providers["sec"] = _provider_result(lambda: sec_enrichment(symbol))
    providers["finnhub"] = (
        _provider_result(lambda: finnhub_enrichment(symbol, start, end))
        if os.environ.get("FINNHUB_API_KEY", "").strip()
        else _skip("FINNHUB_API_KEY not configured")
    )
    providers["alpha_vantage"] = (
        _provider_result(lambda: alpha_vantage_overview(symbol))
        if os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
        else _skip("ALPHA_VANTAGE_API_KEY not configured")
    )
    providers["twelve_data"] = (
        _provider_result(lambda: twelve_data_enrichment(symbol))
        if os.environ.get("TWELVE_DATA_API_KEY", "").strip()
        else _skip("TWELVE_DATA_API_KEY not configured")
    )
    return {
        "symbol": symbol,
        "observed_at": now_iso(),
        "providers": providers,
    }


def macro_refresh(_: dict[str, Any]) -> dict[str, Any]:
    providers: dict[str, Any] = {
        "cboe": _provider_result(cboe_market_context),
        "bls": _provider_result(bls_macro),
    }
    providers["fred"] = (
        _provider_result(fred_macro)
        if os.environ.get("FRED_API_KEY", "").strip()
        else _skip("FRED_API_KEY not configured")
    )
    providers["eia"] = (
        _provider_result(eia_macro)
        if os.environ.get("EIA_API_KEY", "").strip()
        else _skip("EIA_API_KEY not configured")
    )
    return {"observed_at": now_iso(), "providers": providers}


def compute_statistics(payload: dict[str, Any]) -> dict[str, Any]:
    values = [float(value) for value in payload.get("values") or []]
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "stdev": None,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "maximum": max(values),
    }


HANDLERS: dict[
    str, Callable[[dict[str, Any]], dict[str, Any]]
] = {
    "ticker-enrichment": ticker_enrichment,
    "macro-refresh": macro_refresh,
    "compute-statistics": compute_statistics,
    "health-probe": lambda payload: {
        "echo": payload,
        "host": socket.gethostname(),
        "observed_at": now_iso(),
    },
}


def run_one(*, local_fallback: bool = False) -> bool:
    if local_fallback:
        heartbeat = resource_mesh.read_heartbeat()
        remote_id = str(heartbeat.get("worker_id") or "")
        if (
            remote_id
            and remote_id != WORKER_ID
            and resource_mesh.worker_available(max_age_seconds=90)
        ):
            return False
    claimed = resource_mesh.claim_task(WORKER_ID)
    if not claimed:
        resource_mesh.write_heartbeat(
            WORKER_ID,
            role=("local-fallback" if local_fallback else "remote-worker"),
            detail="idle",
        )
        return False
    path, task = claimed
    kind = str(task.get("kind") or "")
    handler = HANDLERS.get(kind)
    if handler is None:
        resource_mesh.finish_task(
            path,
            task,
            worker_id=WORKER_ID,
            status="ERROR",
            result={},
            error=f"No handler is registered for {kind}",
        )
        return True
    resource_mesh.write_heartbeat(
        WORKER_ID,
        role=("local-fallback" if local_fallback else "remote-worker"),
        detail=f"processing {kind} {task.get('task_id')}",
    )
    try:
        result = handler(dict(task.get("payload") or {}))
        resource_mesh.finish_task(
            path,
            task,
            worker_id=WORKER_ID,
            status="OK",
            result=result,
        )
    except Exception as exc:
        resource_mesh.finish_task(
            path,
            task,
            worker_id=WORKER_ID,
            status="ERROR",
            result={},
            error=_redact(f"{type(exc).__name__}: {exc}"),
        )
    return True


def run_forever(*, local_fallback: bool = False) -> None:
    load_worker_env()
    role = "local-fallback" if local_fallback else "remote-worker"
    print(f"Tradysquid resource worker {WORKER_ID} is running as {role}.")
    while True:
        worked = run_one(local_fallback=local_fallback)
        if not worked:
            time.sleep(POLL_SECONDS)


def main() -> int:
    load_worker_env()
    local_fallback = "--local-fallback" in sys.argv
    if "--once" in sys.argv:
        run_one(local_fallback=local_fallback)
        return 0
    run_forever(local_fallback=local_fallback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
