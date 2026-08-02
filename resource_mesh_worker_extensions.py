"""Additional no-cost public-data sources for the resource worker.

These sources are useful but less universal than SEC/Finnhub/Cboe. They are
installed as non-blocking enrichments around the worker's existing handlers:
ClinicalTrials.gov for life-science trial changes, FederalRegister.gov for
regulatory mentions, the legacy public GDELT DOC endpoint for broad news
coverage, and Treasury Fiscal Data for sovereign-rate context.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

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


def install(worker: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_ticker = worker.ticker_enrichment
    original_macro = worker.macro_refresh

    def clinical_trials(company: str) -> dict[str, Any]:
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

    def federal_register(company: str) -> dict[str, Any]:
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

    def gdelt_news(company: str) -> dict[str, Any]:
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

    def treasury_context() -> dict[str, Any]:
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
        "clinicaltrials-federal-register-gdelt-treasury-v1"
    )
    _INSTALLED = True


__all__ = ["install"]
