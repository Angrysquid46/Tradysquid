"""Backtest adapters for the strategies currently live on Discord.

These call the **real** functions out of `spy_scanner` rather than
reimplementing them. Reimplementation would let the backtest drift away
from what is actually deployed, and a ranking built on a drifted copy
would be worse than no ranking at all.

Excluded by owner direction: `evolve_bot`, which is a controlled
experiment with its own venv, Discord category and trade log.

## What the live system actually is

Reading the deployed code rather than the docs turns up something that
matters for any "top N" exercise:

**14 live strategies share 4 entry signals.**

| Entry signal | Live strategies using it |
|---|---|
| Opening-range breakout on 1-min bars | `SPY_0DTE_1M` + all 10 `SPY_RATCHET_*` = **11** |
| Opening-range breakout on 5-min bars | `SPY_0DTE_5M` |
| Key-levels (10 references + 1m/3m/5m agreement) | `SPY_KEY_LEVELS` |
| Expansion (EMA 20/200 + MACD across 15m/30m/1h) | `SPY_EXPANSION_LEVEL` |

The 10 ratchet variants are not 10 ideas. They are one entry with ten
exit shapes, and those shapes are defined in **option-premium percent**
(`step_pct` / `stop_pct` applied to `(mark - entry)/entry`), which cannot
be measured from underlying bars at all. Ranking them against each other
requires the Phase 5 option model; ranking their *entry* does not, and
that is what this module supplies.

A second correction worth recording: CLAUDE.md still says `SPY_0DTE_1M`
enters on a live TradingView alert. That has not been true since the
webhook path was retired after four separate incidents - the deployed
code comments say so explicitly and every 0DTE-family strategy now uses
the self-contained Python opening-range signal. Which is good news here:
**every live entry is reproducible from bars.**
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Sequence

import spy_scanner as ss

SignalFn = Callable[[Sequence[dict[str, Any]]], list[tuple[int, str]]]

# Expansion reads EMA 200 on 15m/30m/60m bars, which needs far more than
# one session: 200 x 60 minutes is about 31 trading days. Keep enough
# 1-minute history to build all three.
EXPANSION_HISTORY_SESSIONS = 40
MIN_ENTRY_MINUTE = 5
LAST_ENTRY_MINUTE = 360


def _tradeable(row: dict[str, Any]) -> bool:
    minute = row.get("minutes_since_open")
    return (
        minute is not None
        and MIN_ENTRY_MINUTE <= minute <= LAST_ENTRY_MINUTE
        and row.get("close") is not None
    )


def _aggregate(rows: Sequence[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    """Roll 1-minute rows up into `minutes`-minute bars, keyed on the bar
    that closes each bucket so nothing is emitted before it completes."""
    buckets: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for row in rows:
        since_open = row.get("minutes_since_open")
        if since_open is None or since_open < 0:
            continue
        key = since_open // minutes
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": row.get("volume") or 0.0,
                "last_index": None, "complete": False,
            }
            order.append(key)
            bucket = buckets[key]
        else:
            bucket["high"] = max(bucket["high"], row["high"])
            bucket["low"] = min(bucket["low"], row["low"])
            bucket["close"] = row["close"]
            bucket["volume"] += row.get("volume") or 0.0
        bucket["complete"] = (since_open % minutes) == minutes - 1
    return [buckets[k] for k in order]


# ---------------------------------------------------------------------------
# SPY_0DTE_1M / SPY_0DTE_5M / all 10 SPY_RATCHET_* - one shared entry
# ---------------------------------------------------------------------------

def live_opening_range_breakout(bar_minutes: int = 1) -> SignalFn:
    """The deployed `spy_0dte_opening_range_signal`, called directly.

    The live function reads the opening range from the first
    `SPY_0DTE_OPENING_RANGE_MINUTES` of bars and then compares the
    **latest** bar against it - deliberately, after a real incident where
    reading the first bar that ever broke out left the signal reporting a
    stale bullish direction all morning while price collapsed. So it
    re-qualifies on every bar that sits outside the range, and the
    engine's one-position-at-a-time rule does the rest, exactly as the
    live cooldown does.

    Passing `opening_range_bars + [current_bar]` gives the live function
    precisely the two things it reads, which keeps this faithful and O(1)
    per bar instead of re-slicing the whole session."""
    bars_needed = max(ss.SPY_0DTE_OPENING_RANGE_MINUTES // bar_minutes, 1)

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        if bar_minutes == 1:
            source = list(rows)
            index_of = list(range(len(rows)))
        else:
            aggregated = _aggregate(rows, bar_minutes)
            source, index_of = [], []
            position = 0
            for row_index, row in enumerate(rows):
                since_open = row.get("minutes_since_open")
                if since_open is None or since_open < 0:
                    continue
                if (since_open % bar_minutes) == bar_minutes - 1:
                    if position < len(aggregated):
                        source.append(aggregated[position])
                        index_of.append(row_index)
                        position += 1

        if len(source) <= bars_needed:
            return []
        opening_range = source[:bars_needed]

        out: list[tuple[int, str]] = []
        for position in range(bars_needed, len(source)):
            row_index = index_of[position]
            if not _tradeable(rows[row_index]):
                continue
            context = ss.spy_0dte_opening_range_signal(
                opening_range + [source[position]], bar_minutes=bar_minutes
            )
            if not context.get("qualified"):
                continue
            regime = context.get("regime", "")
            if regime.startswith("BULLISH"):
                out.append((row_index, "LONG"))
            elif regime.startswith("BEARISH"):
                out.append((row_index, "SHORT"))
        return out

    return signals


# ---------------------------------------------------------------------------
# SPY_KEY_LEVELS
# ---------------------------------------------------------------------------

def live_key_levels(sma200_by_session: dict[str, float]) -> SignalFn:
    """The deployed key-levels strategy: ten reference levels, a 15-minute
    opening range, and 1m/3m/5m direction agreement.

    Uses `spy_key_levels_timeframe_direction`, `..._combined_direction`
    and `..._active_level` straight from the live module. The 200-day SMA
    is supplied per session from prior daily closes, since it cannot be
    derived from a single session's bars."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        if not rows:
            return []
        session = rows[0]["session_date"]
        sma200 = sma200_by_session.get(session)
        first = rows[0]

        out: list[tuple[int, str]] = []
        for index in range(len(rows)):
            row = rows[index]
            if not _tradeable(row):
                continue
            price = row["close"]

            levels = {
                "premarket_high": first.get("premarket_high"),
                "premarket_low": first.get("premarket_low"),
                "prior_day_high": row.get("prev_day_high"),
                "prior_day_low": row.get("prev_day_low"),
                "prior_week_high": row.get("prev_week_high"),
                "prior_week_low": row.get("prev_week_low"),
                "opening_range_high": row.get("or15_high"),
                "opening_range_low": row.get("or15_low"),
                "session_vwap": row.get("vwap"),
                "sma_200": sma200,
            }
            # The opening range must have finished forming before it counts
            # as a level; while FORMING it is still a running extreme.
            if row.get("or15_state") == "FORMING":
                levels["opening_range_high"] = None
                levels["opening_range_low"] = None

            name, _level_price = ss.spy_key_levels_active_level(price, levels)
            if name is None:
                continue

            window = rows[max(0, index - 60): index + 1]
            direction = ss.spy_key_levels_combined_direction(
                ss.spy_key_levels_timeframe_direction(list(window)),
                ss.spy_key_levels_timeframe_direction(_aggregate(window, 3)),
                ss.spy_key_levels_timeframe_direction(_aggregate(window, 5)),
            )
            if direction == "BULLISH":
                out.append((index, "LONG"))
            elif direction == "BEARISH":
                out.append((index, "SHORT"))
        return out

    return signals


