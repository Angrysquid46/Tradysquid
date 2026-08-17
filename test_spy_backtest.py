"""Tests for the Phase 3 backtest engine.

Backtests fail silently. A lookahead leak or an optimistic intrabar
assumption does not raise - it just produces a better number, which is
the most dangerous kind of bug in this repo because the output looks like
evidence. So these tests target the specific ways a backtest lies:

- filling at the signal bar's close instead of the next bar's open
- resolving a stop-and-target bar in the trade's favour
- letting a signal function read bars that had not printed yet
- carrying a 0DTE position past the close

Each one is checked against a hand-constructed scenario with a known
correct answer, not against the engine's own output.
"""

from __future__ import annotations

import pytest

import spy_backtest as bt
import spy_backtest_strategies as strat


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _row(minute: int, o: float, h: float, l: float, c: float, **extra):
    hh, mm = divmod(9 * 60 + 30 + minute, 60)
    row = {
        "ticker": "SPY",
        "bar_time": f"2020-06-15T{hh:02d}:{mm:02d}:00",
        "session_date": "2020-06-15",
        "minutes_since_open": minute,
        "time_bucket": "OPENING",
        "open": o, "high": h, "low": l, "close": c, "volume": 1000.0,
        "atr_14": 1.0, "vwap": 100.0, "vwap_slope": 0.0, "above_vwap": 1,
        "vwap_crosses": 0, "vwap_distance_atr": 0.0, "relative_volume": 1.5,
        "regime": "RANGE", "day_type": "NORMAL_DAY", "alignment": "BULLISH",
        "gap_pct": 0.0,
    }
    row.update(extra)
    return row


def _flat(count: int, price: float = 100.0, start: int = 0):
    return [_row(start + i, price, price, price, price) for i in range(count)]


# ---------------------------------------------------------------------------
# Fill timing
# ---------------------------------------------------------------------------

def test_entry_fills_at_the_next_bar_open_not_the_signal_bar_close():
    """You cannot trade a close you are watching form. Filling at the
    signal bar's close is worth a free tick on every trade, which across
    thousands of trades is entirely fake profit."""
    rows = _flat(10)
    rows[3] = _row(3, 100.0, 100.0, 100.0, 100.0)
    rows[4] = _row(4, 105.0, 105.0, 105.0, 105.0)     # gap up after the signal

    trades = bt.simulate(rows, [(3, "LONG")], bt.ExitPolicy(target_atr=None, stop_atr=None,
                                                            time_stop_minutes=2),
                         strategy="t", variant="v")
    assert len(trades) == 1
    assert trades[0].entry_price == 105.0, "filled at the signal bar's close, not the next open"
    assert trades[0].entry_time == rows[4]["bar_time"]


def test_a_signal_on_the_final_bar_produces_no_trade():
    """There is no next bar to fill against, so the trade cannot exist."""
    rows = _flat(5)
    trades = bt.simulate(rows, [(4, "LONG")], bt.ExitPolicy(), strategy="t", variant="v")
    assert trades == []


# ---------------------------------------------------------------------------
# Intrabar resolution - the big one
# ---------------------------------------------------------------------------

def test_a_bar_containing_both_stop_and_target_resolves_as_the_stop():
    """One-minute OHLC cannot say which was touched first. Assuming the
    target is the single most common way a backtest invents edge, so the
    engine must always take the loss."""
    rows = _flat(6)
    rows[2] = _row(2, 100.0, 100.0, 100.0, 100.0)
    rows[3] = _row(3, 100.0, 100.0, 100.0, 100.0)          # entry bar
    rows[4] = _row(4, 100.0, 102.0, 98.0, 100.0)           # spans both levels

    trades = bt.simulate(rows, [(2, "LONG")],
                         bt.ExitPolicy(target_atr=1.0, stop_atr=1.0, time_stop_minutes=None),
                         strategy="t", variant="v")
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop_and_target_same_bar"
    assert trades[0].pnl_atr == pytest.approx(-1.0)


