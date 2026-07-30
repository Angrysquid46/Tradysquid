from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import local_information_engine as engine
import register_discord_commands


class InformationEngineTests(unittest.TestCase):
    def test_exponential_moving_average(self) -> None:
        values = [float(value) for value in range(1, 31)]
        ema = engine.exponential_moving_average(values, 12)
        self.assertIsNotNone(ema)
        self.assertGreater(ema, 20)
        self.assertLess(ema, 30)

    def test_average_true_range(self) -> None:
        history = [
            {
                "high": 10 + index * 0.1,
                "low": 9 + index * 0.1,
                "close": 9.5 + index * 0.1,
            }
            for index in range(20)
        ]
        self.assertAlmostEqual(engine.average_true_range(history) or 0, 1.0)

    def test_option_quality_marks_liquid_contract(self) -> None:
        option = {
            "symbol": "F260821C00015000",
            "option_type": "call",
            "strike": 15,
            "expiration_date": "2026-08-21",
            "bid": 1.00,
            "ask": 1.05,
            "open_interest": 1000,
            "volume": 250,
            "greeks": {
                "delta": 0.65,
                "theta": -0.02,
                "mid_iv": 0.35,
            },
        }
        result = engine.option_quality(option, 15.50)
        self.assertTrue(result["liquidity_pass"])
        self.assertEqual(result["open_interest"], 1000)
        self.assertGreater(result["quality_score"], 50)

    def test_sqlite_state_and_observation_round_trip(self) -> None:
        original = engine.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            engine.DB_PATH = Path(temp) / "test.db"
            connection = engine.connect_db()
            try:
                engine.set_state(connection, "example", "value")
                engine.store_observation(connection, "market", {"price": 15.25})
                self.assertEqual(engine.get_state(connection, "example"), "value")
            finally:
                connection.close()
            latest = engine.latest_observation("market")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["payload"]["price"], 15.25)
        engine.DB_PATH = original

    def test_registered_command_names_are_unique(self) -> None:
        names = [command["name"] for command in register_discord_commands.COMMANDS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("help", names)
        self.assertIn("chain", names)
        self.assertIn("status", names)


if __name__ == "__main__":
    unittest.main()
