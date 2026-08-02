"""Additional no-cost public-data sources and worker-side cache policy.

These sources are useful but less universal than SEC/Finnhub/Cboe. They are
installed as non-blocking enrichments around the worker's existing handlers:
ClinicalTrials.gov for life-science trial changes, FederalRegister.gov for
regulatory mentions, the legacy public GDELT DOC endpoint for broad news
coverage, and Treasury Fiscal Data for sovereign-rate context. Large or slow
public responses are cached locally so one hourly task does not become one
hourly act of needless repetition.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Callable

import resource_mesh

_INSTALLED = False


def _company_name(result: dict[str, Any], symbol: str) -> str:
    providers = result.get("providers") or {}
    sec = (providers.get("sec") or {}).get("data") or {}
    finnhub = (providers.get("finnhub") or {}).get("data") or {}
    profile = finnhub.get("profile") or {}
    return str(
        sec.get("entity_name")
        or profile.get("name")
        or symbol
    ).strip()


def _cache_key(prefix: str, value: str = "") -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else "global"
    return f"worker-{prefix}-{digest}.json"


def _cached(
    name: str,
    max_age_seconds: int,
    callback: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    existing = resource_mesh.load_cache(name, max_age_seconds=max_age_seconds)
    if existing is not None:
        return existing
    payload = callback()
    resource_mesh.save_cache(name, payload)
    return payload


def install(worker: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_ticker = worker.ticker_enrichment
    original_macro = worker.macro_refresh
    original_sec = worker.sec_enrichment
    original_alpha = worker.alpha_vantage_overview
    original_cboe = worker.cboe_market_context
    original_fred = worker.fred_macro
    original_bls = worker.bls_macro
    original_eia = worker.eia_macro

    # SEC company facts are large and usually change only after a filing. Six
    # hours preserves freshness without downloading the same XBRL payload for
    # every hourly enrichment task.
    worker.sec_enrichment = lambda symbol: _cached(
        _cache_key("sec", symbol.upper()),
        6 * 3600,
        lambda: original_sec(symbol),
    )
    worker.alpha_vantage_overview = lambda symbol: _cached(
        _cache_key("alpha-overview", symbol.upper()),
        24 * 3600,
        lambda: original_alpha(symbol),
    )
    worker.cboe_market_context = lambda: _cached(
        _cache_key("cboe"), 15 * 60, original_cboe
    )
    worker.fred_macro = lambda: _cached(
        _cache_key("fred"), 3600, original_fred
    )
    worker.bls_macro = lambda: _cached(
        _cache_key("bls"), 3600, original_bls
    )
    worker.eia_macro = lambda: _cached(
        _cache_key("eia"), 3600, original_eia
    )

    def clinical_trials(company: str) -> dict[str, Any]:
        def request() -> dict[str, Any]:
            if not worker.wait_quota(
                "clinicaltrials-second",
                limit=3,
                window_seconds=1,
                max_wait_seconds=5,
            ):
                raise worker.WorkerProviderError(
                    "ClinicalTrials.gov request budget did not reset in time"
                )
            return worker.request_json(
                "GET",
                "https://clinicaltrials.gov/api/v2/studies",
                provider="ClinicalTrials.gov",
                params={
                    "query.spons": company,
                    "format": "json",
                    "pageSize": 20,
                    "sort": "LastUpdatePostDate:desc",
                    "countTotal": "true",
                },
            )

        return _cached(_cache_key("clinical-trials", company), 6 * 3600, request)

    def federal_register(company: str) -> dict[str, Any]:
        def request() -> dict[str, Any]:
            if not worker.wait_quota(
                "federal-register-second",
                limit=3,
                window_seconds=1,
                max_wait_seconds=5,
            ):
                raise worker.WorkerProviderError(
                    "Federal Register request budget did not reset in time"
                )
            return worker.request_json(
                "GET",
                "https://www.federalregister.gov/api/v1/documents.json",
                provider="Federal Register",
                params={
                    "per_page": 20,
                    "order": "newest",
                    "conditions[term]": company,
                },
            )

        return _cached(_cache_key("federal-register", company), 6 * 3600, request)

    def gdelt_news(company: str) -> dict[str, Any]:
        def request() -> dict[str, Any]:
            if not worker.wait_quota(
                "gdelt-second",
                limit=1,
                window_seconds=2,
                max_wait_seconds=6,
            ):
                raise worker.WorkerProviderError(
                    "GDELT request budget did not reset in time"
                )
            return worker.request_json(
                "GET",
                "https://api.gdeltproject.org/api/v2/doc/doc",
                provider="GDELT DOC",
                params={
                    "query": f'"{company}" sourcelang:english',
                    "mode": "artlist",
                    "maxrecords": 25,
                    "format": "json",
                    "timespan": "1week",
                    "sort": "hybridrel",
                },
            )

        return _cached(_cache_key("gdelt", company), 3600, request)

    def treasury_context() -> dict[str, Any]:
        def request() -> dict[str, Any]:
            if not worker.wait_quota(
                "treasury-second",
                limit=3,
                window_seconds=1,
                max_wait_seconds=5,
            ):
                raise worker.WorkerProviderError(
                    "Treasury Fiscal Data request budget did not reset in time"
                )
            start = (date.today() - timedelta(days=45)).isoformat()
            return worker.request_json(
                "GET",
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates",
                provider="Treasury Fiscal Data",
                params={
                    "filter": f"record_date:gte:{start}",
                    "sort": "-record_date",
                    "page[size]": 50,
                },
            )

        return _cached(_cache_key("treasury"), 6 * 3600, request)

    def ticker_enrichment(payload: dict[str, Any]) -> dict[str, Any]:
        result = original_ticker(payload)
        symbol = str(result.get("symbol") or payload.get("symbol") or "").upper()
        company = _company_name(result, symbol)
        providers = result.setdefault("providers", {})
        providers["clinical_trials"] = worker._provider_result(
            lambda: clinical_trials(company)
        )
        providers["federal_register"] = worker._provider_result(
            lambda: federal_register(company)
        )
        providers["gdelt"] = worker._provider_result(
            lambda: gdelt_news(company)
        )
        result["company_query"] = company
        return result

    def macro_refresh(payload: dict[str, Any]) -> dict[str, Any]:
        result = original_macro(payload)
        result.setdefault("providers", {})["treasury"] = worker._provider_result(
            treasury_context
        )
        return result

    worker.ticker_enrichment = ticker_enrichment
    worker.macro_refresh = macro_refresh
    worker.HANDLERS["ticker-enrichment"] = ticker_enrichment
    worker.HANDLERS["macro-refresh"] = macro_refresh
    worker.RESOURCE_WORKER_EXTENSIONS = (
        "cached-clinicaltrials-federal-register-gdelt-treasury-v2"
    )
    _INSTALLED = True


__all__ = ["install"]
