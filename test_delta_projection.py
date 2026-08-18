"""Spend the REST budget where a decision is close, not on a fixed clock.

Tradier production allows 120 req/min (2/sec) across ALL REST. Refetches
are batched to one call per staleness window, so a flat 0.5s bound has a
ceiling of exactly 2/sec - the entire budget on its own, leaving nothing
for the entry scan or anything else. Tightening to 0.25s would be 240/min,
double the limit, and exceeding it returns 429s precisely when the market
is moving fast enough to need a fresh quote.

So between ticks the option's move is projected from SPY's using delta.
The projection ONLY decides when to look. An exit is never taken on a
projected price - the real quote is fetched and re-evaluated first.

The property that must hold: freshness near a threshold is unchanged.
Anything else is a regression dressed up as an optimisation.
"""

from __future__ import annotations

import local_information_engine as engine


def _row(play="SPY_GAP_CONT_50", entry="1.00", delta="0.50"):
    return {"play_type": play, "entry_price": entry, "delta": delta,
            "option_symbol": "OPT", "ticker": "SPY", "outcome": "OPEN"}


def _seed(symbol="OPT", bid=1.0, delta=0.5, spot=770.0):
    engine.STREAM_QUOTES[symbol] = {"bid": bid, "ask": bid + 0.02,
                                    "greeks": {"delta": delta}}
    engine.STREAM_QUOTE_SPOT_AT[symbol] = spot


def test_a_position_far_from_any_threshold_relaxes_its_refresh():
    """This is where the budget is recovered - a trade sitting mid-range
    does not need a quote every half second."""
    _seed(bid=1.0, delta=0.5, spot=770.0)
    row = _row()                      # target +150%, stop -75%
    projected = engine._projected_pl_pct(row, "OPT", 770.0)
    assert projected is not None
    assert abs(projected) < 25
    assert engine._near_exit_threshold(row, projected) is False


def test_a_position_near_its_TARGET_stays_on_the_tight_bound():
    """+150% target: a projection of +130% is inside the band and must
    keep refreshing at the original cadence."""
    row = _row()
    assert engine._near_exit_threshold(row, 130.0) is True


def test_a_position_near_its_STOP_stays_on_the_tight_bound():
    """-75% stop: -55% is inside the band."""
    row = _row()
    assert engine._near_exit_threshold(row, -55.0) is True


def test_an_unknown_projection_is_treated_as_near():
    """Never skip a refresh because something could not be computed - the
    failure must land on the safe side."""
    row = _row()
    assert engine._near_exit_threshold(row, None) is True


def test_a_strategy_with_no_premium_exit_always_refreshes():
    """SPY_KEY_LEVELS exits on the underlying, so a premium projection
    says nothing about whether it is close to exiting."""
    assert engine._near_exit_threshold(_row(play="SPY_KEY_LEVELS"), 0.0) is True
    assert engine._near_exit_threshold(_row(play="NOT_A_STRATEGY"), 0.0) is True


def test_the_projection_tracks_the_underlying_through_delta():
    """A 1-point SPY move on a 0.50-delta contract is about $0.50 of
    option value - which on a $1.00 entry is about +50%."""
    _seed(bid=1.00, delta=0.50, spot=770.0)
    row = _row(entry="1.00")
    up = engine._projected_pl_pct(row, "OPT", 771.0)
    assert 45 <= up <= 55
    down = engine._projected_pl_pct(row, "OPT", 769.0)
    assert -55 <= down <= -45


def test_the_projection_moves_a_position_into_the_near_band():
    """The mechanism that matters: SPY runs, the projection crosses into
    the band, and the position goes back on the tight bound BEFORE its
    own option has ticked."""
    _seed(bid=1.00, delta=0.50, spot=770.0)
    row = _row(entry="1.00")
    assert engine._near_exit_threshold(row, engine._projected_pl_pct(row, "OPT", 770.0)) is False
    far_move = engine._projected_pl_pct(row, "OPT", 772.6)   # ~+130%
    assert engine._near_exit_threshold(row, far_move) is True


def test_the_near_bound_is_not_looser_than_before():
    """The whole point: nothing gets less fresh where a decision is close."""
    assert engine.STREAM_QUOTE_STALE_SECONDS <= 0.5
    assert engine.STREAM_FAR_STALE_SECONDS > engine.STREAM_QUOTE_STALE_SECONDS


def test_the_far_bound_actually_saves_calls():
    """At 2s the far-position ceiling is 0.5/sec instead of 2/sec, which
    is what frees room under the 120/min limit."""
    near_ceiling = 60.0 / engine.STREAM_QUOTE_STALE_SECONDS
    far_ceiling = 60.0 / engine.STREAM_FAR_STALE_SECONDS
    assert near_ceiling == 120.0
    assert far_ceiling <= 30.0
