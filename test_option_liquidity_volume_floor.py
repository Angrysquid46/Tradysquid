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

    def test_accepts_a_contract_with_real_same_day_trading(self) -> None:
        option = _option(volume=200)
        self.assertTrue(ford_scan.option_has_liquidity(option))

    def test_volume_floor_is_meaningfully_above_one(self) -> None:
        # A floor of 1 lets contracts with essentially no real trading
        # through - open interest alone doesn't prove today's quote is
        # tradeable. Regression guard against silently dropping this back
        # down to a value that stops filtering anything out.
        self.assertGreaterEqual(ford_scan.MIN_OPTION_VOLUME, 25)


if __name__ == "__main__":
    unittest.main()
