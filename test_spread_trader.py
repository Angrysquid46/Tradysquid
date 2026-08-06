"""Behavioral tests for realized-volatility, IV-rank tracking, and the
dedicated spread trader.

Spreads are the one type that isn't a directional bet at all. Premium
richness is judged against the stock's own realized volatility - available
immediately, no history-building required - so spreads can trade from day
one; IV rank is tracked in parallel and adds context once it matures, but
was deliberately NOT made a hard requirement.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import ford_scan


def _daily_history(closes: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i + 1:02d}", "close": close} for i, close in enumerate(closes)]


def _flat_closes(days: int = 60, level: float = 100.0) -> list[float]:
    return [round(level + (0.15 if i % 2 == 0 else -0.15), 2) for i in range(days)]


def _calm_midrange_closes() -> list[float]:
    """40 flat days then a gentle 20-day wave that settles back near its own
    midpoint - support/resistance exist, but today's price isn't sitting
    at either extreme, unlike an alternating up/down tape."""
    import math

    base = [100.0] * 40
    tail = [round(100 + 2 * math.sin(i * 0.5), 2) for i in range(20)]
    return base + tail


def _with_temp_iv_history():
    """Context manager-ish helper: swap IV_HISTORY_PATH to a temp file and
    restore it afterward, so tests never touch real runtime state."""

    class _Swap:
        def __enter__(self):
            self.original = ford_scan.IV_HISTORY_PATH
            self.tmp = tempfile.TemporaryDirectory()
            ford_scan.IV_HISTORY_PATH = Path(self.tmp.name) / "iv-history.json"
            return ford_scan.IV_HISTORY_PATH

        def __exit__(self, *exc):
            ford_scan.IV_HISTORY_PATH = self.original
            self.tmp.cleanup()

    return _Swap()


def test_realized_volatility_is_none_with_too_little_history():
    assert ford_scan.realized_volatility([100.0, 101.0, 99.0]) is None


def test_realized_volatility_is_near_zero_for_a_dead_flat_tape():
    flat = [100.0] * 25
    rv = ford_scan.realized_volatility(flat)
    assert rv is not None
    assert rv < 0.01


def test_realized_volatility_is_meaningfully_higher_for_a_choppier_tape():
    calm = ford_scan.realized_volatility(_calm_midrange_closes())
    choppy = [100.0] * 40 + [
        round(100 + 8 * ((-1) ** i), 2) for i in range(20)
    ]
    volatile = ford_scan.realized_volatility(choppy)
    assert calm is not None and volatile is not None
    assert volatile > calm * 3


def test_pooled_iv_rank_is_none_when_the_whole_pool_is_thin():
    with _with_temp_iv_history():
        # Only a handful of readings across the whole universe, well under
        # POOLED_IV_MIN_SAMPLES - not enough to mean anything yet either.
        for i, ticker in enumerate(["AAA", "BBB", "CCC"]):
            ford_scan.record_iv_snapshot(ticker, 0.30, "2026-01-15")
        rank, samples = ford_scan.pooled_iv_rank(0.30, "2026-01-15")
        assert rank is None
        assert samples == 3


def test_pooled_iv_rank_gives_a_brand_new_ticker_a_real_read_on_day_one():
    with _with_temp_iv_history():
        # 25 other tickers all scanned today at a calm 0.25 IV - a brand new
        # ticker showing up with a spiked 0.50 IV should rank near the top,
        # even though IT has zero history of its own.
        for i in range(25):
            ford_scan.record_iv_snapshot(f"T{i}", 0.25, "2026-01-15")
        rank, samples = ford_scan.pooled_iv_rank(0.50, "2026-01-15")
        assert rank is not None
        assert rank >= 95.0
        assert samples == 25


def test_pooled_iv_rank_ignores_readings_older_than_the_lookback_window():
    with _with_temp_iv_history():
        for i in range(25):
            ford_scan.record_iv_snapshot(f"T{i}", 0.90, "2025-01-01")  # ancient, way outside window
        rank, samples = ford_scan.pooled_iv_rank(0.30, "2026-01-15", lookback_days=20)
        assert samples == 0
        assert rank is None


def test_spread_context_uses_pooled_rank_when_tickers_own_history_is_thin():
    closes = _calm_midrange_closes()
    spot = closes[-1]
    realized = ford_scan.realized_volatility(closes)
    rich_iv = realized * 1.30
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=rich_iv, iv_rank_value=None, pooled_iv_rank_value=72.0
    )
    assert context["qualified"] is True, context["failures"]
    assert context["pooled_iv_rank"] == 72.0
    assert "wider universe" in context["reason"]


def test_iv_rank_is_none_before_enough_history_exists():
    with _with_temp_iv_history():
        for day in range(5):  # well under IV_HISTORY_MIN_SAMPLES
            ford_scan.record_iv_snapshot("VALE", 0.40, f"2026-01-{day + 1:02d}")
        assert ford_scan.iv_rank("VALE") is None


def test_iv_rank_reflects_where_todays_reading_sits_in_its_own_history():
    with _with_temp_iv_history():
        # 20 days at 0.30, then today spikes to 0.60 - today should rank at
        # (or very near) the top of its own history.
        for day in range(20):
            ford_scan.record_iv_snapshot("VALE", 0.30, f"2026-01-{day + 1:02d}")
        ford_scan.record_iv_snapshot("VALE", 0.60, "2026-01-21")
        rank = ford_scan.iv_rank("VALE")
        assert rank is not None
        assert rank >= 95.0


def test_same_day_recorded_twice_updates_instead_of_duplicating():
    with _with_temp_iv_history():
        ford_scan.record_iv_snapshot("VALE", 0.30, "2026-01-01")
        ford_scan.record_iv_snapshot("VALE", 0.35, "2026-01-01")
        history = ford_scan._load_iv_history()
        assert len(history["VALE"]) == 1
        assert history["VALE"][0][1] == 0.35


def test_spread_context_can_qualify_with_zero_iv_rank_history():
    # The whole point of the IV/RV redesign: it should be able to trade on
    # day one, before iv_rank has any samples at all, as long as implied vol
    # is rich relative to what the stock has actually been doing.
    closes = _calm_midrange_closes()
    spot = closes[-1]
    realized = ford_scan.realized_volatility(closes)
    rich_iv = realized * 1.30
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=rich_iv, iv_rank_value=None
    )
    assert context["qualified"] is True, context["failures"]
    assert context["iv_rank"] is None
    assert "IV rank still building" in context["reason"]


def test_spread_context_refuses_to_fire_on_cheap_premium():
    closes = _calm_midrange_closes()
    spot = closes[-1]
    realized = ford_scan.realized_volatility(closes)
    cheap_iv = realized * 0.80
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=cheap_iv, iv_rank_value=None
    )
    assert context["qualified"] is False


def test_spread_context_qualifies_on_rich_premium_and_a_calm_range():
    closes = _calm_midrange_closes()
    spot = closes[-1]
    realized = ford_scan.realized_volatility(closes)
    rich_iv = realized * 1.30
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=rich_iv, iv_rank_value=65.0
    )
    assert context["qualified"] is True, context["failures"]
    assert context["regime"] == "RANGE / SELL PREMIUM"
    assert context["support"] is not None
    assert context["resistance"] is not None


def test_spread_context_refuses_to_fire_right_at_a_20_day_extreme():
    closes = _calm_midrange_closes()
    realized = ford_scan.realized_volatility(closes)
    rich_iv = realized * 1.30
    # Push the "current" spot to a fresh 20-day high - not calm anymore.
    spot = max(closes[-20:]) * 1.02
    context = ford_scan.spread_market_context(
        _daily_history(closes), spot, current_iv=rich_iv, iv_rank_value=65.0
    )
    assert context["qualified"] is False


def test_bull_put_spread_strike_must_sit_below_real_support():
    # Two candidate pairs, both otherwise valid (delta, credit, risk, and
    # liquidity all pass) - one sits below support, one sits above it. Only
    # the one below support should survive.
    chain = [
        {
            "strike": 89.0, "option_type": "put", "symbol": "P89",
            "bid": 0.15, "ask": 0.17, "greeks": {"delta": -0.10},
            "open_interest": 500, "volume": 50,
        },
        {
            "strike": 90.0, "option_type": "put", "symbol": "P90",
            "bid": 0.35, "ask": 0.38, "greeks": {"delta": -0.20},
            "open_interest": 500, "volume": 50,
        },
        {
            "strike": 97.0, "option_type": "put", "symbol": "P97",
            "bid": 0.15, "ask": 0.17, "greeks": {"delta": -0.10},
            "open_interest": 500, "volume": 50,
        },
        {
            "strike": 98.0, "option_type": "put", "symbol": "P98",
            "bid": 0.35, "ask": 0.38, "greeks": {"delta": -0.20},
            "open_interest": 500, "volume": 50,
        },
    ]
    # Support at 97 - the 98/97 pair has its short strike (98) ABOVE support
    # and must be rejected; the 90/89 pair sits safely below and should pass.
    context = {"support": 97.0, "resistance": 103.0}
    candidates = ford_scan.scan_credit_spreads(chain, "put", "2026-09-18", context)
    short_strikes = {candidate["sell_strike"] for candidate in candidates}
    assert 98.0 not in short_strikes
    assert 90.0 in short_strikes


def test_spread_exit_takes_profit_at_half_of_max_like_before():
    signal, note = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.14,  # captured 0.16 of 0.30 = ~53%
        current_short_delta=-0.18,
        entry_short_delta=-0.20,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "TAKE PROFIT"
    assert "50%" in note


def test_spread_exit_stops_out_at_the_credit_multiple_like_before():
    signal, note = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.62,  # over 2x the credit received
        current_short_delta=-0.35,
        entry_short_delta=-0.20,
        current_iv=0.45,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "STOP OUT"
    assert "credit received" in note


def test_spread_exit_holds_in_the_normal_middle_ground():
    signal, _ = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.25,
        current_short_delta=-0.22,
        entry_short_delta=-0.20,
        current_iv=0.43,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_spread_exit_defends_early_when_short_delta_doubles():
    # Nowhere near the price-based stop (cost_to_close barely above entry
    # credit), but the short strike's own delta has more than doubled -
    # genuinely threatened, not just modestly against.
    signal, note = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.33,
        current_short_delta=-0.45,
        entry_short_delta=-0.20,
        current_iv=0.42,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "STOP OUT"
    assert "delta grew" in note


def test_spread_exit_defends_early_on_a_big_iv_expansion():
    signal, note = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.33,
        current_short_delta=-0.22,
        entry_short_delta=-0.20,
        current_iv=0.60,  # up from 0.42, a 43% expansion
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "STOP OUT"
    assert "IV expanded" in note


def test_spread_exit_missing_greeks_never_crashes_and_falls_back_to_price_only():
    signal, _ = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.20,
        current_short_delta=None,
        entry_short_delta=None,
        current_iv=None,
        entry_iv=None,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_spread_exit_closes_ahead_of_expiration_when_nothing_else_triggered():
    signal, note = ford_scan.spread_exit_signal(
        entry_credit=0.30,
        cost_to_close=0.20,
        current_short_delta=-0.15,
        entry_short_delta=-0.20,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=True,
    )
    assert signal == "EXPIRY CLOSE"
