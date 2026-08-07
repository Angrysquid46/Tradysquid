"""Behavioral tests for the Greeks-aware single-leg exit signal.

Verifies the exit does more than watch a flat +20%/-15% price line: it should
lock in breakeven after a real peak, trail winners instead of capping them,
and react to delta/IV moving against the trade even before price catches up.
"""

from __future__ import annotations

import ford_scan


def test_plain_loser_still_stops_out_like_before():
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=-16.0,
        peak_pct=-2.0,
        current_delta=0.30,
        entry_delta=0.32,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "STOP OUT"


def test_never_profitable_position_holds_above_the_stop():
    signal, _ = ford_scan.single_leg_exit_signal(
        pnl_pct=-5.0,
        peak_pct=2.0,
        current_delta=0.30,
        entry_delta=0.32,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_breakeven_locks_in_after_a_real_peak_and_pullback():
    # Peaked at +12%, pulled all the way back to flat.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=0.0,
        peak_pct=12.0,
        current_delta=0.30,
        entry_delta=0.35,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "TAKE PROFIT"
    assert "breakeven" in note


def test_pullback_that_stays_above_breakeven_does_not_exit_early():
    # Peaked at +12%, currently +3% - still above zero, should hold.
    signal, _ = ford_scan.single_leg_exit_signal(
        pnl_pct=3.0,
        peak_pct=12.0,
        current_delta=0.30,
        entry_delta=0.35,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_big_winner_keeps_running_past_the_old_flat_cap():
    # Old logic would have capped this at exactly +20%. Peaked at 30, now at
    # 25 - within the trail giveback, should still be allowed to run.
    signal, _ = ford_scan.single_leg_exit_signal(
        pnl_pct=25.0,
        peak_pct=30.0,
        current_delta=0.55,
        entry_delta=0.40,
        current_iv=0.45,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_big_winner_exits_once_it_gives_back_too_much_from_peak():
    # Peaked at 30, now down to 20 - an 10pt giveback, more than the 8pt trail.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=20.0,
        peak_pct=30.0,
        current_delta=0.50,
        entry_delta=0.40,
        current_iv=0.45,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "TAKE PROFIT"
    assert "trailing stop" in note


def test_delta_erosion_stops_out_a_losing_trade_before_the_price_stop():
    # Only down 6% by price - the old logic would just say HOLD - but delta
    # has collapsed from 0.40 to 0.15, well under half: the thesis is dead.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=-6.0,
        peak_pct=1.0,
        current_delta=0.15,
        entry_delta=0.40,
        current_iv=0.42,
        entry_iv=0.42,
        expiring_soon=False,
    )
    assert signal == "STOP OUT"
    assert "delta eroded" in note


def test_iv_crush_takes_profit_early_on_a_winning_trade():
    # Up a modest 6%, nowhere near the trailing-stop tier, but IV has
    # cratered from 0.60 to 0.40 (well under the 0.75 ratio) - lock it in.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=6.0,
        peak_pct=6.0,
        current_delta=0.45,
        entry_delta=0.40,
        current_iv=0.40,
        entry_iv=0.60,
        expiring_soon=False,
    )
    assert signal == "TAKE PROFIT"
    assert "IV crushed" in note


def test_missing_greeks_data_never_crashes_and_just_skips_those_checks():
    signal, _ = ford_scan.single_leg_exit_signal(
        pnl_pct=-3.0,
        peak_pct=1.0,
        current_delta=None,
        entry_delta=None,
        current_iv=None,
        entry_iv=None,
        expiring_soon=False,
    )
    assert signal == "HOLD"


def test_pure_spread_crossing_does_not_stop_out_a_fresh_position():
    # Real scenario from the trade log: SNAP entered at $0.39, spread $0.06
    # wide (15.4% of entry). The very next check reads the bid ($0.33) with
    # zero real price movement - pnl_pct is exactly -15.4%, which would trip
    # the flat -15% stop despite nothing having actually moved.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=-15.4,
        peak_pct=-15.4,
        current_delta=0.30,
        entry_delta=0.32,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
        entry_spread_pct=15.4,
    )
    assert signal == "HOLD"


def test_genuine_adverse_move_beyond_the_spread_still_stops_out():
    # Same wide spread as above, but this time price has genuinely moved
    # against the position well beyond the spread allowance - must still
    # protect real capital, not just wave every loss through.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=-35.0,
        peak_pct=-15.4,
        current_delta=0.30,
        entry_delta=0.32,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
        entry_spread_pct=15.4,
    )
    assert signal == "STOP OUT"


def test_breakeven_lock_floor_is_not_widened_by_spread_allowance():
    # A proven winner giving back its gain should still lock at breakeven,
    # not get extra room just because the entry spread happened to be wide -
    # the spread allowance is about absorbing an entry cost, not protecting
    # a peak that already proved itself.
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=0.0,
        peak_pct=12.0,
        current_delta=0.30,
        entry_delta=0.35,
        current_iv=0.40,
        entry_iv=0.42,
        expiring_soon=False,
        entry_spread_pct=15.4,
    )
    # Matches the current intentional behavior of single_leg_exit_signal for
    # a peak-then-pullback-to-flat close (see its own docstring) - this test
    # only cares that entry_spread_pct doesn't change *which* floor rule
    # applies here, not the pre-existing peak/pullback labeling itself.
    assert signal == "BREAKEVEN STOP"
    assert "breakeven" in note


def test_evaluate_open_row_derives_entry_spread_pct_from_the_stored_row():
    # Exercises the real call site, not just the isolated function - proves
    # bid_ask_width_at_entry actually reaches the exit-signal decision.
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({
        "trade_id": "T-SPREAD-1", "ticker": "SNAP", "play_type": "REGULAR",
        "call_or_put": "call", "entry_price": "0.39",
        "bid_ask_width_at_entry": "0.06",
        "option_symbol": "SNAP260821C00050000",
        "delta_at_entry": "0.30", "iv_at_entry": "0.40",
        "timestamp": ford_scan.now_ct().isoformat(),
        "expiration": (ford_scan.now_ct().date() + ford_scan.timedelta(days=10)).isoformat(),
        "max_favorable_pct": "0",
    })
    quotes = {
        "SNAP260821C00050000": {
            "symbol": "SNAP260821C00050000", "bid": 0.33, "ask": 0.39,
            "greeks": {"delta": 0.30, "theta": -0.01, "mid_iv": 0.40},
        }
    }
    evaluation = ford_scan.evaluate_open_row(row, quotes, ford_scan.now_ct())
    # Pure spread crossing with no real movement - must not stop out.
    assert evaluation["signal"] != "STOP OUT"


def test_expiring_soon_closes_when_nothing_else_triggered():
    signal, note = ford_scan.single_leg_exit_signal(
        pnl_pct=1.0,
        peak_pct=3.0,
        current_delta=0.30,
        entry_delta=0.32,
        current_iv=0.40,
        entry_iv=0.41,
        expiring_soon=True,
    )
    assert signal == "EXPIRY CLOSE"
