"""Tests for the Phase 4 strategy library and its Tier-2 features.

Same discipline as Phase 3: every strategy gets a scene built to trigger
it, a truncation check proving it cannot read the future, and a guard
against the fixture producing nothing (which would make the test pass
while checking nothing).

The indicator tests matter separately. Playbook 2 gates entirely on
`ADX > 25` and `efficiency_ratio >= 0.75`, so if those are computed
differently from the standard definitions the strategy being measured is
not the strategy that was specified.
"""

from __future__ import annotations

import pytest

import spy_backtest_strategies_extended as ext
import spy_intraday_features as sif
from test_spy_backtest import _flat, _row


# ---------------------------------------------------------------------------
# Tier-2 indicators
# ---------------------------------------------------------------------------

def test_ema_matches_the_standard_recursive_definition():
    ema = sif._Ema(10)
    multiplier = 2 / 11
    expected = 100.0
    assert ema.update(100.0) == pytest.approx(100.0)      # seeds on first value
    for price in (101.0, 102.0, 99.0):
        expected = (price - expected) * multiplier + expected
        assert ema.update(price) == pytest.approx(expected)


def test_efficiency_ratio_is_one_for_a_straight_line_and_low_for_chop():
    assert sif._efficiency_ratio([100, 101, 102, 103]) == pytest.approx(1.0)
    chop = sif._efficiency_ratio([100, 101, 100, 101, 100])
    assert chop == pytest.approx(0.0)
    assert sif._efficiency_ratio([100]) is None


def test_adx_rises_in_a_clean_trend_and_stays_low_in_chop():
    """Playbook 2 turns itself off below ADX 25, so the indicator has to
    actually separate trend from chop or the filter is decoration."""
    trending = sif._Adx(14)
    adx = None
    for i in range(60):
        price = 100 + i * 0.5
        adx, _, _ = trending.update(price + 0.2, price - 0.2, price)
    assert adx is not None and adx > 25

    choppy = sif._Adx(14)
    adx_chop = None
    for i in range(60):
        price = 100 + (1.0 if i % 2 else 0.0)
        adx_chop, _, _ = choppy.update(price + 0.2, price - 0.2, price)
    assert adx_chop is not None and adx_chop < 25


def test_adx_returns_nothing_until_it_has_a_full_period():
    calc = sif._Adx(14)
    for i in range(10):
        assert calc.update(100 + i, 99 + i, 100 + i)[0] is None


def test_swing_points_only_confirm_after_enough_bars_have_printed():
    """A swing high is not knowable at the bar that forms it - it needs
    bars on the right to confirm. Reporting it early would be lookahead
    dressed as structure."""
    highs = [1, 2, 5, 2, 1, 2, 3]
    lows = [1, 0, 1, 1, 0, 1, 2]
    swing_high, _ = sif._swing_points(highs, lows, 2)
    assert swing_high == 5

    # With only the bars up to the peak, it cannot yet be confirmed.
    assert sif._swing_points(highs[:3], lows[:3], 2)[0] is None


def test_structure_labels_match_the_price_pattern():
    rising_h = [1, 2, 3, 4, 5, 6]
    rising_l = [0, 1, 2, 3, 4, 5]
    assert sif._structure([1] * 6, rising_h, rising_l) == "UPTREND"
    assert sif._structure([1] * 6, rising_h[::-1], rising_l[::-1]) == "DOWNTREND"
    assert sif._structure([1] * 3, [1, 2, 3], [0, 1, 2]) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def _level_scene(high_key="prev_day_high", low_key="prev_day_low"):
    rows = _flat(40)
    for row in rows:
        row.update({high_key: 100.5, low_key: 99.5})
    rows[20].update(open=100.4, high=100.9, low=100.3, close=100.8)     # break up
    rows[24].update(open=100.8, high=100.85, low=100.4, close=100.45)   # retest
    rows[25].update(open=100.45, high=101.0, low=100.45, close=100.95)  # hold + confirm
    return rows


def _failed_break_scene():
    rows = _flat(40)
    for row in rows:
        row.update(prev_day_high=100.5, prev_day_low=99.5)
    rows[15].update(open=99.5, high=99.6, low=99.1, close=99.2)         # breaks below
    rows[16].update(open=99.2, high=99.4, low=99.1, close=99.3)
    rows[17].update(open=99.3, high=99.9, low=99.3, close=99.8)         # reclaims
    return rows


def _sweep_scene():
    rows = _flat(40)
    for row in rows:
        row.update(prev_day_low=99.5, prev_day_high=100.5)
    rows[15].update(open=99.6, high=99.7, low=99.2, close=99.55)        # wick below
    rows[16].update(open=99.55, high=100.0, low=99.5, close=99.95)      # quick reclaim
    return rows