# ---------------------------------------------------------------------------
# SPY_EXPANSION_LEVEL
# ---------------------------------------------------------------------------

def _aggregate_across_sessions(
    bars: Sequence[dict[str, Any]], minutes: int
) -> tuple[list[dict[str, Any]], list[int]]:
    """Aggregate multi-session 1-minute bars, returning the bars and the
    index in `bars` at which each one closes.

    Buckets are keyed on (session, minute-block) - keying on the minute
    block alone would merge 10:00 on Monday with 10:00 on Tuesday."""
    out: list[dict[str, Any]] = []
    ends: list[int] = []
    key: tuple[str, int] | None = None
    for index, row in enumerate(bars):
        since_open = row.get("minutes_since_open")
        if since_open is None or since_open < 0:
            continue
        current = (row["session_date"], since_open // minutes)
        if current != key:
            key = current
            out.append({"open": row["open"], "high": row["high"],
                        "low": row["low"], "close": row["close"]})
            ends.append(index)
        else:
            bar = out[-1]
            bar["high"] = max(bar["high"], row["high"])
            bar["low"] = min(bar["low"], row["low"])
            bar["close"] = row["close"]
            ends[-1] = index
    return out, ends


def timeframe_read_series(closes: Sequence[float]) -> list[dict[str, Any]]:
    """One EMA/MACD read per bar, computed in a single pass.

    Equivalent to calling `spy_expansion_timeframe_read(closes[:k+1])` for
    every k, but O(N) instead of O(N^2). That equivalence is not an
    assumption: `exponential_moving_average_series` is prefix-stable - it
    seeds at index period-1 from the SMA of the first `period` values and
    smooths forward - so its value at index k depends only on
    `closes[:k+1]`. The MACD line is elementwise, and the signal line is
    an EMA over the non-None suffix of it, so the same property holds
    through the whole chain. `test_timeframe_read_series_matches_the_live
    _function_bar_for_bar` pins it against the live function directly.

    Recomputing per bar cost 26 minutes across the history; this is the
    difference between the ranking being runnable and not."""
    values = list(closes)
    fast_series = ss.exponential_moving_average_series(values, ss.SPY_EXPANSION_MACD_FAST_PERIOD)
    slow_series = ss.exponential_moving_average_series(values, ss.SPY_EXPANSION_MACD_SLOW_PERIOD)
    ema_fast = ss.exponential_moving_average_series(values, ss.SPY_EXPANSION_EMA_FAST_PERIOD)
    ema_slow = ss.exponential_moving_average_series(values, ss.SPY_EXPANSION_EMA_SLOW_PERIOD)

    macd_line = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_series, slow_series)
    ]
    # Index of each valid MACD entry, so a bar can be mapped onto its
    # position within the compacted series the live function builds.
    valid_macd: list[float] = []
    valid_count_at: list[int] = []
    for value in macd_line:
        if value is not None:
            valid_macd.append(value)
        valid_count_at.append(len(valid_macd))

    signal_series = ss.exponential_moving_average_series(
        valid_macd, ss.SPY_EXPANSION_MACD_SIGNAL_PERIOD
    )
    histogram_series = [
        m - sig if sig is not None else None
        for m, sig in zip(valid_macd, signal_series)
    ]
    valid_histogram: list[float] = []
    histogram_count_at: list[int] = []
    for value in histogram_series:
        if value is not None:
            valid_histogram.append(value)
        histogram_count_at.append(len(valid_histogram))

    out: list[dict[str, Any]] = []
    for index in range(len(values)):
        direction = "UNKNOWN"
        fast, slow = ema_fast[index], ema_slow[index]
        if fast is not None and slow is not None:
            if fast > slow:
                direction = "BULLISH"
            elif fast < slow:
                direction = "BEARISH"

        current = previous = None
        macd_valid = valid_count_at[index]
        if macd_valid >= ss.SPY_EXPANSION_MACD_SIGNAL_PERIOD + 1:
            available = histogram_count_at[macd_valid - 1]
            if available >= 2:
                current = valid_histogram[available - 1]
                previous = valid_histogram[available - 2]
        out.append({
            "ema_direction": direction,
            "macd_color": ss.spy_expansion_macd_color(current, previous),
        })
    return out


