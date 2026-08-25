from __future__ import annotations

import market_api_budget
import market_data
import market_response_cache


class Response:
    ok = True
    headers = {
        "X-Ratelimit-Allowed": "120", "X-Ratelimit-Used": "1",
        "X-Ratelimit-Available": "119", "X-Ratelimit-Expiry": "1787593740000",
    }

    def json(self):
        return {"expirations": {"date": "2026-08-25"}}


def test_identical_factual_request_is_reused_without_second_provider_call(tmp_path, monkeypatch):
    monkeypatch.setattr(market_response_cache, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(market_api_budget, "DB_PATH", tmp_path / "budget.db")
    monkeypatch.setattr(market_data, "TRADIER_TOKEN", "redacted-test-token")
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        return Response()

    monkeypatch.setattr(market_data.SESSION, "get", get)
    first = market_data.get_expirations("SPY")
    second = market_data.get_expirations("SPY")
    assert first == second == ["2026-08-25"]
    assert len(calls) == 1


def test_cache_key_is_order_independent_for_identical_parameters():
    left = market_response_cache.cache_key("/x", {"a": 1, "b": 2})
    right = market_response_cache.cache_key("/x", {"b": 2, "a": 1})
    assert left == right
