from __future__ import annotations

import unittest

import resource_compute_runtime


class ResourceComputeRuntimeTests(unittest.TestCase):
    def test_grouped_analysis_is_review_only_and_deterministic(self) -> None:
        trades = [
            {
                "ticker": "F",
                "strategy": "regular-call",
                "direction": "call",
                "regime": "BULLISH / CONTROLLED",
                "pnl": 20,
                "mfe": 25,
                "mae": -5,
            },
            {
                "ticker": "F",
                "strategy": "regular-call",
                "direction": "call",
                "regime": "BULLISH / CONTROLLED",
                "pnl": -15,
                "mfe": 3,
                "mae": -18,
            },
            {
                "ticker": "SOFI",
                "strategy": "swing-put",
                "direction": "put",
                "regime": "BEARISH / CONTROLLED",
                "pnl": 30,
                "mfe": 40,
                "mae": -4,
            },
        ]
        first = resource_compute_runtime.analyze(
            {"source_digest": "abc", "trades": trades}
        )
        second = resource_compute_runtime.analyze(
            {"source_digest": "abc", "trades": trades}
        )
        self.assertEqual(first["trade_count"], 3)
        self.assertEqual(first["overall"]["total_pnl"], 35)
        self.assertAlmostEqual(first["overall"]["win_rate_pct"], 66.6666666667)
        self.assertEqual(
            first["overall"]["pnl_mean_95_low"],
            second["overall"]["pnl_mean_95_low"],
        )
        self.assertIn("no scanner", first["contract"])
        strategies = {
            item["label"]: item
            for item in first["groups"]["strategy"]
        }
        self.assertEqual(
            strategies["strategy:regular-call"]["count"], 2
        )


if __name__ == "__main__":
    unittest.main()
