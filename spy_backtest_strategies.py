"""Phase 3 strategy signal definitions - the ORB and VWAP families.

Covers the spec's Strategies 1, 2, 3, 4 and 10. Each returns entry
signals only; exits are the backtest engine's job, so one set of entries
can be replayed against many exit policies.

Every strategy exposes the parameter the spec explicitly says to test
rather than assume - the opening-range window (5/15/30), the pullback
zone (A-E), the VWAP chop-cross limit (2-5), the extension threshold
(0.5-2.0 ATR). None of these are guessed here.

A signal at index i may read rows[:i+1] and nothing beyond. The engine
then fills at rows[i+1]'s open. `test_spy_backtest.py` enforces this by
truncation rather than trusting the convention.

RANDOM_BASELINE exists because a win rate means nothing on its own. SPY
drifts up, so a long-only strategy inherits that drift and can look
skilful while contributing nothing. Every result is reported against
entries taken at random qualifying bars, which is the honest comparison -
the same base-rate lesson that corrected the market_memory pattern stats.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Sequence

SignalFn = Callable[[Sequence[dict[str, Any]]], list[tuple[int, str]]]

# The spec's minimum quality gates. Deliberately loose: Phase 3 measures
# how effective each strategy is, and over-filtering up front would hide
# the answer rather than reveal it.
MIN_MINUTE = 5                 # nothing in the first few chaotic minutes
LAST_ENTRY_MINUTE = 360        # 15:30 - leave room for the trade to work


def _tradeable(row: dict[str, Any]) -> bool:
    minute = row.get("minutes_since_open")
    return (
        minute is not None
        and MIN_MINUTE <= minute <= LAST_ENTRY_MINUTE
        and row.get("atr_14")
        and row.get("close") is not None
        and row.get("vwap") is not None
    )


# ---------------------------------------------------------------------------
# Strategy 1 - Opening range breakout, WITH retest
# ---------------------------------------------------------------------------

def orb_retest(window: int, *, require_vwap: bool = True) -> SignalFn:
    """Break out, close outside the range, pull back, hold, confirm.

    The spec is emphatic: "Do NOT automatically buy the first tick above
    the OR." The retest is the whole point of Strategy 1, and comparing
    it against Strategy 2 is how we learn whether waiting pays."""
    high_key, low_key, state_key = f"or{window}_high", f"or{window}_low", f"or{window}_state"

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            state, level_h, level_l = row.get(state_key), row.get(high_key), row.get(low_key)
            if state == "BROKEN_UP" and level_h:
                retested = row["low"] <= level_h                 # came back to the level
                held = row["close"] > level_h                    # and closed back above it
                confirmed = row["close"] > prev["high"]          # break of prior bar high
                aligned = (not require_vwap) or (row.get("above_vwap") and (row.get("vwap_slope") or 0) > 0)
                if retested and held and confirmed and aligned:
                    out.append((i, "LONG"))
            elif state == "BROKEN_DOWN" and level_l:
                retested = row["high"] >= level_l
                held = row["close"] < level_l
                confirmed = row["close"] < prev["low"]
                aligned = (not require_vwap) or (not row.get("above_vwap") and (row.get("vwap_slope") or 0) < 0)
                if retested and held and confirmed and aligned:
                    out.append((i, "SHORT"))
        return out

    return signals


# ---------------------------------------------------------------------------
# Strategy 2 - Opening range breakout, NO retest
# ---------------------------------------------------------------------------

def orb_immediate(window: int, *, min_rvol: float = 1.0) -> SignalFn:
    """Enter on the breakout bar itself.

    Fires exactly once per session per direction - on the bar where the
    range first breaks - so it can be compared like-for-like against the
    patience of Strategy 1."""
    high_key, low_key = f"or{window}_high", f"or{window}_low"
    state_key, break_key = f"or{window}_state", f"or{window}_break_minute"

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i, row in enumerate(rows):
            if not _tradeable(row):
                continue
            if row.get(break_key) != row.get("minutes_since_open"):
                continue                                   # only the breakout bar itself
            if (row.get("relative_volume") or 0) < min_rvol:
                continue
            state = row.get(state_key)
            if state == "BROKEN_UP" and row.get(high_key) and row["close"] > row[high_key]:
                out.append((i, "LONG"))
            elif state == "BROKEN_DOWN" and row.get(low_key) and row["close"] < row[low_key]:
                out.append((i, "SHORT"))
        return out

    return signals


# ---------------------------------------------------------------------------
# Strategy 3 - VWAP trend pullback
# ---------------------------------------------------------------------------

def vwap_pullback(zone_atr: float, *, require_alignment: bool = True) -> SignalFn:
    """Established trend, first high-quality pullback into the zone.

    zone_atr maps to the spec's zones: 0.0 = Zone A (VWAP itself),
    0.25 = Zone B, 0.50 = Zone C."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            vwap, atr = row["vwap"], row["atr_14"]
            slope = row.get("vwap_slope") or 0.0
            alignment = row.get("alignment") or ""

            if row.get("above_vwap") and slope > 0:
                if require_alignment and alignment not in ("BULLISH", "STRONG_BULLISH"):
                    continue
                reached = row["low"] <= vwap + zone_atr * atr      # pulled into the zone
                held = row["close"] > vwap                          # did not lose VWAP
                turned = row["close"] > prev["high"]                # stopped making lower lows
                if reached and held and turned:
                    out.append((i, "LONG"))
            elif (not row.get("above_vwap")) and slope < 0:
                if require_alignment and alignment not in ("BEARISH", "STRONG_BEARISH"):
                    continue
                reached = row["high"] >= vwap - zone_atr * atr
                held = row["close"] < vwap
                turned = row["close"] < prev["low"]
                if reached and held and turned:
                    out.append((i, "SHORT"))
        return out

    return signals


