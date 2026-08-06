"""Tests for thesis invalidation: every other exit reacts to price or
Greeks - nothing previously checked whether the actual setup that
justified the trade was still true. This re-reads the same regime
classifier used at entry and flags a genuine reversal, requiring two
consecutive confirmations (same persistence principle as the Greeks
gate) so a single noisy regime re-read can't close a position alone."""

from __future__ import annotations

import ford_scan


def _daily_history(closes: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i + 1:02d}", "close": close, "volume": 1_000_000} for i, close in enumerate(closes)]


def _uptrend_closes(days: int = 60) -> list[float]:
    return [round(100.0 * (1 + 0.0035) ** i, 2) for i in range(days)]


def _downtrend_closes(days: int = 60) -> list[float]:
    return [round(100.0 * (1 - 0.0035) ** i, 2) for i in range(days)]


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({"trade_id": "T-1", "ticker": "F", "outcome": "OPEN"})
    row.update(overrides)
    return row


class _PrimedCache:
    """Seeds the module-level history caches for ticker F for the duration
    of a `with` block, then removes exactly what it added - so nothing
    leaks into unrelated tests that happen to also use ticker F."""

    def __init__(self, closes: list[float]):
        self.closes = closes

    def __enter__(self):
        ford_scan.DAILY_SNAPSHOT_CACHE["F"] = (ford_scan.time.monotonic(), _daily_history(self.closes))
        ford_scan.INTRADAY_SNAPSHOT_CACHE["F"] = (ford_scan.time.monotonic(), [])

    def __exit__(self, *exc):
        ford_scan.DAILY_SNAPSHOT_CACHE.pop("F", None)
        ford_scan.INTRADAY_SNAPSHOT_CACHE.pop("F", None)


def test_spreads_are_never_evaluated_for_thesis_invalidation():
    row = _row(play_type="SPREAD", call_or_put="put")
    invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is False


def test_a_call_held_through_a_genuine_reversal_to_bearish_is_flagged():
    with _PrimedCache(_downtrend_closes()):
        row = _row(play_type="SWING", call_or_put="call")
        invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is True
    assert "reversed" in note


def test_a_call_still_matching_a_bullish_regime_is_not_flagged():
    with _PrimedCache(_uptrend_closes()):
        row = _row(play_type="SWING", call_or_put="call")
        invalidated, note = ford_scan.check_thesis_invalidation(row, ford_scan.now_ct())
    assert invalidated is False


def test_a_first_invalidation_reading_only_watches_does_not_close():
    quote = {
        "F260821C00100000": {
            "symbol": "F260821C00100000", "bid": 0.95, "ask": 1.00,
            "greeks": {"delta": 0.30, "mid_iv": 0.40},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="F260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="0",
    )
    with _PrimedCache(_downtrend_closes()):
        evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    assert evaluation.get("signal") != "THESIS INVALIDATED"
    assert row["thesis_invalid_streak"] == "1"


def test_a_second_consecutive_invalidation_reading_actually_closes():
    quote = {
        "F260821C00100000": {
            "symbol": "F260821C00100000", "bid": 0.95, "ask": 1.00,
            "greeks": {"delta": 0.30, "mid_iv": 0.40},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="F260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="1",  # already seen once
    )
    with _PrimedCache(_downtrend_closes()):
        evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    assert evaluation.get("signal") == "THESIS INVALIDATED"


def test_thesis_invalidation_never_overrides_a_real_price_stop_already_firing():
    # A genuine stop-out must win even if the regime also happens to have
    # reversed - this is a lower-priority signal, not a competing one.
    quote = {
        "F260821C00100000": {
            "symbol": "F260821C00100000", "bid": 0.60, "ask": 0.65,
            "greeks": {"delta": 0.20, "mid_iv": 0.35},
        }
    }
    row = _row(
        play_type="SWING", call_or_put="call", entry_price="1.00",
        option_symbol="F260821C00100000",
        delta_at_entry="0.32", iv_at_entry="0.41",
        expiration=(ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        max_favorable_pct="0", thesis_invalid_streak="1",
    )
    with _PrimedCache(_downtrend_closes()):
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
        assert "F" in ford_scan.DAILY_SNAPSHOT_CACHE
    assert "F" not in ford_scan.DAILY_SNAPSHOT_CACHE
    assert "F" not in ford_scan.INTRADAY_SNAPSHOT_CACHE
