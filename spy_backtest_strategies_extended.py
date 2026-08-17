"""Phase 4 strategy definitions - the rest of the spec's library.

Covers Strategies 5-9, 11-19, 21, 22 and the two directional quantified
playbooks, using the same signal contract as Phase 3: return entry
indices only, read nothing past bar i, let the engine handle exits.

Two items from the spec's list of 22 are deliberately absent, for
reasons that are about the data rather than the idea:

- **Strategy 20 (Relative-Strength Confirmed Breakout)** needs intraday
  QQQ/IWM/DIA and breadth to confirm SPY against. None of that exists in
  the archive - it is SPY-only. Implementing it against SPY alone would
  not be the strategy, so it is reported as untestable rather than
  approximated into something that could be mistaken for a result.
- **Playbook 3 (Mid-Day Theta Burn)** is an iron condor. It has no
  underlying entry to measure; its entire P/L is option premium decay.
  That belongs to Phase 5, where options are modelled.

**Strategy 5 (Premarket High/Low Breakout)** is included but only 226 of
3,347 sessions carry premarket bars, nearly all in 2020. Its sample is
reported with that caveat attached and should not be read as comparable
to the others.
"""

from __future__ import annotations

from typing import Any, Sequence

from spy_backtest_strategies import SignalFn, _tradeable

TREND_REGIMES = {"STRONG_BULL_TREND", "STRONG_BEAR_TREND", "WEAK_BULL_TREND", "WEAK_BEAR_TREND"}
RANGE_REGIMES = {"RANGE", "COMPRESSION", "UNCERTAIN"}


def _level_break(
    rows: Sequence[dict[str, Any]], high_key: str, low_key: str, *, retest: bool
) -> list[tuple[int, str]]:
    """Shared break/retest/hold engine for level-based strategies.

    Strategies 5 and 6 are the same shape over different levels - the
    premarket extremes and the previous day's extremes - so they share
    one implementation rather than two that can drift apart."""
    out: list[tuple[int, str]] = []
    broken_up = broken_down = False

    for i in range(1, len(rows)):
        row, prev = rows[i], rows[i - 1]
        level_h, level_l = row.get(high_key), row.get(low_key)
        if not _tradeable(row) or level_h is None or level_l is None:
            continue

        if not broken_up and row["close"] > level_h:
            broken_up = True
            if not retest:
                out.append((i, "LONG"))
        elif broken_up and retest and row["low"] <= level_h < row["close"] and row["close"] > prev["high"]:
            out.append((i, "LONG"))
            broken_up = False                       # one retest entry per break

        if not broken_down and row["close"] < level_l:
            broken_down = True
            if not retest:
                out.append((i, "SHORT"))
        elif broken_down and retest and row["high"] >= level_l > row["close"] and row["close"] < prev["low"]:
            out.append((i, "SHORT"))
            broken_down = False

    return out


# --------------------------------------------------------------------------
# 5 / 6 - level breakouts
# --------------------------------------------------------------------------

def premarket_breakout(*, retest: bool = True) -> SignalFn:
    """Only fires on the ~6.8% of sessions that have premarket bars."""
    def signals(rows):
        return _level_break(rows, "premarket_high", "premarket_low", retest=retest)
    return signals


def prev_day_breakout(*, retest: bool = True) -> SignalFn:
    def signals(rows):
        return _level_break(rows, "prev_day_high", "prev_day_low", retest=retest)
    return signals


# --------------------------------------------------------------------------
# 7 / 8 - failed breakout and liquidity sweep
# --------------------------------------------------------------------------

