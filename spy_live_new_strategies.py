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

# SPY_KEY_LEVELS is rank 11 of the locked 15. Its ENTRY lives in
# spy_scanner (it predates this module and is not re-implemented here), but
# it gets a channel and card routing on the same footing as the other 14 -
# otherwise the one surviving original strategy is the only one without its
# own channel, which is an inconsistency rather than a design.
KEY_LEVELS_SPEC: dict[str, Any] = {
    "play_type": "SPY_KEY_LEVELS", "rank": 11, "label": "Key-Levels Strategy",
    "signal": None,          # entry handled by spy_scanner, not this module
}

# Channel/reporting roster: the 14 promoted strategies plus Key-Levels.
# Kept separate from NEW_STRATEGY_SPECS, which is the SCANNING roster - only
# the 14 are scanned here, and adding Key-Levels to that would double-run it.
CHANNEL_ROSTER: tuple[dict[str, Any], ...] = NEW_STRATEGY_SPECS + (KEY_LEVELS_SPEC,)

NEW_STRATEGY_PLAY_TYPES = tuple(spec["play_type"] for spec in NEW_STRATEGY_SPECS)
NEW_STRATEGY_BY_PLAY_TYPE = {spec["play_type"]: spec for spec in NEW_STRATEGY_SPECS}
CHANNEL_ROSTER_BY_PLAY_TYPE = {spec["play_type"]: spec for spec in CHANNEL_ROSTER}


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


def build_session_context(
    daily_history: Sequence[dict[str, Any]], *, session: str | None = None
) -> sif.SessionContext:
    """Prior-session context from daily bars - everything knowable before
    the open.

    `session` is today's date, and dropping it matters: the provider's daily
    history INCLUDES a partial bar for the current session, so using the
    last bar blindly would make today's own high/low/close the "previous
    day" levels. That is lookahead - a strategy would be trading against a
    level derived from the very move it is trying to predict."""
    context = sif.SessionContext()
    bars = [b for b in daily_history if b.get("close") is not None]
    if session:
        bars = [b for b in bars if str(b.get("date") or b.get("bar_time") or "")[:10] < session]
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
    session = bars[-1]["bar_time"][:10]
    return sif.compute_session_features(
        bars, build_session_context(daily_history, session=session)
    )


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
# Each strategy carries its OWN exit, derived from the target/stop the
# backtest actually measured as best for it (docs/BACKTEST_RESULTS.md) -
# not one shape flattened across all 14, which is what an earlier version
# of this did and which threw away a real per-strategy result.
#
# Converting the measured ATR exits into option-premium percent: at SPY's
# ~$2.30 average ATR and ~0.50 delta on a near-ATM contract, an underlying
# move of N ATR moves premium by roughly N x 2.30 x 0.50 dollars. Against a
# typical ~$1.50 entry that gives:
#
#   2.00 ATR -> ~+153%     1.00 ATR -> ~+77%
#   1.50 ATR -> ~+115%     0.75 ATR -> ~-58%
#   0.50 ATR -> ~+38%      0.50 ATR -> ~-38%
#
# Rounded to sensible levels below. Time stops are carried across directly
# in minutes, since three of the 15 measured better with one.
NEW_STRATEGY_LAST_EXIT_MINUTE = 375        # 15:45 - flat before expiry
NEW_STRATEGY_DEFAULT_TARGET_PCT = 150.0
NEW_STRATEGY_DEFAULT_STOP_PCT = -75.0

# play_type -> (target_pct, stop_pct, time_stop_minutes | None)
NEW_STRATEGY_EXITS: dict[str, tuple[float, float, int | None]] = {
    "SPY_GAP_CONT_50":      (150.0, -75.0, None),   # measured t2.0/s1.0
    "SPY_FAILED_BREAK":     (115.0, -75.0, None),   # t1.5/s1.0
    "SPY_GAP_CONT_25":      (115.0, -75.0, None),   # t1.5/s1.0
    "SPY_SWEEP_10":         (150.0, -75.0, None),   # t2.0/s1.0
    "SPY_SWEEP_5":          (115.0, -75.0, None),   # t1.5/s1.0
    "SPY_MOMENTUM_ADX25":   (115.0, -75.0, None),   # t1.5/s1.0
    "SPY_TOD_MIDDAY":       (150.0, -75.0, None),   # t2.0/s1.0
    "SPY_CONFLUENCE_4":     (115.0, -75.0, None),   # t1.5/s1.0
    "SPY_TOD_FINAL30":      (115.0, -75.0, 30),     # t1.5/s1.0/m30
    "SPY_MTF_4OF4":         (150.0, -75.0, None),   # t2.0/s1.0
    "SPY_EXHAUSTION_1ATR":  (40.0,  -40.0, 30),     # t0.5/s0.5/m30
    "SPY_GAP_CONT_100":     (150.0, -75.0, None),   # t2.0/s1.0
    "SPY_FIRST_PULLBACK":   (75.0,  -58.0, None),   # t1.0/s0.75
    "SPY_OPENING_GAP_FADE": (40.0,  -40.0, 15),     # t0.5/s0.5/m15
}


