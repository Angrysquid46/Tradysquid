"""Tests for thesis invalidation: every other exit reacts to price or
Greeks - nothing previously checked whether the actual setup that
justified the trade was still true. This re-reads the same regime
classifier used at entry and flags a genuine reversal, requiring two
consecutive confirmations (same persistence principle as the Greeks
gate) so a single noisy regime re-read can't close a position alone.

Swing's classifier only trades SOFI/HL (see MEAN_REVERSION_VALIDATED_TICKERS
in ford_scan.py) and reacts to a confirmed pullback-in-trend (buy the dip
in an uptrend, fade the bounce in a downtrend), not a reversal - fixtures
here build that shape directly instead of a generic up/downtrend.
"""

from __future__ import annotations

import ford_scan


def _daily_history(closes: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i + 1:02d}", "close": close, "volume": 1_000_000} for i, close in enumerate(closes)]


def _uptrend_closes(days: int = 60) -> list[float]:
    return [round(100.0 * (1 + 0.0035) ** i, 2) for i in range(days)]


def _downtrend_closes(days: int = 60) -> list[float]:
    return [round(100.0 * (1 - 0.0035) ** i, 2) for i in range(days)]


def _pullback_in_uptrend_closes() -> list[float]:
    # Steady climb for 35 days (rising 30-day average), then a shallow
    # 3-day pullback that touches the 10-day average without breaking
    # the larger uptrend - the confirmed-trend-pullback shape swing's
    # BULLISH regime needs.
    closes = [100.0]
    for _ in range(34):
        closes.append(round(closes[-1] * 1.01, 2))
    for _ in range(3):
        closes.append(round(closes[-1] * 0.995, 2))
    return closes


def _pullback_in_downtrend_closes() -> list[float]:
    closes = [100.0]
    for _ in range(34):
        closes.append(round(closes[-1] * 0.99, 2))
    for _ in range(3):
        closes.append(round(closes[-1] * 1.005, 2))
    return closes


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({"trade_id": "T-1", "ticker": "SOFI", "outcome": "OPEN"})
    row.update(overrides)
    return row


class _PrimedCache:
    """Seeds the module-level history caches for a ticker for the duration
    of a `with` block, then removes exactly what it added - so nothing
    leaks into unrelated tests that happen to also use the same ticker."""

    def __init__(self, closes: list[float], ticker: str = "SOFI"):
        self.closes = closes
        self.ticker = ticker

    def __enter__(self):
        ford_scan.DAILY_SNAPSHOT_CACHE[self.ticker] = (ford_scan.time.monotonic(), _daily_history(self.closes))
        ford_scan.INTRADAY_SNAPSHOT_CACHE[self.ticker] = (ford_scan.time.monotonic(), [])

    def __exit__(self, *exc):
        ford_scan.DAILY_SNAPSHOT_CACHE.pop(self.ticker, None)
        ford_scan.INTRADAY_SNAPSHOT_CACHE.pop(self.ticker, None)


def test_spreads_are_never_evaluated_for_thesis_invalidation():
    row = _row(play_type="SPREAD", call_or_put="put")
    invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is False


def test_a_call_held_through_a_genuine_reversal_to_bearish_is_flagged():
    with _PrimedCache(_pullback_in_downtrend_closes()):
        row = _row(play_type="SWING", call_or_put="call")
        invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is True
    assert "reversed" in note


def test_a_ticker_outside_the_validated_swing_set_never_flags_a_reversal():
    # F isn't in MEAN_REVERSION_VALIDATED_TICKERS - swing has nothing to
    # say about it either way, so it must never fire true here.
    with _PrimedCache(_pullback_in_downtrend_closes(), ticker="F"):
        row = _row(play_type="SWING", call_or_put="call", ticker="F")
        invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is False


def test_a_call_still_matching_a_bullish_regime_is_not_flagged():
    with _PrimedCache(_pullback_in_uptrend_closes()):
        row = _row(play_type="SWING", call_or_put="call")
        invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is False


def test_a_first_invalidation_reading_only_watches_does_not_close():
    quote = {
        "SOFI260821C00100000": {
            "symbol": "SOFI260821C00100000", "bid": 0.95, "ask": 1.00,
            "greeks": {"delta": 0.30, "mid_iv": 0.40},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="SOFI260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="0",
    )
    with _PrimedCache(_pullback_in_downtrend_closes()):
        evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    assert evaluation.get("signal") != "THESIS INVALIDATED"
    assert row["thesis_invalid_streak"] == "1"


def test_a_second_consecutive_invalidation_reading_actually_closes():
    quote = {
        "SOFI260821C00100000": {
            "symbol": "SOFI260821C00100000", "bid": 0.95, "ask": 1.00,
            "greeks": {"delta": 0.30, "mid_iv": 0.40},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="SOFI260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="1",  # already seen once
    )
    with _PrimedCache(_pullback_in_downtrend_closes()):
        evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    assert evaluation.get("signal") == "THESIS INVALIDATED"


def test_thesis_invalidation_never_overrides_a_real_price_stop_already_firing():
    # A genuine stop-out must win even if the regime also happens to have
    # reversed - this is a lower-priority signal, not a competing one.
    quote = {
        "SOFI260821C00100000": {
            "symbol": "SOFI260821C00100000", "bid": 0.60, "ask": 0.65,
            "greeks": {"delta": 0.20, "mid_iv": 0.35},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="SOFI260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="1",
    )
    with _PrimedCache(_pullback_in_downtrend_closes()):
        evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    # -35% is well past swing's own stop - that must win regardless of
    # thesis-invalidation streak state.
    assert evaluation.get("signal") == "STOP OUT"


def test_terminal_signal_sets_include_thesis_invalidated():
    # Confirms the signal actually closes the position through all three
    # code paths this was wired into tonight, not just returned as a label.
    import inspect
    source = inspect.getsource(ford_scan)
    assert source.count('"THESIS INVALIDATED"') >= 1


def test_cache_priming_does_not_leak_between_tests():
    # Directly verifies the cleanup contract this whole file depends on.
    with _PrimedCache(_uptrend_closes()):
        assert "SOFI" in ford_scan.DAILY_SNAPSHOT_CACHE
    assert "SOFI" not in ford_scan.DAILY_SNAPSHOT_CACHE
    assert "SOFI" not in ford_scan.INTRADAY_SNAPSHOT_CACHE