def _range_scene():
    rows = _flat(40)
    for i, row in enumerate(rows):
        row.update(regime="RANGE", session_high=101.0, session_low=99.0, session_range=2.0)
    rows[19].update(open=99.2, high=99.25, low=99.05, close=99.1)
    rows[20].update(open=99.1, high=99.3, low=99.05, close=99.25)       # bounces off the low
    return rows


def _compression_scene():
    rows = _flat(40)
    for i, row in enumerate(rows):
        row.update(compression=1 if 10 <= i < 20 else 0, compression_ratio=0.4 if 10 <= i < 20 else 1.0)
    rows[20].update(open=100.0, high=100.8, low=99.9, close=100.7, compression=0, compression_ratio=2.0)
    return rows


def _drive_scene():
    rows = _flat(40)
    for row in rows:
        row.update(session_open=100.0, above_vwap=1)
    for i in range(10, 22):
        rows[i].update(open=101.0, high=101.2, low=100.9, close=101.1)  # the drive
    rows[24].update(open=101.1, high=101.15, low=100.95, close=101.0, structure="HIGHER_LOW")
    rows[25].update(open=101.0, high=101.4, low=101.0, close=101.3, structure="HIGHER_LOW")
    return rows


def _structure_scene():
    rows = _flat(40)
    rows[20].update(structure="HIGHER_LOW", open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(structure="HIGHER_LOW", open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _momentum_scene():
    rows = _flat(40)
    for row in rows:
        row.update(adx_14=30.0, ema_9_slope=0.05, above_ema_5_10=1, alignment="BULLISH")
    rows[20].update(open=100.0, high=100.3, low=99.9, close=100.2)
    rows[21].update(open=100.2, high=100.8, low=100.1, close=100.7)
    return rows


def _exhaustion_scene():
    rows = _flat(40)
    for row in rows:
        row.update(vwap_distance_atr=2.0, structure="LOWER_HIGH")
    rows[20].update(open=100.0, high=100.2, low=99.8, close=99.9)
    rows[21].update(open=99.9, high=100.0, low=99.4, close=99.5)
    return rows


def _confluence_scene():
    rows = _flat(40)
    for row in rows:
        row.update(confluence_count=4)
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _expected_move_scene():
    rows = _flat(40)
    for row in rows:
        row.update(move_consumed_pct=30.0, above_vwap=1)
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _time_of_day_scene():
    rows = _flat(40)
    for row in rows:
        row.update(time_bucket="MIDDAY", above_ema_5_10=1)
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _mtf_scene():
    rows = _flat(40)
    for row in rows:
        row.update(trend_5m="UP", trend_15m="UP", trend_60m="UP", trend_daily="UP")
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _gap_scene():
    rows = _flat(40)
    for row in rows:
        row.update(gap_pct=0.8, above_vwap=1)
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.6, low=100.0, close=100.5)
    return rows


def _gap_fade_scene():
    rows = _flat(40)
    for row in rows:
        row.update(gap_pct=0.8, above_vwap=0)
    rows[20].update(open=100.0, high=100.2, low=99.9, close=100.1)
    rows[21].update(open=100.1, high=100.0, low=99.4, close=99.5)
    return rows


def _playbook1_scene():
    rows = _flat(40)
    for row in rows:
        row.update(gap_pct=0.85, volume_zscore_20=2.0, momentum_score=-30.0, range_position=0.1)
    return rows


def _playbook2_scene():
    rows = _flat(40)
    for i, row in enumerate(rows):
        row.update(adx_14=30.0, efficiency_ratio=0.9, volume_zscore_20=1.5,
                   ema_9_slope=0.02, above_ema_5_10=0)
    rows[20].update(above_ema_5_10=0, ema_9_slope=0.01)
    rows[21].update(above_ema_5_10=1, ema_9_slope=0.05)                # clean cross up
    return rows


SCENES = [
    ("S5 premarket", ext.premarket_breakout(retest=True),
     lambda: _level_scene("premarket_high", "premarket_low")),
    ("S6 prev-day", ext.prev_day_breakout(retest=True), _level_scene),
    ("S6 prev-day immediate", ext.prev_day_breakout(retest=False), _level_scene),
    ("S7 failed breakout", ext.failed_breakout_reversal(), _failed_break_scene),
    ("S8 liquidity sweep", ext.liquidity_sweep(5), _sweep_scene),
    ("S9 range reversal", ext.range_extreme_reversal(), _range_scene),
    ("S11 compression", ext.compression_breakout(5), _compression_scene),
    ("S12 first pullback", ext.first_pullback_after_drive(0.5), _drive_scene),
    ("S13 structure", ext.structure_reversal(), _structure_scene),
    ("S14 momentum", ext.momentum_continuation(25.0), _momentum_scene),
    ("S15 exhaustion", ext.momentum_exhaustion(1.5), _exhaustion_scene),
    ("S16 confluence", ext.multi_level_confluence(3), _confluence_scene),
    ("S17 expected-move", ext.expected_move_breakout(75.0), _expected_move_scene),
    ("S18 time-of-day", ext.time_of_day_momentum("MIDDAY"), _time_of_day_scene),
    ("S19 mtf", ext.multi_timeframe_breakout(3), _mtf_scene),
    ("S21 gap continuation", ext.gap_continuation(0.5), _gap_scene),
    ("S22 gap fade", ext.gap_fade(0.5), _gap_fade_scene),
    ("PB1 gap fade", ext.playbook_opening_gap_fade(), _playbook1_scene),
    ("PB2 squeeze", ext.playbook_momentum_squeeze(0.75), _playbook2_scene),
]


@pytest.mark.parametrize("name,fn,scene", SCENES)
def test_each_strategy_fires_on_a_scene_built_for_it(name, fn, scene):
    """Guards against a strategy that can never trigger - which would
    otherwise show up as a clean 0-trade row and be mistaken for 'no
    setups occurred' rather than 'this code is broken'."""
    assert fn(scene()), f"{name} produced no signal on a scene designed to trigger it"


@pytest.mark.parametrize("name,fn,scene", SCENES)
def test_no_extended_strategy_reads_bars_that_had_not_printed(name, fn, scene):
    rows = scene()
    for index, direction in fn(rows):
        truncated = fn(rows[: index + 1])
        assert (index, direction) in truncated, (
            f"{name}: signal at bar {index} vanishes when later bars are removed - "
            f"it is reading the future"
        )


# ---------------------------------------------------------------------------
# Spec fidelity
# ---------------------------------------------------------------------------

def test_playbook_1_honours_its_stated_entry_window_and_thresholds():
    """The spec fixes this one precisely: gap >= 0.40%, 09:45-10:00 only,
    volume z-score > 1.5. Loosening any of them silently would mean
    measuring a different strategy than the one written down."""
    fn = ext.playbook_opening_gap_fade()

    rows = _playbook1_scene()
    minutes = {rows[i]["minutes_since_open"] for i, _ in fn(rows)}
    assert minutes and all(15 <= m <= 30 for m in minutes), "traded outside 09:45-10:00"

    small_gap = _playbook1_scene()
    for row in small_gap:
        row["gap_pct"] = 0.30
    assert fn(small_gap) == [], "traded a gap below the 0.40% threshold"

    quiet = _playbook1_scene()
    for row in quiet:
        row["volume_zscore_20"] = 1.0
    assert fn(quiet) == [], "traded without the required volume z-score"


def test_playbook_2_stands_down_below_its_adx_and_efficiency_gates():
    fn = ext.playbook_momentum_squeeze(0.75)
    assert fn(_playbook2_scene()), "scene should trigger"

    low_adx = _playbook2_scene()
    for row in low_adx:
        row["adx_14"] = 20.0
    assert fn(low_adx) == [], "traded with ADX below 25"

    choppy = _playbook2_scene()
    for row in choppy:
        row["efficiency_ratio"] = 0.5
    assert fn(choppy) == [], "traded below the efficiency floor"


def test_range_reversal_trend_filter_actually_changes_behaviour():
    """The spec insists a range strategy needs a trend filter. If the
    filtered and unfiltered variants behaved identically, the comparison
    the sweep reports would be meaningless."""
    rows = _range_scene()
    for row in rows:
        row["regime"] = "STRONG_BULL_TREND"
    assert ext.range_extreme_reversal(require_range_regime=True)(rows) == []
    assert ext.range_extreme_reversal(require_range_regime=False)(rows)


def test_untestable_strategies_are_declared_rather_than_silently_missing():
    """A library of 22 that reports 20 results must say which two are
    absent and why, or the gap reads as an oversight."""
    assert "S20 Relative-Strength Breakout" in ext.UNTESTABLE
    assert "PB3 Mid-Day Theta Burn" in ext.UNTESTABLE
    for reason in ext.UNTESTABLE.values():
        assert len(reason) > 40, "a one-word reason is not a reason"


def test_every_registered_variant_is_callable_and_returns_pairs():
    rows = _flat(40)
    for family, members in ext.build_extended_variants().items():
        for variant, fn in members.items():
            result = fn(rows)
            assert isinstance(result, list)
            for item in result:
                assert len(item) == 2 and item[1] in ("LONG", "SHORT")