def failed_breakout_reversal(level: str = "prev_day") -> SignalFn:
    """Break a level, fail to hold it, reclaim it, confirm - trade the
    reclaim, not the break. The spec calls this one of the most important
    reversal strategies."""
    high_key, low_key = f"{level}_high", f"{level}_low"

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        below_since: int | None = None
        above_since: int | None = None

        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            level_h, level_l = row.get(high_key), row.get(low_key)
            if level_h is None or level_l is None:
                continue

            # Broke below support, then reclaimed it -> long.
            if row["close"] < level_l:
                below_since = i if below_since is None else below_since
            elif below_since is not None and row["close"] > level_l:
                if _tradeable(row) and row["close"] > prev["high"]:
                    out.append((i, "LONG"))
                below_since = None

            # Broke above resistance, then lost it -> short.
            if row["close"] > level_h:
                above_since = i if above_since is None else above_since
            elif above_since is not None and row["close"] < level_h:
                if _tradeable(row) and row["close"] < prev["low"]:
                    out.append((i, "SHORT"))
                above_since = None
        return out

    return signals


def liquidity_sweep(max_bars_beyond: int = 5, level: str = "prev_day") -> SignalFn:
    """A stricter failed breakout: price must poke through the level and
    reclaim it QUICKLY. A slow grind back is acceptance, not a sweep, and
    the distinction is the whole idea - so the reclaim window is the
    parameter."""
    high_key, low_key = f"{level}_high", f"{level}_low"

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        below_since: int | None = None
        above_since: int | None = None

        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            level_h, level_l = row.get(high_key), row.get(low_key)
            if level_h is None or level_l is None:
                continue

            if row["low"] < level_l:
                below_since = i if below_since is None else below_since
            elif below_since is not None:
                if i - below_since <= max_bars_beyond and _tradeable(row) and row["close"] > level_l:
                    out.append((i, "LONG"))
                below_since = None

            if row["high"] > level_h:
                above_since = i if above_since is None else above_since
            elif above_since is not None:
                if i - above_since <= max_bars_beyond and _tradeable(row) and row["close"] < level_h:
                    out.append((i, "SHORT"))
                above_since = None
        return out

    return signals


# --------------------------------------------------------------------------
# 9 - range extreme reversal
# --------------------------------------------------------------------------

def range_extreme_reversal(*, require_range_regime: bool = True) -> SignalFn:
    """Fade the edges of the session range - but only in a range. The
    spec is explicit that a range strategy needs a trend filter, so the
    filter is exposed as a parameter to show what it is worth."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            if require_range_regime and (row.get("regime") or "") not in RANGE_REGIMES:
                continue
            high, low = row.get("session_high"), row.get("session_low")
            span = row.get("session_range") or 0.0
            if not high or not low or span <= 0:
                continue

            position = (row["close"] - low) / span
            if position <= 0.15 and row["close"] > prev["close"]:
                out.append((i, "LONG"))
            elif position >= 0.85 and row["close"] < prev["close"]:
                out.append((i, "SHORT"))
        return out

    return signals


# --------------------------------------------------------------------------
# 11 - compression then expansion
# --------------------------------------------------------------------------

def compression_breakout(min_compressed_bars: int = 5) -> SignalFn:
    """Quiet range, then a bar that expands out of it."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        run = 0
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if row.get("compression"):
                run += 1
                continue
            expanded = (row.get("compression_ratio") or 0) > 1.5
            if run >= min_compressed_bars and expanded and _tradeable(row):
                if row["close"] > prev["high"]:
                    out.append((i, "LONG"))
                elif row["close"] < prev["low"]:
                    out.append((i, "SHORT"))
            run = 0
        return out

    return signals


# --------------------------------------------------------------------------
# 12 / 13 - structure strategies
# --------------------------------------------------------------------------

