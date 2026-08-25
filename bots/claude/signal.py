"""Phase 13: AXIOM's entry signal - a volatility-compression opening-range
breakout, independently designed with zero knowledge of BLACKTIDE's private
logic (the other competitor's private directory was never read while
building this).

Core thesis: a naive "any break of the opening range" signal fires on
every session regardless of context. AXIOM instead requires three
independent conditions before treating a range break as tradeable:

  1. Compression  - the pre-breakout volatility regime was unusually quiet
     (bottom-third ATR percentile), a "coiled spring" precondition.
  2. Breakout     - the first bar since the opening range closed, closing
     outside that range.
  3. Confirmation - real participation (relative volume above a modest
     threshold) AND the breakout direction agrees with price's side of
     VWAP (long only above VWAP, short only below).

Each is a separately testable predicate, ANDed together. All bar/feature
inputs come from backtest_lab.MarketView (bars_as_of/compute_features) -
the one shared no-lookahead interface - so this module works identically
whether called from a live loop or a backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bots.claude.parameters import DEFAULT_PARAMETERS, Parameters


@dataclass(frozen=True)
class EntryDecision:
    should_enter: bool
    side: str | None
    rationale: str
    contributing_signals: dict[str, Any] = field(default_factory=dict)


def _session_key(bar: dict[str, Any]) -> str:
    return str(bar["bar_time"])[:10]


def compute_regime_features(
    bars: list[dict[str, Any]], parameters: Parameters = DEFAULT_PARAMETERS
) -> dict[str, Any] | None:
    """Causal opening-range and prior-day-level features built directly
    from MarketView.bars_as_of() rows - not covered by
    backtest_lab.compute_features(), so AXIOM computes them itself rather
    than reaching into a second, differently-governed data pipeline
    (spy_intraday_features.py) outside the no-lookahead interface.

    `bars` must already be sorted ascending by bar_timestamp (bars_as_of
    returns them that way).
    """
    if not bars:
        return None

    today_key = _session_key(bars[-1])
    session_bars = [b for b in bars if _session_key(b) == today_key]
    if not session_bars:
        return None

    session_start_ts = session_bars[0]["bar_timestamp"]
    or_end_ts = session_start_ts + parameters.opening_range_minutes * 60

    or_bars = [b for b in session_bars if b["bar_timestamp"] <= or_end_ts]
    post_or_bars = [b for b in session_bars if b["bar_timestamp"] > or_end_ts]

    opening_range_high = max((b["high"] for b in or_bars), default=None)
    opening_range_low = min((b["low"] for b in or_bars), default=None)
    opening_range_established = bool(or_bars) and bool(post_or_bars)

    is_first_breakout_bar = False
    breakout_side = None
    if opening_range_established:
        current = post_or_bars[-1]
        earlier = post_or_bars[:-1]

        def _breaks(bar: dict[str, Any]) -> bool:
            return bar["close"] > opening_range_high or bar["close"] < opening_range_low

        current_breaks = _breaks(current)
        any_earlier_broke = any(_breaks(b) for b in earlier)
        if current_breaks and not any_earlier_broke:
            is_first_breakout_bar = True
            breakout_side = "CALL" if current["close"] > opening_range_high else "PUT"

    prior_day_keys = sorted({_session_key(b) for b in bars if _session_key(b) != today_key})
    prior_day_high = prior_day_low = prior_day_close = None
    if prior_day_keys:
        prior_key = prior_day_keys[-1]
        prior_bars = [b for b in bars if _session_key(b) == prior_key]
        prior_day_high = max(b["high"] for b in prior_bars)
        prior_day_low = min(b["low"] for b in prior_bars)
        prior_day_close = prior_bars[-1]["close"]

    return {
        "opening_range_high": opening_range_high,
        "opening_range_low": opening_range_low,
        "opening_range_established": opening_range_established,
        "is_first_breakout_bar": is_first_breakout_bar,
        "breakout_side": breakout_side,
        "prior_day_high": prior_day_high,
        "prior_day_low": prior_day_low,
        "prior_day_close": prior_day_close,
        "current_close": session_bars[-1]["close"],
    }


def entry_decision(
    regime_features: dict[str, Any] | None,
    causal_features: dict[str, Any] | None,
    parameters: Parameters,
) -> EntryDecision:
    """ANDs the three independent predicates. Never raises on missing/None
    inputs - a missing feature just fails that predicate, which is the
    correct behavior when data is thin (INSUFFICIENT_DATA upstream)."""
    signals: dict[str, Any] = {
        "regime_features": regime_features,
        "causal_features": causal_features,
    }

    if not regime_features or not regime_features.get("is_first_breakout_bar"):
        return EntryDecision(False, None, "no first-breakout bar this session", signals)

    side = regime_features["breakout_side"]
    current_close = regime_features["current_close"]

    atr_percentile = (causal_features or {}).get("atr_percentile")
    compression_ok = atr_percentile is not None and atr_percentile <= parameters.compression_atr_percentile_max
    signals["atr_percentile"] = atr_percentile
    signals["compression_ok"] = compression_ok
    if not compression_ok:
        return EntryDecision(False, None, f"regime not compressed (atr_percentile={atr_percentile})", signals)

    relative_volume = (causal_features or {}).get("relative_volume")
    volume_ok = relative_volume is not None and relative_volume >= parameters.relative_volume_min
    signals["relative_volume"] = relative_volume
    signals["volume_ok"] = volume_ok
    if not volume_ok:
        return EntryDecision(False, None, f"volume not confirmed (relative_volume={relative_volume})", signals)

    vwap = (causal_features or {}).get("vwap")
    if vwap is None:
        return EntryDecision(False, None, "no vwap available for confluence check", signals)
    confluence_ok = (current_close > vwap) if side == "CALL" else (current_close < vwap)
    signals["vwap"] = vwap
    signals["confluence_ok"] = confluence_ok
    if not confluence_ok:
        return EntryDecision(False, None, f"breakout disagrees with VWAP side (vwap={vwap})", signals)

    return EntryDecision(
        True, side,
        f"compressed regime + confirmed {side} breakout of opening range, aligned with VWAP",
        signals,
    )
