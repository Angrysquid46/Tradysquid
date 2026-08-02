from __future__ import annotations

import tempfile
import unittest

import iv_history_runtime


class IvHistoryRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = iv_history_runtime.Path(self.temp.name)
        self.original_db = iv_history_runtime.DB_PATH
        self.original_status = iv_history_runtime.STATUS_PATH
        self.original_minimum = iv_history_runtime.MIN_IV_SAMPLES
        iv_history_runtime.DB_PATH = root / "iv.db"
        iv_history_runtime.STATUS_PATH = root / "status.json"
        iv_history_runtime.MIN_IV_SAMPLES = 5

    def tearDown(self) -> None:
        iv_history_runtime.DB_PATH = self.original_db
        iv_history_runtime.STATUS_PATH = self.original_status
        iv_history_runtime.MIN_IV_SAMPLES = self.original_minimum
        self.temp.cleanup()

    def test_rank_and_percentile_require_real_observations(self) -> None:
        collecting = iv_history_runtime.metrics("F", 0.40)
        self.assertTrue(collecting["collecting"])
        self.assertIsNone(collecting["iv_rank"])

        connection = iv_history_runtime._connect()
        try:
            for index, value in enumerate((0.20, 0.30, 0.40, 0.50, 0.60), start=1):
                connection.execute(
                    """
                    INSERT INTO daily_iv(
                        symbol, session_date, observed_at, representative_iv,
                        expiration, contract_count
                    ) VALUES ('F', ?, ?, ?, '', 10)
                    """,
                    (f"2026-01-{index:02d}", f"2026-01-{index:02d}T12:00:00-06:00", value),
                )
            connection.commit()
        finally:
            connection.close()

        result = iv_history_runtime.metrics("F", 0.50)
        self.assertFalse(result["collecting"])
        self.assertEqual(result["iv_rank"], 75.0)
        self.assertEqual(result["iv_percentile"], 80.0)

    def test_realized_volatility_uses_log_returns(self) -> None:
        history = [
            {"date": f"2026-01-{index:02d}", "close": 100 + index}
            for index in range(1, 25)
        ]
        value = iv_history_runtime.realized_volatility(history, period=20)
        self.assertIsNotNone(value)
        self.assertGreater(value, 0)


if __name__ == "__main__":
    unittest.main()