def _expansion_signals_for_session(
    rows: Sequence[dict[str, Any]], history: Sequence[dict[str, Any]]
) -> list[tuple[int, str]]:
    """One session's expansion signals, given enough prior 1-minute bars
    to build a 200-period EMA on 15m/30m/60m.

    The EMA/MACD reads are computed once per higher-timeframe bar, not
    once per minute. They can only change when such a bar closes, and the
    naive version re-aggregated ~16,000 history bars on every single
    minute - 23 minutes of work for the full history instead of about
    two. Same functions, same math, same values; just not recomputed
    hundreds of times for an answer that has not moved."""
    out: list[tuple[int, str]] = []
    if not rows:
        return out

    first = rows[0]
    levels = {
        "PDH": first.get("prev_day_high"), "PDL": first.get("prev_day_low"),
        "PWH": first.get("prev_week_high"), "PWL": first.get("prev_week_low"),
        "PMH": first.get("premarket_high"), "PML": first.get("premarket_low"),
    }
    if not any(value for value in levels.values()):
        return out

    combined = list(history) + list(rows)
    offset = len(history)

    # read_at[minutes][row_index] -> the read in force at that minute,
    # carried forward from the last CLOSED higher-timeframe bar.
    read_at: dict[int, list[dict[str, Any] | None]] = {}
    for minutes in (15, 30, 60):
        bars, ends = _aggregate_across_sessions(combined, minutes)
        reads = timeframe_read_series([bar["close"] for bar in bars])
        timeline: list[dict[str, Any] | None] = [None] * len(rows)
        current: dict[str, Any] | None = None
        position = 0
        for index in range(len(rows)):
            combined_index = offset + index
            # Advance through any higher-timeframe bars that closed at or
            # before this minute - only a CLOSED bar may inform a read.
            while position < len(bars) and ends[position] <= combined_index:
                current = reads[position]
                position += 1
            timeline[index] = current
        read_at[minutes] = timeline

    for index, row in enumerate(rows):
        if not _tradeable(row):
            continue
        price = row["close"]
        code, _price, _distance = ss.spy_expansion_nearest_level(price, levels)
        if code is None:
            continue

        reads = {
            label: read_at[minutes][index]
            for label, minutes in (("15m", 15), ("30m", 30), ("1h", 60))
        }
        if any(value is None for value in reads.values()):
            continue

        signal = ss.spy_expansion_signal(
            spot_price=price, levels=levels, timeframe_reads=reads
        )
        state = signal.get("state")
        if state == "CALL_ENTRY_QUALIFIED":
            out.append((index, "LONG"))
        elif state == "PUT_ENTRY_QUALIFIED":
            out.append((index, "SHORT"))
    return out


