"""Tests for directional spread trading: a strong trend used to block both
bull put and bear call spreads equally. Now it only blocks the spread
betting against the trend - a bull put spread benefits from the same push
that makes a bear call spread dangerous, and vice versa."""

from __future__ import annotations

import ford_scan


def _daily_history(closes: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i + 1:02d}", "close": close} for i, close in enumerate(closes)]


def _strong_uptrend_closes(days: int = 60) -> list[float]:
    # Fast enough SMA20-vs-SMA50 divergence to clear SPREAD_MAX_TREND_STRENGTH,
    # while landing well clear of the 20-day high/low extreme buffer.
    return [round(100.0 * (1 + 0.006) ** i, 2) for i in range(days)]


def _strong_downtrend_closes(days: int = 60) -> list[float]:
    return [round(100.0 * (1 - 0.006) ** i, 2) for i in range(days)]


def test_a_strong_uptrend_permits_bull_put_but_not_bear_call():
    closes = _strong_uptrend_closes()
    # Spot a bit below the recent high, clear of the extreme buffer.
    spot = closes[-1] * 0.98
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=0.50, iv_rank_value=None
    )
    assert context["qualified"] is True, context["failures"]
    assert context["spread_direction"] == "bull_put_only"
    assert context["regime"] == "TREND / SELL WITH MOMENTUM"


def test_a_strong_downtrend_permits_bear_call_but_not_bull_put():
    closes = _strong_downtrend_closes()
    spot = closes[-1] * 1.02
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=0.50, iv_rank_value=None
    )
    assert context["qualified"] is True, context["failures"]
    assert context["spread_direction"] == "bear_call_only"


def test_a_calm_market_still_permits_both_directions():
    import math
    base = [100.0] * 40
    tail = [round(100 + 2 * math.sin(i * 0.5), 2) for i in range(20)]
    closes = base + tail
    context = ford_scan.spread_market_context(
        _daily_history(closes), closes[-1], current_iv=0.50, iv_rank_value=None
    )
    assert context["qualified"] is True, context["failures"]
    assert context["spread_direction"] == "both"
    assert context["regime"] == "RANGE / SELL PREMIUM"


def test_price_at_the_extreme_still_blocks_everything_regardless_of_trend():
    # The near-extreme safety check is untouched by this change - it's a
    # separate, legitimate risk control, not the trend-direction gate.
    closes = _strong_uptrend_closes()
    spot = closes[-1]  # right at today's high, not clear of it
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=0.50, iv_rank_value=None
    )
    assert context["qualified"] is False
    assert context["spread_direction"] is None