def exit_rules_for(play_type: str) -> tuple[float, float, int | None]:
    """This strategy's own target/stop/time-stop."""
    return NEW_STRATEGY_EXITS.get(
        play_type, (NEW_STRATEGY_DEFAULT_TARGET_PCT, NEW_STRATEGY_DEFAULT_STOP_PCT, None)
    )


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
    entry_price: float,
    mark: float,
    minutes_remaining: float,
    peak_pct: float = 0.0,
    *,
    play_type: str | None = None,
    minutes_held: float | None = None,
) -> tuple[str, str]:
    """Exit in option-premium percent, using THIS strategy's own rules.

    play_type selects the target/stop/time-stop the backtest measured for
    that specific strategy. Three of them exit better on a time stop than
    on price, so minutes_held is honoured when the caller can supply it."""
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    target_pct, stop_pct, time_stop = exit_rules_for(play_type or "")
    pnl_pct = (mark - entry_price) / entry_price * 100.0

    if pnl_pct <= stop_pct:
        return "STOP OUT", f"down {pnl_pct:.0f}%, past this strategy's {stop_pct:.0f}% stop"
    if pnl_pct >= target_pct:
        return "TAKE PROFIT", f"up {pnl_pct:.0f}%, past this strategy's {target_pct:.0f}% target"
    if time_stop is not None and minutes_held is not None and minutes_held >= time_stop:
        return "TIME STOP", (
            f"held {minutes_held:.0f} minutes at {pnl_pct:+.0f}% - past this "
            f"strategy's {time_stop}-minute time stop"
        )
    if minutes_remaining <= 15:
        return "EOD CLOSE", "closing ahead of same-day expiration - never holds overnight"
    return "HOLD", "no exit condition met"


# ---------------------------------------------------------------------------
# Discord wiring
# ---------------------------------------------------------------------------

def channel_slug(play_type: str) -> str:
    """Discord channel name for a strategy, rank-prefixed.

    The prefix is not decoration: Discord sorts channels alphabetically
    within a category, so `s01-`...`s15-` makes the category read in
    shortlist order - best performer first - without any manual ordering.
    """
    spec = CHANNEL_ROSTER_BY_PLAY_TYPE[play_type]
    body = play_type.removeprefix("SPY_").lower().replace("_", "-")
    return f"s{spec['rank']:02d}-{body}"


def performance_key(play_type: str) -> str:
    return f"performance_{play_type.removeprefix('SPY_').lower()}"


def results_key(play_type: str) -> str:
    return f"results_{play_type.removeprefix('SPY_').lower()}"


def channel_names() -> dict[str, str]:
    """CHANNEL_NAMES entries for all 14.

    Both the performance card and the results feed route to the strategy's
    OWN channel - one channel per strategy, per the locked Phase 7 scope,
    so a strategy's card and its trade history sit together instead of
    being scattered across two shared feeds."""
    mapping: dict[str, str] = {}
    for play_type in (spec["play_type"] for spec in CHANNEL_ROSTER):
        channel = channel_slug(play_type)
        mapping[performance_key(play_type)] = channel
        mapping[results_key(play_type)] = channel
    return mapping


def report_variants() -> tuple[tuple[str, str, str, str], ...]:
    """(play_type, performance_key, results_key, label) for each strategy,
    in the shape performance_reconciliation.STRATEGY_VARIANTS expects."""
    # Key-Levels is deliberately excluded here: performance_reconciliation
    # already registers it under its own legacy keys, and adding it again
    # would give one strategy two competing ledgers.
    return tuple(
        (spec["play_type"], performance_key(spec["play_type"]),
         results_key(spec["play_type"]), spec["label"])
        for spec in NEW_STRATEGY_SPECS
    )


def report_markers() -> dict[str, tuple[str, ...]]:
    """Search markers keeping each strategy's cards distinct.

    These must be unique per strategy or one strategy's card would be found
    and overwritten by another's update - the markers are how an existing
    card is located to edit in place."""
    markers: dict[str, tuple[str, ...]] = {}
    for spec in NEW_STRATEGY_SPECS:
        label = spec["label"]
        markers[performance_key(spec["play_type"])] = (
            f"{label} Monthly Performance Index",
            f"{label} Monthly Performance ·",
            f"{label} Monthly Trade History ·",
        )
        markers[results_key(spec["play_type"])] = (
            f"{label} Results",
            f"{label} Trade History ·",
        )
    return markers


def channel_specs() -> list[tuple[str, str, str]]:
    """(category, channel, description) for sync_discord_structure."""
    specs = []
    for spec in CHANNEL_ROSTER:
        play_type = spec["play_type"]
        if play_type in NEW_STRATEGY_EXITS:
            target, stop, time_stop = exit_rules_for(play_type)
            timing = f", {time_stop}-minute time stop" if time_stop else ""
            exit_text = f"own exit (+{target:.0f}%/{stop:.0f}% of premium{timing})"
        else:
            # Key-Levels manages itself in spy_scanner under its own R-multiple
            # rule. Quoting this module's default here would state an exit it
            # does not use.
            exit_text = "own exit rules (managed by its original evaluator)"
        specs.append((
            "STRATEGIES", channel_slug(play_type),
            f"#{spec['rank']} of the tested set - {spec['label']}. "
            f"Own entry signal, {exit_text}. "
            f"Live P/L card plus this strategy's own trade history.",
        ))
    return specs
