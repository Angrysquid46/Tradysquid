from tradysquid.market.regime import classify_regime
from tradysquid.core.enums import Regime
def bars(values): return [{'close':v} for v in values]
def test_bullish_regime():
    r=classify_regime(bars([100+i*.5 for i in range(60)])); assert r.regime==Regime.BULLISH_CONTROLLED
def test_bearish_regime():
    r=classify_regime(bars([130-i*.5 for i in range(60)])); assert r.regime==Regime.BEARISH_CONTROLLED
def test_insufficient(): assert classify_regime(bars([1]*10)).regime==Regime.DATA_INSUFFICIENT
