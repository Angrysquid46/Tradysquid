"""Real test for market_data.get_quote's priority forwarding - found
missing during Phase 15 AXIOM launch-readiness review: get_quotes/
get_expirations/get_chain all gained a `priority` kwarg forwarded to
tradier_get's self-gating budget check (Phase 14), but get_quote didn't,
so any caller wanting a specific priority tier silently got the default
instead."""

from __future__ import annotations

import market_api_budget
import market_data


def test_get_quote_forwards_priority_to_tradier_get(monkeypatch):
    seen_priority = {}

    def fake_tradier_get(path, params=None, *, priority=None, cache_ttl_seconds=0):
        seen_priority["value"] = priority
        return {"quotes": {"quote": {"symbol": "SPY", "bid": 1.0, "ask": 1.1}}}

    monkeypatch.setattr(market_data, "tradier_get", fake_tradier_get)
    market_data.get_quote("SPY", priority=market_api_budget.PRIORITY_ENTRY_CRITICAL_DATA)
    assert seen_priority["value"] == market_api_budget.PRIORITY_ENTRY_CRITICAL_DATA


def test_get_quote_defaults_to_secondary_context_priority(monkeypatch):
    seen_priority = {}

    def fake_tradier_get(path, params=None, *, priority=None, cache_ttl_seconds=0):
        seen_priority["value"] = priority
        return {"quotes": {"quote": {"symbol": "SPY", "bid": 1.0, "ask": 1.1}}}

    monkeypatch.setattr(market_data, "tradier_get", fake_tradier_get)
    market_data.get_quote("SPY")
    assert seen_priority["value"] == market_api_budget.PRIORITY_SECONDARY_CONTEXT