def test_the_ambiguous_case_is_reported_distinctly_from_a_clean_stop():
    """These are not the same event and must stay countable separately -
    a strategy whose results depend heavily on ambiguous bars is one
    whose results depend on an assumption, and that has to be visible."""
    rows = _flat(6)
    rows[3] = _row(3, 100.0, 100.0, 100.0, 100.0)
    rows[4] = _row(4, 100.0, 100.5, 98.0, 99.0)            # stop only, target untouched

    trades = bt.simulate(rows, [(2, "LONG")],
                         bt.ExitPolicy(target_atr=1.0, stop_atr=1.0, time_stop_minutes=None),
                         strategy="t", variant="v")
    assert trades[0].exit_reason == "stop"


def test_short_side_stop_and_target_resolve_with_the_same_pessimism():
    rows = _flat(6)
    rows[4] = _row(4, 100.0, 102.0, 98.0, 100.0)
    trades = bt.simulate(rows, [(2, "SHORT")],
                         bt.ExitPolicy(target_atr=1.0, stop_atr=1.0, time_stop_minutes=None),
                         strategy="t", variant="v")
    assert trades[0].exit_reason == "stop_and_target_same_bar"
    assert trades[0].pnl_atr == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Exits
# ---------------------------------------------------------------------------

def test_a_clean_target_is_taken_at_the_target_price_not_the_bar_extreme():
    """Filling at the bar's high would credit the trade with more than
    the order would actually have got."""
    rows = _flat(6)
    rows[4] = _row(4, 100.0, 103.0, 99.8, 102.5)
    trades = bt.simulate(rows, [(2, "LONG")],
                         bt.ExitPolicy(target_atr=1.0, stop_atr=1.0, time_stop_minutes=None),
                         strategy="t", variant="v")
    assert trades[0].exit_reason == "target"
    assert trades[0].exit_price == pytest.approx(101.0)
    assert trades[0].pnl_atr == pytest.approx(1.0)


def test_time_stop_closes_the_trade_at_the_close_of_the_limiting_bar():
    rows = _flat(10)
    trades = bt.simulate(rows, [(1, "LONG")],
                         bt.ExitPolicy(target_atr=None, stop_atr=None, time_stop_minutes=3),
                         strategy="t", variant="v")
    assert trades[0].exit_reason == "time_stop"
    assert trades[0].bars_held == 3


def test_a_position_is_forced_flat_at_the_session_close():
    """These are 0DTE ideas. Holding past the close is not a real option,
    and a backtest that allows it is measuring a different instrument."""
    rows = [_row(m, 100.0, 100.0, 100.0, 100.0) for m in range(385, 390)]
    trades = bt.simulate(rows, [(0, "LONG")],
                         bt.ExitPolicy(target_atr=99.0, stop_atr=99.0, time_stop_minutes=None),
                         strategy="t", variant="v")
    assert trades[0].exit_reason == "session_close"
    assert trades[0].exit_time.endswith("15:59:00")


def test_breakeven_trail_arms_only_after_the_trade_has_run_far_enough():
    rows = _flat(8)
    rows[3] = _row(3, 100.0, 101.0, 100.0, 101.0)          # runs 1 ATR in favour
    rows[4] = _row(4, 101.0, 101.0, 99.5, 99.5)            # comes back through entry

    trades = bt.simulate(rows, [(1, "LONG")],
                         bt.ExitPolicy(target_atr=5.0, stop_atr=2.0, time_stop_minutes=None,
                                       breakeven_after_atr=1.0),
                         strategy="t", variant="v")
    assert trades[0].exit_price == pytest.approx(100.0), "breakeven stop did not arm"
    assert trades[0].pnl_atr == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Position management
# ---------------------------------------------------------------------------

def test_only_one_position_is_open_at_a_time():
    """Matches how the live system trades - one position per strategy.
    Stacking entries would report an exposure that was never taken."""
    rows = _flat(20)
    signals = [(i, "LONG") for i in range(0, 15)]
    trades = bt.simulate(rows, signals,
                         bt.ExitPolicy(target_atr=None, stop_atr=None, time_stop_minutes=5),
                         strategy="t", variant="v")
    for earlier, later in zip(trades, trades[1:]):
        assert later.entry_time > earlier.exit_time, "positions overlapped"