def first_pullback_after_drive(drive_atr: float = 0.75) -> SignalFn:
    """Strong opening move, then the FIRST controlled pullback. The spec
    is explicit: do not chase the drive itself."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        drive: str | None = None
        taken = False

        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            atr, open_price = row.get("atr_14"), row.get("session_open")
            if not atr or not open_price:
                continue
            minute = row.get("minutes_since_open") or 0

            if drive is None and 10 <= minute <= 30:
                move = (row["close"] - open_price) / atr
                if move >= drive_atr:
                    drive = "LONG"
                elif move <= -drive_atr:
                    drive = "SHORT"
            elif drive and not taken and _tradeable(row):
                if drive == "LONG" and row.get("above_vwap") and row.get("structure") == "HIGHER_LOW" \
                        and row["close"] > prev["high"]:
                    out.append((i, "LONG"))
                    taken = True
                elif drive == "SHORT" and not row.get("above_vwap") and row.get("structure") == "LOWER_HIGH" \
                        and row["close"] < prev["low"]:
                    out.append((i, "SHORT"))
                    taken = True
        return out

    return signals


def structure_reversal(*, require_vwap: bool = False) -> SignalFn:
    """First higher-low after a decline / lower-high after an advance.
    The spec asks for this tested both with and without VWAP
    confirmation, so that is the parameter."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            structure = row.get("structure")
            if structure == "HIGHER_LOW" and row["close"] > prev["high"]:
                if require_vwap and not row.get("above_vwap"):
                    continue
                out.append((i, "LONG"))
            elif structure == "LOWER_HIGH" and row["close"] < prev["low"]:
                if require_vwap and row.get("above_vwap"):
                    continue
                out.append((i, "SHORT"))
        return out

    return signals


# --------------------------------------------------------------------------
# 14 / 15 - momentum continuation and exhaustion
# --------------------------------------------------------------------------

def momentum_continuation(min_adx: float = 25.0, *, require_alignment: bool = True) -> SignalFn:
    """Momentum, small consolidation, continuation break - not the
    largest candle. min_adx doubles as the filter-strength sweep."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row) or (row.get("adx_14") or 0) < min_adx:
                continue
            alignment = row.get("alignment") or ""
            rising = (row.get("ema_9_slope") or 0) > 0

            if rising and row.get("above_ema_5_10") and row["close"] > prev["high"]:
                if require_alignment and alignment not in ("BULLISH", "STRONG_BULLISH"):
                    continue
                out.append((i, "LONG"))
            elif (not rising) and not row.get("above_ema_5_10") and row["close"] < prev["low"]:
                if require_alignment and alignment not in ("BEARISH", "STRONG_BEARISH"):
                    continue
                out.append((i, "SHORT"))
        return out

    return signals


def momentum_exhaustion(extension_atr: float = 1.5) -> SignalFn:
    """Extended move that fails and breaks structure the other way.

    The spec warns explicitly against shorting a rally merely because it
    looks too high, so extension alone is never the trigger - a structure
    break is required."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            distance = row.get("vwap_distance_atr")
            if distance is None:
                continue
            if distance >= extension_atr and row.get("structure") == "LOWER_HIGH" \
                    and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
            elif distance <= -extension_atr and row.get("structure") == "HIGHER_LOW" \
                    and row["close"] > prev["high"]:
                out.append((i, "LONG"))
        return out

    return signals


# --------------------------------------------------------------------------
# 16 / 17 - confluence and expected move
# --------------------------------------------------------------------------

def multi_level_confluence(min_levels: int = 3) -> SignalFn:
    """Several independent references at one price, THEN confirmation.
    The spec is emphatic that touching four levels is not itself a
    trade."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row) or (row.get("confluence_count") or 0) < min_levels:
                continue
            if row["close"] > prev["high"]:
                out.append((i, "LONG"))
            elif row["close"] < prev["low"]:
                out.append((i, "SHORT"))
        return out

    return signals


def expected_move_breakout(consumed_pct: float) -> SignalFn:
    """Continuation while less than `consumed_pct` of the expected move
    has been used up.

    Caveat carried through the report: the expected move is derived from
    daily ATR, not a 0DTE implied move, because no intraday IV exists in
    this archive."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            consumed = row.get("move_consumed_pct")
            if consumed is None or consumed > consumed_pct:
                continue
            if row.get("above_vwap") and row["close"] > prev["high"]:
                out.append((i, "LONG"))
            elif (not row.get("above_vwap")) and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
        return out

    return signals


# --------------------------------------------------------------------------
# 18 / 19 - time of day and timeframe alignment
# --------------------------------------------------------------------------

