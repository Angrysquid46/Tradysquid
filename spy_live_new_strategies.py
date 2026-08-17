"""Live scanners for the 14 new strategies from the locked top 15.

The 15th, `SPY_KEY_LEVELS`, already runs in `spy_scanner` and is left
alone. These are the other 14, promoted from research code to live paper
trading.

They are not reimplemented here. The entry rules are the exact signal
functions that were backtested - `spy_backtest_strategies` and
`spy_backtest_strategies_extended` - called against features built from
live bars by the same `spy_intraday_features.compute_session_features`
used on history. Reimplementing them for live would let the traded rule
drift from the measured one, which is the whole failure this avoids.

What differs from the backtest, necessarily:

- The backtest evaluates a whole session at once. Live, only the newest
  closed bar matters, so a signal counts only if it fires on that bar.
  `compute_session_features` is causal, so passing the bars so far gives
  the same row the backtest saw at that point.
- Exits are option-premium based, matching how the live system manages
  every position.

Each strategy is an independently-tracked play type with its own config
flag, so any one can be paused without touching the others.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import spy_backtest_strategies as base
import spy_backtest_strategies_extended as ext
import spy_intraday_features as sif

# ---------------------------------------------------------------------------
# The 14 promoted strategies, in shortlist order. play_type -> spec.
#
# `rank` is its position in the locked top 15 (docs/BACKTEST_RESULTS.md).
# `signal` is the exact backtested entry function.
# ---------------------------------------------------------------------------

NEW_STRATEGY_SPECS: tuple[dict[str, Any], ...] = (
    {"play_type": "SPY_GAP_CONT_50", "rank": 1, "label": "Gap Continuation 0.5%",
     "signal": ext.gap_continuation(0.5)},
    {"play_type": "SPY_FAILED_BREAK", "rank": 2, "label": "Failed Breakout (prev-day)",
     "signal": ext.failed_breakout_reversal("prev_day")},
    {"play_type": "SPY_GAP_CONT_25", "rank": 3, "label": "Gap Continuation 0.25%",
     "signal": ext.gap_continuation(0.25)},
    {"play_type": "SPY_SWEEP_10", "rank": 4, "label": "Liquidity Sweep 10-bar",
     "signal": ext.liquidity_sweep(10)},
    {"play_type": "SPY_SWEEP_5", "rank": 5, "label": "Liquidity Sweep 5-bar",
     "signal": ext.liquidity_sweep(5)},
    {"play_type": "SPY_MOMENTUM_ADX25", "rank": 6, "label": "Momentum Continuation ADX25",
     "signal": ext.momentum_continuation(25.0, require_alignment=False)},
    {"play_type": "SPY_TOD_MIDDAY", "rank": 7, "label": "Time-of-Day Midday",
     "signal": ext.time_of_day_momentum("MIDDAY")},
    {"play_type": "SPY_CONFLUENCE_4", "rank": 8, "label": "Confluence 4+ Levels",
     "signal": ext.multi_level_confluence(4)},
    {"play_type": "SPY_TOD_FINAL30", "rank": 9, "label": "Time-of-Day Final 30",
     "signal": ext.time_of_day_momentum("FINAL_30")},
    {"play_type": "SPY_MTF_4OF4", "rank": 10, "label": "MTF Breakout 4/4",
     "signal": ext.multi_timeframe_breakout(4)},
    {"play_type": "SPY_EXHAUSTION_1ATR", "rank": 12, "label": "Momentum Exhaustion 1 ATR",
     "signal": ext.momentum_exhaustion(1.0)},
    {"play_type": "SPY_GAP_CONT_100", "rank": 13, "label": "Gap Continuation 1.0%",
     "signal": ext.gap_continuation(1.0)},
    {"play_type": "SPY_FIRST_PULLBACK", "rank": 14, "label": "First Pullback 0.5 ATR",
     "signal": ext.first_pullback_after_drive(0.5)},
    {"play_type": "SPY_OPENING_GAP_FADE", "rank": 15, "label": "Opening Gap Fade",
     "signal": ext.playbook_opening_gap_fade()},
)

NEW_STRATEGY_PLAY_TYPES = tuple(spec["play_type"] for spec in NEW_STRATEGY_SPECS)
NEW_STRATEGY_BY_PLAY_TYPE = {spec["play_type"]: spec for spec in NEW_STRATEGY_SPECS}


def is_new_strategy_play_type(play_type: str | None) -> bool:
    return play_type in NEW_STRATEGY_BY_PLAY_TYPE


def config_flag(play_type: str) -> str:
    """Config key for a play type, matching the lowercase convention every
    other strategy's `trade_types_enabled` entry uses."""
    return play_type.lower()


# ---------------------------------------------------------------------------
# Features from live bars
# ---------------------------------------------------------------------------

