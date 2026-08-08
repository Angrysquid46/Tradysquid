"""Behavioral tests for the split regular/swing trader logic.

These build synthetic market data by hand (no network, no Tradier) so the
entry logic can be verified against known-shape scenarios: a clean uptrend
with same-session confirmation, a clean uptrend with NO same-session
confirmation, a downtrend, and a flat/choppy tape. If these ever fail after
an edit, the trader logic changed behavior - that's the point of having them.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import ford_scan


def _daily_history(closes: list[float], volumes: list[float] | None = None) -> list[dict]:
    volumes = volumes or [1_000_000] * len(closes)
    return [
        {"date": f"2026-01-{i + 1:02d}", "close": close, "volume": volume}
        for i, (close, volume) in enumerate(zip(closes, volumes))
    ]


def _intraday_bars(prices: list[float], volume_each: float = 50_000) -> list[dict]:
    return [{"close": price, "volume": volume_each} for price in prices]


def _uptrend_closes(days: int = 60, start: float = 100.0, daily_gain: float = 0.35) -> list[float]:
    return [round(start * (1 + daily_gain / 100) ** i, 2) for i in range(days)]


def _downtrend_closes(days: int = 60, start: float = 100.0, daily_loss: float = 0.35) -> list[float]:
    return [round(start * (1 - daily_loss / 100) ** i, 2) for i in range(days)]


def _flat_closes(days: int = 60, level: float = 100.0) -> list[float]:
    # Small alternating noise, no real drift either direction.
    return [round(level + (0.15 if i % 2 == 0 else -0.15), 2) for i in range(days)]


def test_regular_requires_same_session_confirmation_and_none_is_available():
    closes = _uptrend_closes()
    context = ford_scan.regular_market_context(_daily_history(closes), closes[-1], intraday=[])
    assert context["qualified"] is False
    assert context["regime"] == "NO TRADE"


def test_regular_goes_bullish_on_strong_intraday_confirmation():
    closes = _uptrend_closes()
    spot = closes[-1]
    # Intraday: opens near yesterday's close, grinds up all day, closes strong.
    intraday_prices = [spot * (1 + 0.006 * i / 12) for i in range(13)]
    context = ford_scan.regular_market_context(
        _daily_history(closes), intraday_prices[-1], intraday=_intraday_bars(intraday_prices)
    )
    assert context["qualified"] is True, context["failures"]
    assert context["regime"] == "BULLISH / CONTROLLED"


def test_regular_goes_bearish_on_strong_intraday_breakdown():
    closes = _downtrend_closes()
    spot = closes[-1]
    intraday_prices = [spot * (1 - 0.006 * i / 12) for i in range(13)]
    context = ford_scan.regular_market_context(
        _daily_history(closes), intraday_prices[-1], intraday=_intraday_bars(intraday_prices)
    )
    assert context["qualified"] is True, context["failures"]
    assert context["regime"] == "BEARISH / CONTROLLED"


def test_regular_reason_text_includes_rsi_and_daily_trend_when_they_score():
    # RSI and the daily trend both feed evidence_score but used to never
    # appear in "reason" - the displayed thesis was silently missing up to
    # half of what actually justified the trade. A clean, strong uptrend
    # with an intraday grind up that pulls back periodically (real RSI in
    # the confirming 60-75 band, not pinned at the 100 ceiling a perfectly
    # monotonic tape would produce) should score on every category,
    # including these two, and now say so.
    closes = _uptrend_closes()
    intraday_prices = [100.0 * 0.97]
    for i in range(1, 16):
        intraday_prices.append(
            intraday_prices[-1] * (0.994 if i % 4 == 0 else 1.004)
        )
    context = ford_scan.regular_market_context(
        _daily_history(closes), intraday_prices[-1], intraday=_intraday_bars(intraday_prices)
    )
    assert context["qualified"] is True, context["failures"]
    assert "RSI is bullish" in context["reason"]
    assert "20-day trend" in context["reason"]
    # Numeric magnitude, not just a static boolean phrase - this is what
    # makes two genuinely different observations produce different text
    # even when the same conditions qualify both times.
    assert "%" in context["reason"]


def test_regular_extreme_rsi_is_excluded_not_counted_as_fresh_confirmation():
    # A perfectly monotonic intraday grind pins RSI at the 100 ceiling -
    # already-exhausted territory, not "still building." It must not be
    # counted as confirmation just because it crossed the bullish threshold.
    closes = _uptrend_closes()
    spot = closes[-1]
    intraday_prices = [spot * (1 + 0.006 * i / 12) for i in range(13)]
    context = ford_scan.regular_market_context(
        _daily_history(closes), intraday_prices[-1], intraday=_intraday_bars(intraday_prices)
    )
    assert "RSI is bullish" not in context["reason"]
    assert "already extended" in context["reason"]


def test_regular_does_not_qualify_on_a_flat_choppy_intraday_tape():
    closes = _flat_closes()
    spot = closes[-1]
    intraday_prices = [spot + (0.02 if i % 2 == 0 else -0.02) for i in range(13)]
    context = ford_scan.regular_market_context(
        _daily_history(closes), spot, intraday=_intraday_bars(intraday_prices)
    )
    assert context["qualified"] is False


def _oversold_bounce_closes() -> list[float]:
    closes = [100.0]
    for _ in range(39):
        closes.append(round(closes[-1] * 0.985, 2))  # steady decline -> RSI pinned low
    for _ in range(3):
        closes.append(round(closes[-1] * 1.03, 2))  # 3-day bounce
    return closes


def _overbought_fade_closes() -> list[float]:
    closes = [100.0]
    for _ in range(39):
        closes.append(round(closes[-1] * 1.015, 2))  # steady climb -> RSI pinned high
    for _ in range(3):
        closes.append(round(closes[-1] * 0.97, 2))  # 3-day fade
    return closes


def _with_ticker(ticker, fn):
    original = ford_scan.TICKER
    ford_scan.TICKER = ticker
    try:
        return fn()
    finally:
        ford_scan.TICKER = original


def test_swing_only_trades_the_backtest_validated_ticker_set():
    # F is not in MEAN_REVERSION_VALIDATED_TICKERS - a real oversold-bounce
    # shape must still be blocked, because the edge was only ever proven
    # for SHOP and META, not universally.
    closes = _oversold_bounce_closes()
    context = _with_ticker(
        "F", lambda: ford_scan.swing_market_context(_daily_history(closes), closes[-1], intraday=[])
    )
    assert context["qualified"] is False
    assert "not in the validated swing ticker set" in context["failures"][0]


def test_swing_reads_bullish_on_a_confirmed_oversold_bounce():
    closes = _oversold_bounce_closes()
    context = _with_ticker(
        "SHOP", lambda: ford_scan.swing_market_context(_daily_history(closes), closes[-1], intraday=[])
    )
    assert context["qualified"] is True, context["failures"]
    assert context["regime"] == "BULLISH / CONTROLLED"
    assert "oversold" in context["reason"]


def test_swing_reads_bearish_on_a_confirmed_overbought_fade():
    closes = _overbought_fade_closes()
    context = _with_ticker(
        "META", lambda: ford_scan.swing_market_context(_daily_history(closes), closes[-1], intraday=[])
    )
    assert context["qualified"] is True, context["failures"]
    assert context["regime"] == "BEARISH / CONTROLLED"
    assert "overbought" in context["reason"]


def test_swing_does_not_qualify_without_a_confirmed_reversal():
    # A validated ticker, but a plain uptrend with no oversold/overbought
    # extreme to bounce from - there's nothing to confirm.
    closes = _uptrend_closes()
    context = _with_ticker(
        "SHOP", lambda: ford_scan.swing_market_context(_daily_history(closes), closes[-1], intraday=[])
    )
    assert context["qualified"] is False
    assert "no confirmed RSI reversal" in context["failures"][0]


def test_trade_types_enabled_defaults_true_when_config_missing_key():
    # Isolated from the real config/scanner.json - that file reflects live
    # trading decisions (e.g. everything paused pending backtest
    # validation) which is not what this test is checking. This checks
    # trade_types_enabled()'s own default behavior when a key is absent.
    original_path = ford_scan.SCANNER_CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        temp_config = Path(tmp) / "scanner.json"
        temp_config.write_text(json.dumps({}), encoding="utf-8")
        ford_scan.SCANNER_CONFIG_PATH = temp_config
        try:
            enabled = ford_scan.trade_types_enabled()
            assert enabled["regular_calls"] is True
            assert enabled["swing_puts"] is True
        finally:
            ford_scan.SCANNER_CONFIG_PATH = original_path


def test_trade_types_enabled_honors_a_disabled_flag():
    original_path = ford_scan.SCANNER_CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        temp_config = Path(tmp) / "scanner.json"
        temp_config.write_text(
            json.dumps({"trade_types_enabled": {"regular_calls": False}}), encoding="utf-8"
        )
        ford_scan.SCANNER_CONFIG_PATH = temp_config
        try:
            enabled = ford_scan.trade_types_enabled()
            assert enabled["regular_calls"] is False
            # Untouched keys still default true.
            assert enabled["swing_calls"] is True
        finally:
            ford_scan.SCANNER_CONFIG_PATH = original_path


def test_a_broken_context_never_raises_only_reports_unqualified():
    # Simulates what scan_candidates()'s try/except falls back to.
    context = ford_scan._unavailable_context("swing trader errored: boom")
    assert context["qualified"] is False
    assert context["regime"] == "NO TRADE"
    assert "boom" in context["failures"][0]


def test_regular_category_scoring_caps_the_maximum_possible_score():
    # Before category-based scoring, six raw signal points could sum to as
    # much as +/-7. Now there are four independent categories worth at
    # most one point each, so the true ceiling is +/-4 - directly
    # verifiable regardless of exactly which categories a given scenario
    # happens to trigger.
    closes = _uptrend_closes()
    spot = closes[-1]
    intraday_prices = [spot * (1 + 0.006 * i / 12) for i in range(13)]
    context = ford_scan.regular_market_context(
        _daily_history(closes), intraday_prices[-1], intraday=_intraday_bars(intraday_prices)
    )
    assert abs(context["evidence_score"]) <= 4
