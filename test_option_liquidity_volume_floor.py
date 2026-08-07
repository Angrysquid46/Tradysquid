import unittest

import ford_scan


def _option(**overrides):
    base = {
        "bid": 0.60,
        "ask": 0.65,
        "open_interest": 500,
        "volume": 200,
    }
    base.update(overrides)
    return base


class OptionLiquidityVolumeFloorTests(unittest.TestCase):
    def test_rejects_a_contract_with_almost_no_same_day_trading(self) -> None:
        option = _option(volume=2)
        self.assertFalse(ford_scan.option_has_liquidity(option))

    def test_rejects_a_contract_with_stale_open_interest_only(self) -> None:
        # High open interest can just mean a position has sat unchanged for
        # weeks. Real same-day volume is required too.
        option = _option(open_interest=200, volume=500)
        self.assertFalse(ford_scan.option_has_liquidity(option))

    def test_accepts_a_contract_with_real_same_day_trading(self) -> None:
        option = _option(volume=200, open_interest=500)
        self.assertTrue(ford_scan.option_has_liquidity(option))

    def test_volume_and_open_interest_floors_are_genuinely_high(self) -> None:
        # Set from real chain depth (see ford_scan.py comment), not a
        # trivial "not literally zero" bar. Regression guard against
        # silently dropping these back down to a near-worthless floor.
        self.assertGreaterEqual(ford_scan.MIN_OPTION_VOLUME, 200)
        self.assertGreaterEqual(ford_scan.MIN_OPEN_INTEREST, 500)


if __name__ == "__main__":
    unittest.main()