def time_of_day_momentum(bucket: str) -> SignalFn:
    """The same momentum rule, restricted to one part of the session.
    The spec's point is that SPY does not behave identically all day, so
    this holds the rule fixed and varies only the clock."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row) or row.get("time_bucket") != bucket:
                continue
            if row.get("above_ema_5_10") and row["close"] > prev["high"]:
                out.append((i, "LONG"))
            elif (not row.get("above_ema_5_10")) and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
        return out

    return signals


def multi_timeframe_breakout(min_agree: int) -> SignalFn:
    """Breakout requiring N of the 4 tracked timeframes to agree.

    The spec explicitly says not to require full alignment unless testing
    proves it improves expectancy - so 2, 3 and 4 are all run and the
    answer is read off the results."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            trends = [row.get(k) for k in ("trend_5m", "trend_15m", "trend_60m", "trend_daily")]
            ups = sum(1 for t in trends if t == "UP")
            downs = sum(1 for t in trends if t == "DOWN")
            if ups >= min_agree and row["close"] > prev["high"]:
                out.append((i, "LONG"))
            elif downs >= min_agree and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
        return out

    return signals


# --------------------------------------------------------------------------
# 21 / 22 - gap continuation and gap fade
# --------------------------------------------------------------------------

def gap_continuation(min_gap_pct: float) -> SignalFn:
    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            gap = row.get("gap_pct")
            if not _tradeable(row) or gap is None or abs(gap) < min_gap_pct:
                continue
            if gap > 0 and row.get("above_vwap") and row["close"] > prev["high"]:
                out.append((i, "LONG"))
            elif gap < 0 and (not row.get("above_vwap")) and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
        return out
    return signals


def gap_fade(min_gap_pct: float) -> SignalFn:
    """Trade back toward the prior close."""
    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            gap = row.get("gap_pct")
            if not _tradeable(row) or gap is None or abs(gap) < min_gap_pct:
                continue
            if gap > 0 and (not row.get("above_vwap")) and row["close"] < prev["low"]:
                out.append((i, "SHORT"))
            elif gap < 0 and row.get("above_vwap") and row["close"] > prev["high"]:
                out.append((i, "LONG"))
        return out
    return signals


# --------------------------------------------------------------------------
# Quantified playbooks (the two directional ones)
# --------------------------------------------------------------------------

def playbook_opening_gap_fade() -> SignalFn:
    """Playbook 1, with the spec's exact stated thresholds.

    Gap >= 0.40%, entry window strictly 09:45-10:00, Volume_ZScore_20 >
    1.5, momentum flipped against the gap, and the bar closing at the
    extreme of its own range."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for row_index, row in enumerate(rows):
            minute = row.get("minutes_since_open")
            if minute is None or not (15 <= minute <= 30):     # 09:45-10:00
                continue
            gap = row.get("gap_pct")
            if gap is None or abs(gap) < 0.40:
                continue
            if (row.get("volume_zscore_20") or 0) <= 1.5:
                continue
            momentum = row.get("momentum_score")
            position = row.get("range_position")
            if momentum is None or position is None:
                continue
            if gap >= 0.40 and momentum < -20 and position < 0.20:
                out.append((row_index, "SHORT"))
            elif gap <= -0.40 and momentum > 20 and position > 0.80:
                out.append((row_index, "LONG"))
        return out

    return signals


def playbook_momentum_squeeze(min_efficiency: float = 0.75) -> SignalFn:
    """Playbook 2: ADX > 25, price cleanly through EMA 5 and 10, EMA-9
    slope accelerating, efficiency ratio >= 0.75, volume expanding."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            if (row.get("adx_14") or 0) <= 25:
                continue
            if (row.get("efficiency_ratio") or 0) < min_efficiency:
                continue
            if (row.get("volume_zscore_20") or 0) <= 0:
                continue
            slope, prev_slope = row.get("ema_9_slope"), prev.get("ema_9_slope")
            if slope is None or prev_slope is None:
                continue
            crossed_up = row.get("above_ema_5_10") and not prev.get("above_ema_5_10")
            crossed_down = (not row.get("above_ema_5_10")) and prev.get("above_ema_5_10")
            if crossed_up and slope > 0 and slope > prev_slope:
                out.append((i, "LONG"))
            elif crossed_down and slope < 0 and slope < prev_slope:
                out.append((i, "SHORT"))
        return out

    return signals


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