# ---------------------------------------------------------------------------
# Strategy 4 - VWAP reclaim
# ---------------------------------------------------------------------------

def vwap_reclaim(max_crosses: int, *, confirm_within: int = 15) -> SignalFn:
    """Lose VWAP, reclaim it, hold the retest, break the pullback high.

    max_crosses implements the spec's chop filter: once SPY has crossed
    VWAP too many times the day is chop and the strategy stands down."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        pending: tuple[str, int, float] | None = None       # direction, bar, pullback extreme

        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if row.get("vwap") is None or row.get("close") is None:
                continue
            if (row.get("vwap_crosses") or 0) > max_crosses:
                pending = None
                continue

            vwap = row["vwap"]
            reclaimed_up = prev["close"] <= prev["vwap"] and row["close"] > vwap
            reclaimed_down = prev["close"] >= prev["vwap"] and row["close"] < vwap
            if reclaimed_up:
                pending = ("LONG", i, row["high"])
            elif reclaimed_down:
                pending = ("SHORT", i, row["low"])
            elif pending:
                direction, start, extreme = pending
                if i - start > confirm_within:
                    pending = None
                elif direction == "LONG":
                    if row["close"] < vwap:
                        pending = None                       # VWAP failed to hold
                    elif _tradeable(row) and row["close"] > extreme:
                        out.append((i, "LONG"))              # broke the pullback high
                        pending = None
                    else:
                        pending = (direction, start, max(extreme, row["high"]))
                else:
                    if row["close"] > vwap:
                        pending = None
                    elif _tradeable(row) and row["close"] < extreme:
                        out.append((i, "SHORT"))
                        pending = None
                    else:
                        pending = (direction, start, min(extreme, row["low"]))
        return out

    return signals


# ---------------------------------------------------------------------------
# Strategy 10 - VWAP extreme reversion
# ---------------------------------------------------------------------------

RANGE_LIKE_REGIMES = {"RANGE", "COMPRESSION", "UNCERTAIN"}


def vwap_extreme_reversion(threshold_atr: float) -> SignalFn:
    """Counter-trend: price statistically extended from a flat VWAP in a
    range-like regime, with momentum starting to turn back.

    The spec gates this hard - it is explicitly NOT a trend strategy, and
    firing it during an expansion is how mean-reversion systems die."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i in range(1, len(rows)):
            row, prev = rows[i], rows[i - 1]
            if not _tradeable(row):
                continue
            if (row.get("regime") or "") not in RANGE_LIKE_REGIMES:
                continue
            distance = row.get("vwap_distance_atr")
            if distance is None:
                continue

            if distance <= -threshold_atr and row["close"] > prev["close"]:
                out.append((i, "LONG"))                      # extended below, turning up
            elif distance >= threshold_atr and row["close"] < prev["close"]:
                out.append((i, "SHORT"))                     # extended above, turning down
        return out

    return signals


# ---------------------------------------------------------------------------
# Baseline - what "no skill" looks like on the same bars
# ---------------------------------------------------------------------------

def random_baseline(per_session: int = 2, *, seed: int = 20260816) -> SignalFn:
    """Random entries at tradeable bars, both directions equally.

    This is the control. A strategy that cannot beat it is not producing
    edge, however good its win rate looks in isolation - SPY's upward
    drift alone will carry a long-biased rule to a respectable-looking
    number."""

    def signals(rows: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
        candidates = [i for i, row in enumerate(rows) if _tradeable(row)]
        if not candidates:
            return []
        rng = random.Random(f"{seed}:{rows[0]['session_date']}")
        picks = sorted(rng.sample(candidates, min(per_session, len(candidates))))
        return [(i, rng.choice(("LONG", "SHORT"))) for i in picks]

    return signals


# ---------------------------------------------------------------------------
# The registry the sweep runs over
# ---------------------------------------------------------------------------

def build_variants() -> dict[str, dict[str, SignalFn]]:
    """Every strategy/parameter combination the spec asks to test."""
    return {
        "S1 ORB retest": {f"or{w}": orb_retest(w) for w in (5, 15, 30)},
        "S2 ORB immediate": {f"or{w}": orb_immediate(w) for w in (5, 15, 30)},
        "S3 VWAP pullback": {
            "zoneA vwap": vwap_pullback(0.0),
            "zoneB 0.25atr": vwap_pullback(0.25),
            "zoneC 0.50atr": vwap_pullback(0.50),
        },
        "S4 VWAP reclaim": {f"chop<={c}": vwap_reclaim(c) for c in (2, 3, 4, 5)},
        "S10 VWAP reversion": {
            f"{t}atr": vwap_extreme_reversion(t) for t in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
        },
        "BASELINE random": {"2/session": random_baseline(2)},
    }


def build_exit_policies() -> list[Any]:
    """A small, deliberately spanning grid rather than an exhaustive one.

    Wide enough to show whether a strategy wants a tight scalp or room to
    run; small enough that the sweep stays honest about how many
    configurations were tried."""
    from spy_backtest import ExitPolicy
    policies = []
    for target, stop in ((0.5, 0.5), (1.0, 0.75), (1.5, 1.0), (2.0, 1.0)):
        for time_stop in (15, 30, None):
            policies.append(ExitPolicy(target_atr=target, stop_atr=stop, time_stop_minutes=time_stop))
    return policies