def test_mfe_and_mae_capture_the_full_excursion_of_the_trade():
    rows = _flat(8)
    rows[3] = _row(3, 100.0, 100.0, 97.0, 100.0)           # 3 ATR against
    rows[4] = _row(4, 100.0, 104.0, 100.0, 104.0)          # 4 ATR in favour
    trades = bt.simulate(rows, [(1, "LONG")],
                         bt.ExitPolicy(target_atr=None, stop_atr=None, time_stop_minutes=6),
                         strategy="t", variant="v")
    assert trades[0].mae_atr == pytest.approx(3.0)
    assert trades[0].mfe_atr == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Strategy signals may not read the future
# ---------------------------------------------------------------------------

def _orb_scene():
    """Break above the 15-min range, pull back to it, hold, confirm."""
    rows = _flat(40)
    for minute, row in enumerate(rows):
        row.update(or15_high=100.5, or15_low=99.0, or15_mid=99.75, or15_width=1.5,
                   or15_state="BROKEN_UP" if minute >= 15 else "FORMING",
                   or15_break_minute=20 if minute >= 15 else None,
                   vwap_slope=0.01, above_vwap=1, vwap=100.0)
    rows[20].update(open=100.5, high=101.0, low=100.4, close=100.9)      # the breakout bar
    rows[24].update(open=100.8, high=100.7, low=100.4, close=100.6)      # retest low
    rows[25].update(open=100.6, high=101.2, low=100.45, close=101.1)     # holds + confirms
    return rows


def _pullback_scene():
    """Uptrend above a rising VWAP, dip into the 0.25-ATR zone, reverse."""
    rows = _flat(40)
    for row in rows:
        row.update(vwap=100.0, vwap_slope=0.02, above_vwap=1, alignment="BULLISH")
    rows[17].update(open=100.5, high=100.6, low=100.2, close=100.3)
    rows[18].update(open=100.3, high=100.9, low=100.1, close=100.8)      # into zone, reverses
    return rows


def _reclaim_scene():
    """Lose VWAP, reclaim it, hold the retest, break the pullback high."""
    rows = _flat(40)
    for row in rows:
        row.update(vwap=100.0, vwap_crosses=1, alignment="BULLISH")
    rows[9].update(open=99.5, high=99.7, low=99.3, close=99.6)           # below VWAP
    rows[10].update(open=99.6, high=100.4, low=99.6, close=100.3)        # reclaim
    rows[11].update(open=100.3, high=100.35, low=100.05, close=100.2)    # holds
    rows[12].update(open=100.2, high=100.8, low=100.15, close=100.7)     # breaks pullback high
    return rows


def _reversion_scene():
    """Range regime, price extended a full ATR below a flat VWAP, turning up."""
    rows = _flat(40)
    for row in rows:
        row.update(vwap=100.0, regime="RANGE", above_vwap=0)
    rows[14].update(open=98.9, high=99.0, low=98.8, close=98.9, vwap_distance_atr=-1.4)
    rows[15].update(open=98.9, high=99.3, low=98.85, close=99.2, vwap_distance_atr=-1.2)
    return rows


@pytest.mark.parametrize("name,fn,scene", [
    ("orb_retest_15", strat.orb_retest(15), _orb_scene),
    ("orb_immediate_15", strat.orb_immediate(15), _orb_scene),
    ("vwap_pullback_025", strat.vwap_pullback(0.25), _pullback_scene),
    ("vwap_reclaim_3", strat.vwap_reclaim(3), _reclaim_scene),
    ("vwap_reversion_1", strat.vwap_extreme_reversion(1.0), _reversion_scene),
])
def test_signals_do_not_depend_on_bars_that_had_not_printed_yet(name, fn, scene):
    """Truncation test, same principle as Phase 2: a signal at bar i must
    still be a signal when every bar after i is removed, because live
    that is all that exists.

    Each strategy gets a scenario built to actually trigger it - a
    fixture that produces no signals would make this test pass while
    checking nothing, so that case is asserted against explicitly."""
    rows = scene()
    full = fn(rows)
    assert full, f"{name} produced no signals on its scene - the test would be vacuous"

    for index, direction in full:
        truncated = fn(rows[: index + 1])
        assert (index, direction) in truncated, (
            f"{name}: signal at bar {index} disappears when later bars are removed - "
            f"it is reading the future"
        )