def build_expansion_cache(load_sessions) -> dict[str, list[tuple[int, str]]]:
    """Precompute expansion signals for every session in one ordered walk.

    Expansion is the only live strategy that needs cross-session history,
    and a signal function that quietly accumulated state would give
    different answers on a second pass. Precomputing sidesteps that
    entirely."""
    cache: dict[str, list[tuple[int, str]]] = {}
    history: deque[dict[str, Any]] = deque(maxlen=EXPANSION_HISTORY_SESSIONS * 400)
    for session, rows in load_sessions():
        cache[session] = _expansion_signals_for_session(rows, history)
        history.extend(rows)
    return cache


def live_expansion(cache: dict[str, list[tuple[int, str]]]) -> SignalFn:
    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        if not rows:
            return []
        return cache.get(rows[0]["session_date"], [])
    return signals


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def daily_sma200(session_ohlc: Sequence[tuple[str, dict[str, float]]]) -> dict[str, float]:
    """200-day SMA of prior closes, per session. Strictly prior - the
    session's own close is not in its own average."""
    out: dict[str, float] = {}
    closes: list[float] = []
    for session, ohlc in session_ohlc:
        if len(closes) >= 200:
            out[session] = sum(closes[-200:]) / 200
        closes.append(ohlc["close"])
    return out


# Recorded so the ranking can state plainly that these are one entry with
# many exits, not many independent strategies.
SHARED_ENTRY_GROUPS: dict[str, list[str]] = {
    "LIVE ORB 1-min entry": ["SPY_0DTE_1M"] + list(ss.SPY_RATCHET_PLAY_TYPES),
    "LIVE ORB 5-min entry": ["SPY_0DTE_5M"],
    "LIVE Key-Levels entry": ["SPY_KEY_LEVELS"],
    "LIVE Expansion entry": ["SPY_EXPANSION_LEVEL"],
}

# The adapters impose an entry window (minutes 5-360) that the live
# scanners do not have, inherited from the research strategies so the
# comparison is like-for-like. That is a real difference from production,
# so it was checked rather than assumed: relaxing it to minute 380 moves
# ORB 1-min from +0.0004 (t=+0.39) to +0.0009 (t=+0.95) and ORB 5-min
# from -0.0004 (t=-0.64) to +0.0002 (t=+0.27). Both stay indistinguishable
# from zero, so the finding does not depend on the window.
ENTRY_WINDOW_SENSITIVITY = (
    "Relaxing the entry window from minute 360 to 380 leaves both ORB variants "
    "statistically indistinguishable from zero (1-min t=+0.39 -> +0.95, 5-min "
    "t=-0.64 -> +0.27), so the result is not an artefact of the window."
)

EXIT_SHAPES_NEED_OPTION_MODEL = (
    "Every live exit is defined in option-premium percent - SPY_0DTE's "
    "+50%/-50% with a one-time floor raise at +30%, and each ratchet variant's "
    "step_pct/stop_pct floor. None of those can be measured from underlying "
    "bars, so the 10 ratchet variants are indistinguishable here: they share "
    "one entry and differ only in exit shape. Ranking them against each other "
    "requires the Phase 5 option model."
)


def build_live_variants(conn) -> dict[str, dict[str, SignalFn]]:
    """The live Discord strategies, as backtestable entry signals."""
    import spy_backtest as bt
    import spy_intraday_features as sif

    session_ohlc = sif.all_session_ohlc(conn)
    sma200 = daily_sma200(session_ohlc)
    expansion_cache = build_expansion_cache(lambda: bt.load_sessions(conn))

    return {
        "LIVE SPY_0DTE (ORB)": {
            "1-min bars (1M + 10 ratchets)": live_opening_range_breakout(1),
            "5-min bars (5M)": live_opening_range_breakout(5),
        },
        "LIVE SPY_KEY_LEVELS": {"deployed rules": live_key_levels(sma200)},
        "LIVE SPY_EXPANSION_LEVEL": {"deployed rules": live_expansion(expansion_cache)},
    }