# Named here so the report can state plainly what was not tested and why,
# rather than leaving a silent gap in a list of 22.
UNTESTABLE: dict[str, str] = {
    "S20 Relative-Strength Breakout":
        "needs intraday QQQ/IWM/DIA and breadth to confirm against; the archive is "
        "SPY-only, so there is nothing to compare SPY with",
    "PB3 Mid-Day Theta Burn":
        "an iron condor - all of its P/L is option premium decay, with no underlying "
        "entry to measure. Belongs to Phase 5",
}

CAVEATS: dict[str, str] = {
    "S5 Premarket breakout":
        "only 226 of 3,347 sessions carry premarket bars (6.8%), nearly all in 2020 - "
        "not comparable to the other samples",
    "S17 Expected-move breakout":
        "expected move is derived from daily ATR, not a 0DTE implied move; no intraday "
        "IV exists in this archive",
}


def build_extended_variants() -> dict[str, dict[str, SignalFn]]:
    return {
        "S5 Premarket breakout": {
            "retest": premarket_breakout(retest=True),
            "immediate": premarket_breakout(retest=False),
        },
        "S6 Prev-day breakout": {
            "retest": prev_day_breakout(retest=True),
            "immediate": prev_day_breakout(retest=False),
        },
        "S7 Failed breakout": {"prev-day levels": failed_breakout_reversal("prev_day")},
        "S8 Liquidity sweep": {f"reclaim<={n}bars": liquidity_sweep(n) for n in (3, 5, 10)},
        "S9 Range reversal": {
            "range-filtered": range_extreme_reversal(require_range_regime=True),
            "unfiltered": range_extreme_reversal(require_range_regime=False),
        },
        "S11 Compression break": {f"{n}bars quiet": compression_breakout(n) for n in (3, 5, 10)},
        "S12 First pullback": {f"{d}atr drive": first_pullback_after_drive(d) for d in (0.5, 0.75, 1.0)},
        "S13 Structure reversal": {
            "no vwap filter": structure_reversal(require_vwap=False),
            "vwap confirmed": structure_reversal(require_vwap=True),
        },
        "S14 Momentum continuation": {
            "adx20 aligned": momentum_continuation(20.0, require_alignment=True),
            "adx25 aligned": momentum_continuation(25.0, require_alignment=True),
            "adx25 unaligned": momentum_continuation(25.0, require_alignment=False),
            "adx30 aligned": momentum_continuation(30.0, require_alignment=True),
        },
        "S15 Momentum exhaustion": {f"{e}atr ext": momentum_exhaustion(e) for e in (1.0, 1.5, 2.0)},
        "S16 Confluence": {f"{n}+ levels": multi_level_confluence(n) for n in (2, 3, 4)},
        "S17 Expected-move": {f"<{c:.0f}% used": expected_move_breakout(c) for c in (50.0, 75.0, 100.0, 125.0)},
        "S18 Time-of-day": {
            bucket: time_of_day_momentum(bucket)
            for bucket in ("OPEN", "MORNING", "MIDMORNING", "MIDDAY", "AFTERNOON", "FINAL_30")
        },
        "S19 MTF breakout": {f"{n}/4 agree": multi_timeframe_breakout(n) for n in (2, 3, 4)},
        "S21 Gap continuation": {f"gap>={g}%": gap_continuation(g) for g in (0.25, 0.50, 1.0)},
        "S22 Gap fade": {f"gap>={g}%": gap_fade(g) for g in (0.25, 0.50, 1.0)},
        "PB1 Opening gap fade": {"spec thresholds": playbook_opening_gap_fade()},
        "PB2 Momentum squeeze": {
            f"eff>={e}": playbook_momentum_squeeze(e) for e in (0.65, 0.75, 0.85)
        },
    }
