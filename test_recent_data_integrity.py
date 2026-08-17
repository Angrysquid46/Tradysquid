"""The research store must describe the market that exists now.

Three defects sat behind every number this system produced:

1. The intraday store stopped at 2021-05-06, so "recent" data was five
   years old.
2. Ingesting recent bars across that hole corrupted the session context -
   the first session after the gap reported a 76% gap against a 2021
   prior close, and relative_volume came out around 90x because a 2021
   volume profile was still in the baseline.
3. atr_14 was consequently ~3.5x too large, and because several strategy
   thresholds are expressed in ATR multiples, that silently made them
   look unreachable when they were not. Two strategies were nearly
   retuned on the strength of it.

The last one is the reason these are tests and not a one-off check: a
contaminated ATR does not raise, it just quietly rescales every
ATR-relative decision in the system.
"""

from __future__ import annotations

import sqlite3

import pytest

import spy_intraday_features as sif
import spy_live_new_strategies as lns


@pytest.fixture
def conn():
    c = sif.connect()
    yield c
    c.close()


def test_daily_bars_cover_the_intraday_hole(conn):
    """Minute bars cannot exist for 2021-2026 - no provider sells
    1-minute history that far back (Tradier ~20 days, Yahoo caps at 30).
    Daily bars can, and every feature the gap corrupted is derived from
    session-level OHLC."""
    row = conn.execute(
        "SELECT COUNT(*) n FROM daily_bars WHERE ticker='SPY' "
        "AND session_date > '2021-05-06' AND session_date < '2026-07-17'"
    ).fetchone()
    assert row[0] > 1000, "the 2021-2026 context hole is not filled"


def test_session_ohlc_falls_back_to_daily_where_minute_bars_are_missing(conn):
    sessions = dict(sif.all_session_ohlc(conn, "SPY"))
    # A session inside the hole - present only via daily_bars.
    assert "2023-06-15" in sessions
    entry = sessions["2023-06-15"]
    assert entry["high"] >= entry["low"]
    assert entry["open"] and entry["close"]


def test_minute_derived_ohlc_wins_over_daily(conn):
    """Daily only fills sessions that would otherwise be absent. If it
    overwrote real intraday aggregates, every historical feature would
    shift."""
    merged = dict(sif.all_session_ohlc(conn, "SPY"))
    row = conn.execute(
        """SELECT MIN(open) o, MAX(high) h, MIN(low) l FROM (
             SELECT open, high, low FROM minute_bars
             WHERE ticker='SPY' AND regular_session=1
               AND bar_time >= '2020-06-15T' AND bar_time < '2020-06-15U')"""
    ).fetchone()
    if row and row["h"] is not None:
        assert merged["2020-06-15"]["high"] == pytest.approx(row["h"])
        assert merged["2020-06-15"]["low"] == pytest.approx(row["l"])


def test_no_recent_session_reports_an_absurd_gap(conn):
    """The symptom that exposed all of this: gap_pct of 76% against a
    five-year-old prior close."""
    rows = conn.execute(
        "SELECT session_date, MIN(gap_pct) g FROM minute_features "
        "WHERE ticker='SPY' AND session_date >= '2026-01-01' "
        "GROUP BY session_date"
    ).fetchall()
    assert rows, "no recent sessions ingested"
    for row in rows:
        assert abs(row["g"] or 0) < 10, f"{row['session_date']} gap {row['g']}"


def test_recent_atr_matches_a_770_dollar_spy(conn):
    """atr_14 read 27-32 while contaminated and ~8 once fixed. Because
    strategy thresholds are ATR multiples, the wrong value rescales every
    one of them - silently."""
    row = conn.execute(
        "SELECT AVG(atr_14) a FROM minute_features "
        "WHERE ticker='SPY' AND session_date >= '2026-08-01'"
    ).fetchone()
    assert 3.0 < row["a"] < 20.0, f"atr_14 averages {row['a']}, wrong scale"


def test_the_volume_baseline_does_not_survive_a_coverage_break(conn):
    """A volume profile from before a break in intraday coverage is not a
    baseline. Without the reset, relative_volume came out around 90x."""
    rows = conn.execute(
        "SELECT session_date, AVG(relative_volume) v FROM minute_features "
        "WHERE ticker='SPY' AND session_date >= '2026-07-23' "
        "GROUP BY session_date"
    ).fetchall()
    assert rows
    for row in rows:
        assert 0.2 < (row["v"] or 0) < 5.0, (
            f"{row['session_date']} relative_volume {row['v']}"
        )


def test_every_strategy_fires_on_current_data(conn):
    """The whole point. A strategy that cannot trigger in the current
    regime is a dead Discord channel, and three of them were - each with
    a threshold sitting above the observed maximum."""
    import spy_backtest as bt

    sessions = list(bt.load_sessions(conn, since="2026-07-21"))
    assert len(sessions) >= 10, "not enough clean recent sessions to judge"

    dead = []
    for spec in lns.NEW_STRATEGY_SPECS:
        fired = sum(len(spec["signal"](rows)) for _s, rows in sessions)
        if fired == 0:
            dead.append(spec["play_type"])
    assert not dead, f"these cannot fire on current data: {dead}"