def test_no_strategy_signals_outside_its_permitted_entry_window():
    """Entering at 15:55 on a 0DTE and holding to the close is not the
    strategy being described; the window keeps results honest."""
    rows = [_row(m, 100.0, 101.0, 99.0, 100.5, or15_state="BROKEN_UP",
                 or15_high=100.0, or15_break_minute=m, vwap_distance_atr=3.0,
                 relative_volume=5.0) for m in range(390)]
    for family in strat.build_variants().values():
        for fn in family.values():
            for index, _ in fn(rows):
                minute = rows[index]["minutes_since_open"]
                assert strat.MIN_MINUTE <= minute <= strat.LAST_ENTRY_MINUTE


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def test_expectancy_and_profit_factor_match_hand_computed_values():
    trades = [
        bt.Trade("s", "v", "LONG", "2020-06-15", "t", 100.0, 10, "OPENING", "t", 102.0,
                 "target", 5, 1.0, 2.0, 2.0, 2.0, 2.0, 0.0, "RANGE", "NORMAL_DAY",
                 "BULLISH", 0.0, "e"),
        bt.Trade("s", "v", "LONG", "2020-06-16", "t", 100.0, 10, "OPENING", "t", 99.0,
                 "stop", 5, 1.0, -1.0, -1.0, -1.0, 0.0, 1.0, "RANGE", "NORMAL_DAY",
                 "BULLISH", 0.0, "e"),
    ]
    stats = bt.summarize(trades)
    assert stats["trades"] == 2
    assert stats["win_rate"] == pytest.approx(50.0)
    assert stats["expectancy_atr"] == pytest.approx(0.5)
    assert stats["profit_factor"] == pytest.approx(2.0)


def test_a_tiny_edge_over_few_trades_is_reported_as_not_significant():
    """The guard against the central failure mode of this whole phase:
    a +0.02 ATR expectancy on a few hundred noisy trades is a coin flip,
    and must not be presentable as a finding."""
    import random
    rng = random.Random(7)
    trades = [_pnl_trade(rng.choice((1.0, -1.0)) + 0.02) for _ in range(400)]
    stats = bt.summarize(trades)
    assert abs(stats["expectancy_atr"]) < 0.15
    assert stats["significant_95"] is False
    assert abs(stats["t_stat"]) < 1.96


def test_a_genuine_edge_over_many_trades_is_reported_as_significant():
    """The other direction - the test must be able to say yes, or it is
    just a rubber stamp that always says no."""
    trades = [_pnl_trade(0.5) for _ in range(500)] + [_pnl_trade(-0.4) for _ in range(400)]
    stats = bt.summarize(trades)
    assert stats["expectancy_atr"] > 0
    assert stats["significant_95"] is True


def _pnl_trade(pnl: float) -> bt.Trade:
    return bt.Trade("s", "v", "LONG", "2020-06-15", "t", 100.0, 10, "OPENING", "t",
                    100.0 + pnl, "target", 5, 1.0, pnl, pnl, pnl,
                    max(pnl, 0.0), max(-pnl, 0.0), "RANGE", "NORMAL_DAY", "BULLISH", 0.0, "e")


def test_max_drawdown_is_measured_from_the_running_peak():
    assert bt._max_drawdown([1.0, 1.0, -3.0, 0.5]) == pytest.approx(-3.0)
    assert bt._max_drawdown([1.0, 2.0, 3.0]) == pytest.approx(0.0)


def test_summarize_reports_nothing_rather_than_dividing_by_zero():
    assert bt.summarize([])["trades"] == 0


def test_eras_partition_the_history_without_gaps_or_overlap():
    assert bt.era_for("2008-01-22").startswith("2008")
    assert bt.era_for("2015-12-31").startswith("2012")
    assert bt.era_for("2021-05-06").startswith("2020")
    covered = [bt.era_for(f"{y}-06-15") for y in range(2008, 2022)]
    assert "unclassified" not in covered


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def test_random_baseline_is_reproducible_for_a_given_session():
    rows = _flat(100)
    assert strat.random_baseline(3)(rows) == strat.random_baseline(3)(rows)


def test_random_baseline_takes_both_directions_across_sessions():
    """A one-sided baseline would inherit SPY's drift and stop being a
    control."""
    directions = set()
    for day in range(1, 40):
        rows = _flat(100)
        for row in rows:
            row["session_date"] = f"2020-06-{day:02d}"
        directions.update(d for _, d in strat.random_baseline(3)(rows))
    assert directions == {"LONG", "SHORT"}
