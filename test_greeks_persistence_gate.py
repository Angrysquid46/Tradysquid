"""Tests for the Greeks-persistence gate: Tradier's Greeks data refreshes
roughly once an hour, not continuously (confirmed independently, not
assumed) - so a delta-erosion or IV-crush exit reacting to a single reading
could really be reacting to an hour-stale snapshot. This requires the same
condition to hold on two consecutive checks before actually closing
anything."""

from __future__ import annotations

import ford_scan


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update(overrides)
    return row


def test_a_single_delta_erosion_reading_does_not_close_the_position():
    row = _row(delta_erosion_streak="0", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "STOP OUT", "delta eroded from 0.35 to 0.15; the thesis lost its edge before the price stop hit"
    )
    assert signal == "HOLD"
    assert row["delta_erosion_streak"] == "1"


def test_a_second_consecutive_delta_erosion_reading_confirms_the_close():
    row = _row(delta_erosion_streak="1", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "STOP OUT", "delta eroded from 0.35 to 0.15; the thesis lost its edge before the price stop hit"
    )
    assert signal == "STOP OUT"
    assert row["delta_erosion_streak"] == "0"


def test_a_single_iv_crush_reading_does_not_take_profit_yet():
    row = _row(delta_erosion_streak="0", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "TAKE PROFIT", "IV crushed from 0.60 to 0.40 while profitable; locking in the gain before further decay"
    )
    assert signal == "HOLD"
    assert row["iv_crush_streak"] == "1"


def test_a_second_consecutive_iv_crush_reading_confirms_the_take_profit():
    row = _row(delta_erosion_streak="0", iv_crush_streak="1")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "TAKE PROFIT", "IV crushed from 0.60 to 0.40 while profitable; locking in the gain before further decay"
    )
    assert signal == "TAKE PROFIT"
    assert row["iv_crush_streak"] == "0"


def test_the_streak_resets_if_the_condition_does_not_reappear_next_check():
    # First check: delta erosion seen once, streak set to 1.
    row = _row(delta_erosion_streak="0", iv_crush_streak="0")
    ford_scan.apply_greeks_persistence_gate(
        row, "STOP OUT", "delta eroded from 0.35 to 0.15; the thesis lost its edge before the price stop hit"
    )
    assert row["delta_erosion_streak"] == "1"
    # Next check: price recovered, ordinary HOLD with no erosion note -
    # the streak must reset, not silently carry over and confirm later on
    # an unrelated signal.
    signal, note = ford_scan.apply_greeks_persistence_gate(row, "HOLD", "holding")
    assert row["delta_erosion_streak"] == "0"


def test_a_genuine_price_stop_is_never_gated_by_this():
    # A real price-based stop must fire immediately - this gate is only
    # for the two signals that depend on potentially-stale Greeks data.
    row = _row(delta_erosion_streak="0", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "STOP OUT", "-18% pnl hit the -15% stop"
    )
    assert signal == "STOP OUT"


def test_a_genuine_trailing_take_profit_is_never_gated_by_this():
    row = _row(delta_erosion_streak="0", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "TAKE PROFIT", "trailing stop: 25% is down 8 pts from the 33% peak"
    )
    assert signal == "TAKE PROFIT"


def test_delta_and_iv_streaks_are_tracked_independently():
    # An IV-crush confirmation must not be able to piggyback on a
    # delta-erosion streak, or vice versa.
    row = _row(delta_erosion_streak="1", iv_crush_streak="0")
    signal, note = ford_scan.apply_greeks_persistence_gate(
        row, "TAKE PROFIT", "IV crushed from 0.60 to 0.40 while profitable; locking in the gain before further decay"
    )
    assert signal == "HOLD"
    assert row["iv_crush_streak"] == "1"
    assert row["delta_erosion_streak"] == "0"  # cleared - it wasn't the active signal this check
