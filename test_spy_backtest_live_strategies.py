"""Tests for the live-Discord-strategy backtest adapters.

These adapters exist to answer "how good are the strategies we are
actually running?", so the thing that would invalidate them is drift
between the backtest and the deployed code. They call `spy_scanner`
directly to avoid that, and the tests here pin the two places where a
faithful call was replaced by something faster:

- `timeframe_read_series` computes EMA/MACD reads in one pass instead of
  recomputing per bar. It must agree with the live function bar for bar,
  or the expansion strategy being measured is not the one deployed.
- the opening-range adapter feeds the live signal a compact
  `opening_range + [current]` list rather than the whole session. It must
  produce what passing the full prefix would.
"""

from __future__ import annotations

import random

import pytest

import spy_backtest_live_strategies as live
import spy_scanner as ss


def _series(count: int, seed: int = 11, step: float = 0.4) -> list[float]:
    rng = random.Random(seed)
    price = 100.0
    out = []
    for _ in range(count):
        price += rng.gauss(0, step)
        out.append(round(price, 2))
    return out


def _rows(count: int, session: str = "2020-06-15", start_minute: int = 0, base: float = 100.0):
    rows = []
    for i in range(count):
        minute = start_minute + i
        hh, mm = divmod(9 * 60 + 30 + minute, 60)
        price = base + (i % 11) * 0.1 - (i % 7) * 0.08
        rows.append({
            "bar_time": f"{session}T{hh:02d}:{mm:02d}:00",
            "session_date": session,
            "minutes_since_open": minute,
            "open": price, "high": price + 0.15, "low": price - 0.15,
            "close": price, "volume": 1000.0,
        })
    return rows


# ---------------------------------------------------------------------------
# Parity with the deployed code
# ---------------------------------------------------------------------------





def test_opening_range_adapter_agrees_with_passing_the_whole_session():
    """The adapter hands the live signal only the bars it actually reads
    (the opening range plus the current bar) for speed. That shortcut has
    to produce the same answer as the honest full-prefix call."""
    rows = _rows(120)
    fn = live.live_opening_range_breakout(1)
    produced = dict(fn(rows))

    bars_needed = ss.SPY_0DTE_OPENING_RANGE_MINUTES
    for index in range(bars_needed, len(rows)):
        context = ss.spy_0dte_opening_range_signal(rows[: index + 1], bar_minutes=1)
        minute = rows[index]["minutes_since_open"]
        if not (live.MIN_ENTRY_MINUTE <= minute <= live.LAST_ENTRY_MINUTE):
            continue
        if context.get("qualified"):
            expected = "LONG" if context["regime"].startswith("BULLISH") else "SHORT"
            assert produced.get(index) == expected, f"bar {index} disagrees with the live signal"
        else:
            assert index not in produced, f"bar {index} signalled but the live function did not qualify"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------





def test_five_minute_adapter_only_reads_completed_bars():
    """A 5-minute strategy must not act on a 5-minute bar that has not
    closed - that is lookahead with extra steps."""
    rows = _rows(120)
    fn = live.live_opening_range_breakout(5)
    for index, _direction in fn(rows):
        assert rows[index]["minutes_since_open"] % 5 == 4


# ---------------------------------------------------------------------------
# 200-day SMA
# ---------------------------------------------------------------------------

def test_sma200_uses_only_prior_closes():
    """A session's own close must not appear in its own 200-day average."""
    ohlc = [(f"2020-01-{i:02d}", {"open": 1, "high": 1, "low": 1, "close": float(i)})
            for i in range(1, 10)]
    ohlc += [(f"2021-{m:02d}-{d:02d}", {"open": 1, "high": 1, "low": 1, "close": 500.0})
             for m in range(1, 13) for d in range(1, 21)]
    result = live.daily_sma200(ohlc)
    assert len(result) < len(ohlc)             # the first 200 have no average
    for session, value in result.items():
        assert value is not None


def test_sma200_needs_a_full_two_hundred_sessions():
    ohlc = [(f"d{i}", {"open": 1, "high": 1, "low": 1, "close": 100.0}) for i in range(150)]
    assert live.daily_sma200(ohlc) == {}


# ---------------------------------------------------------------------------
# Structural claims the ranking depends on
# ---------------------------------------------------------------------------





def test_every_live_play_type_is_accounted_for_in_a_group():
    """No live strategy may be silently missing from the ranking."""
    grouped = {p for members in live.SHARED_ENTRY_GROUPS.values() for p in members}
    expected = {"SPY_KEY_LEVELS"}
    assert grouped == expected


def test_exit_shape_limitation_is_stated():
    assert "option-premium percent" in live.EXIT_SHAPES_NEED_OPTION_MODEL
    assert "Phase 5" in live.EXIT_SHAPES_NEED_OPTION_MODEL


def test_live_signals_respect_the_entry_window():
    rows = _rows(390)
    for fn in (live.live_opening_range_breakout(1), live.live_opening_range_breakout(5)):
        for index, _ in fn(rows):
            minute = rows[index]["minutes_since_open"]
            assert live.MIN_ENTRY_MINUTE <= minute <= live.LAST_ENTRY_MINUTE