def _bar(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a provider bar into what compute_session_features wants."""
    time = row.get("time") or row.get("bar_time") or row.get("timestamp")
    close = row.get("close")
    if not time or close is None:
        return None
    stamp = str(time).replace(" ", "T")[:19]
    if len(stamp) == 16:
        stamp += ":00"
    return {
        "bar_time": stamp,
        "open": row.get("open"), "high": row.get("high"),
        "low": row.get("low"), "close": close,
        "volume": row.get("volume") or 0.0,
        "regular_session": 1,
    }


def build_session_context(daily_history: Sequence[dict[str, Any]]) -> sif.SessionContext:
    """Prior-session context from daily bars - everything knowable before
    the open. Strictly prior: the current session is never included."""
    context = sif.SessionContext()
    bars = [b for b in daily_history if b.get("close") is not None]
    if not bars:
        return context

    prior = bars[-1]
    context.prev_day_high = prior.get("high")
    context.prev_day_low = prior.get("low")
    context.prev_day_close = prior.get("close")

    if len(bars) >= sif.ATR_PERIOD + 1:
        ranges = []
        for previous, current in zip(bars[-(sif.ATR_PERIOD + 1):-1], bars[-sif.ATR_PERIOD:]):
            high, low, close = current.get("high"), current.get("low"), previous.get("close")
            if high is None or low is None:
                continue
            ranges.append(max(high - low,
                              abs(high - close) if close is not None else 0.0,
                              abs(low - close) if close is not None else 0.0))
        if ranges:
            context.atr_14 = sum(ranges) / len(ranges)

    # Prior week's extremes, by ISO week, excluding the current one.
    from datetime import date
    def week_of(bar):
        stamp = str(bar.get("date") or bar.get("bar_time") or "")[:10]
        try:
            return date.fromisoformat(stamp).isocalendar()[:2]
        except ValueError:
            return None

    current_week = week_of(bars[-1])
    earlier = [b for b in bars if (w := week_of(b)) is not None
               and current_week is not None and w < current_week]
    if earlier:
        last_week = week_of(earlier[-1])
        week_bars = [b for b in earlier if week_of(b) == last_week]
        highs = [b["high"] for b in week_bars if b.get("high") is not None]
        lows = [b["low"] for b in week_bars if b.get("low") is not None]
        if highs and lows:
            context.prev_week_high = max(highs)
            context.prev_week_low = min(lows)
            context.prev_week_close = week_bars[-1].get("close")

    if len(bars) >= 6:
        closes = [b["close"] for b in bars[-6:]]
        context.daily_trend = "UP" if closes[-1] > closes[0] else (
            "DOWN" if closes[-1] < closes[0] else "FLAT")
    return context


def live_feature_rows(
    intraday_bars: Sequence[dict[str, Any]], daily_history: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Feature rows for today's session so far, using the same engine the
    backtest used. Causal, so the last row is what a strategy sees now."""
    bars = [b for b in (_bar(row) for row in intraday_bars) if b]
    if not bars:
        return []
    return sif.compute_session_features(bars, build_session_context(daily_history))


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def signals_on_latest_bar(
    rows: Sequence[dict[str, Any]], enabled: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Which strategies fire on the newest closed bar.

    Only the last row counts. A signal that fired earlier in the session
    has already passed - acting on it now would be entering a setup that
    is no longer live, which is exactly the stale-signal bug that once had
    the old ORB reporting a long-since-reversed breakout all morning."""
    if not rows:
        return []
    last_index = len(rows) - 1
    fired: list[dict[str, Any]] = []

    for spec in NEW_STRATEGY_SPECS:
        play_type = spec["play_type"]
        if enabled is not None and not enabled.get(config_flag(play_type)):
            continue
        try:
            hits = spec["signal"](rows)
        except Exception:
            # A single strategy's signal must never take down the scan.
            continue
        for index, direction in hits:
            if index != last_index:
                continue
            fired.append({
                "play_type": play_type,
                "label": spec["label"],
                "rank": spec["rank"],
                "side": "call" if direction == "LONG" else "put",
                "direction": direction,
                "bar_time": rows[index]["bar_time"],
                "spot_at_signal": rows[index]["close"],
                "regime": rows[index].get("regime"),
                "reason": f"{spec['label']} fired on {rows[index]['bar_time'][11:16]}",
            })
    return fired


def default_flags() -> dict[str, bool]:
    """All 14 default to paused. A brand-new strategy must be switched on
    deliberately - the same rule every other play type follows, so a
    missing config key can never silently start trading real size."""
    return {config_flag(play_type): False for play_type in NEW_STRATEGY_PLAY_TYPES}


# ---------------------------------------------------------------------------
# Contract selection and exits
# ---------------------------------------------------------------------------
#
# Delta band, ask ceiling and risk cap mirror the surviving live strategies
# so these 14 take the same size and liquidity risk as SPY_KEY_LEVELS, not
# a looser version of it.
NEW_STRATEGY_DELTA_MIN = 0.40
NEW_STRATEGY_DELTA_MAX = 0.60
NEW_STRATEGY_MAX_CONTRACT_ASK = 5.00
NEW_STRATEGY_MAX_RISK_PER_TRADE = 500.0

# Exit shape, in option-premium percent.
#
# NOT the +50/-50 the retired 0DTE strategies used. Phase 5 measured that
# shape losing money on every strategy tested: it forces an ~8-minute hold
# on contracts that need ~40 minutes to work, and a symmetric target/stop
# needs a win rate above 50% just to break even, which theta and the spread
# take away. A wider target with a deeper stop was the only shape that
# turned a positive underlying edge into positive option P/L (+$211,726 at
# PF 1.56 on gap continuation, against -$156,222 for +50/-50).
#
# Honest limit: that was validated on gap continuation specifically. For the
# other strategies it is the best-supported shape available rather than an
# individually measured one, which is a reason to watch the early live
# results rather than trust these numbers.
NEW_STRATEGY_TARGET_PCT = 200.0
NEW_STRATEGY_STOP_PCT = -80.0
NEW_STRATEGY_LAST_EXIT_MINUTE = 375        # 15:45 - flat before expiry


def scan_new_strategy_candidates(
    chain: Sequence[dict[str, Any]],
    signal: dict[str, Any],
    expiration: str,
    spot_price: float,
) -> list[dict[str, Any]]:
    """Candidate builder shared by all 14. `signal` is one entry from
    signals_on_latest_bar.

    candidate_to_row reads cost_or_credit/pop/max_profit/max_risk/breakeven/
    option_symbol straight off every candidate, so a missing one KeyErrors
    the moment a real trade opens rather than merely looking incomplete."""
    import spy_scanner as ss

    kind = signal["side"]
    candidates: list[dict[str, Any]] = []
    for option in chain:
        if option.get("option_type") != kind:
            continue
        if not ss.option_has_liquidity(option):
            continue
        delta = abs(ss.greek(option, "delta") or 0.0)
        if not NEW_STRATEGY_DELTA_MIN <= delta <= NEW_STRATEGY_DELTA_MAX:
            continue
        ask = ss.as_float(option.get("ask"), 0.0) or 0.0
        bid = ss.as_float(option.get("bid"), 0.0) or 0.0
        if ask <= 0 or ask > NEW_STRATEGY_MAX_CONTRACT_ASK:
            continue
        if ask * 100 > NEW_STRATEGY_MAX_RISK_PER_TRADE:
            continue
        strike = float(option["strike"])
        max_profit = "UNLIMITED" if kind == "call" else round(max((strike - ask) * 100, 0), 2)
        candidates.append({
            "play_type": signal["play_type"],
            "call_or_put": kind,
            "strike": ss.fmt_strike(strike),
            "expiration": expiration,
            "entry_price": round(ask, 2),
            "cost_or_credit": str(round(ask, 2)),
            "delta": round(delta, 4),
            "theta": round(ss.greek(option, "theta") or 0.0, 4),
            "iv": round(ss.iv_value(option), 4) if ss.iv_value(option) is not None else "",
            "pop": round(delta * 100, 1),
            "max_profit": max_profit,
            "max_risk": round(ask * 100, 2),
            "breakeven": round(strike + ask if kind == "call" else strike - ask, 2),
            "open_interest": ss.open_interest_value(option),
            "option_volume": ss.option_volume_value(option),
            "bid_ask_width": round(max(ask - bid, 0), 2),
            "option_symbol": option.get("symbol") or ss.option_symbol(
                "SPY", expiration, kind, strike),
            "spot_at_entry": spot_price,
            "score": round(delta * 100, 1),
            "setup_reason": signal["reason"],
            "market_regime": signal.get("regime") or "UNKNOWN",
        })
    # Cheapest real contract that still clears the delta band.
    candidates.sort(key=lambda c: c["entry_price"])
    return candidates


def new_strategy_exit_signal(
    entry_price: float, mark: float, minutes_remaining: float, peak_pct: float = 0.0,
) -> tuple[str, str]:
    """Exit for all 14, in option-premium percent - the same units the rest
    of the live system manages positions in."""
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    pnl_pct = (mark - entry_price) / entry_price * 100.0

    if pnl_pct <= NEW_STRATEGY_STOP_PCT:
        return "STOP OUT", (
            f"down {pnl_pct:.0f}%, past the {NEW_STRATEGY_STOP_PCT:.0f}% stop"
        )
    if pnl_pct >= NEW_STRATEGY_TARGET_PCT:
        return "TAKE PROFIT", (
            f"up {pnl_pct:.0f}%, past the {NEW_STRATEGY_TARGET_PCT:.0f}% target"
        )
    if minutes_remaining <= 15:
        return "EOD CLOSE", "closing ahead of same-day expiration - never holds overnight"
    return "HOLD", "no exit condition met"
