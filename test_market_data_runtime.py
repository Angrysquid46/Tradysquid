from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest import mock

import market_data_runtime


class MarketDataRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = market_data_runtime.DB_PATH
        self.original_status = market_data_runtime.STATUS_PATH
        market_data_runtime.DB_PATH = (
            market_data_runtime.Path(self.temp.name) / "provider.db"
        )
        market_data_runtime.STATUS_PATH = (
            market_data_runtime.Path(self.temp.name) / "status.json"
        )

    def tearDown(self) -> None:
        market_data_runtime.DB_PATH = self.original_db
        market_data_runtime.STATUS_PATH = self.original_status
        self.temp.cleanup()

    def test_budget_defaults_to_configured_allowance(self) -> None:
        snapshot = market_data_runtime.budget_snapshot()
        self.assertEqual(
            snapshot["allowed"], market_data_runtime.DEFAULT_ALLOWED
        )
        self.assertEqual(snapshot["used"], 0)

    def test_response_headers_override_local_allowance(self) -> None:
        future = int(time.time()) + 60
        market_data_runtime.record_headers(
            {
                "X-Ratelimit-Allowed": "125",
                "X-Ratelimit-Used": "17",
                "X-Ratelimit-Available": "108",
                "X-Ratelimit-Expiry": str(future),
            }
        )
        snapshot = market_data_runtime.budget_snapshot()
        self.assertEqual(snapshot["allowed"], 125)
        self.assertEqual(snapshot["used"], 17)
        self.assertEqual(snapshot["available"], 108)
        self.assertEqual(snapshot["source"], "response-headers")

    def test_daily_history_cache_can_use_bounded_stale_fallback(self) -> None:
        params = {"symbol": "F", "interval": "daily"}
        payload = {"history": {"day": [{"close": 12.34}]}}
        market_data_runtime.cache_put(
            "tradier", "/markets/history", params, payload
        )
        fresh, status = market_data_runtime.cache_get(
            "tradier", "/markets/history", params
        )
        self.assertEqual(status, "hit")
        self.assertEqual(fresh, payload)

        connection = market_data_runtime._connect()
        try:
            connection.execute(
                "UPDATE response_cache SET expires_ms=?",
                (int(time.time() * 1000) - 1,),
            )
            connection.commit()
        finally:
            connection.close()
        stale, stale_status = market_data_runtime.cache_get(
            "tradier",
            "/markets/history",
            params,
            allow_stale=True,
        )
        self.assertEqual(stale_status, "stale")
        self.assertEqual(stale, payload)

    def test_live_quotes_never_use_stale_fallback(self) -> None:
        params = {"symbols": "F", "greeks": "false"}
        payload = {"quotes": {"quote": {"symbol": "F", "last": 12.3}}}
        market_data_runtime.cache_put(
            "tradier", "/markets/quotes", params, payload
        )
        connection = market_data_runtime._connect()
        try:
            connection.execute(
                "UPDATE response_cache SET expires_ms=?, stale_until_ms=?",
                (
                    int(time.time() * 1000) - 1,
                    int(time.time() * 1000) - 1,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        stale, status = market_data_runtime.cache_get(
            "tradier", "/markets/quotes", params, allow_stale=True
        )
        self.assertIsNone(stale)
        self.assertEqual(status, "expired")


if __name__ == "__main__":
    unittest.main()
