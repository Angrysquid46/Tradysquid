"""Tests for the time-efficiency exit, the third leg of the exit model
alongside price stops and thesis invalidation: a position can be neither
winning nor losing by price while still bleeding value to theta every day
it sits stuck. Only fires after real time has passed and only when the
position is genuinely stuck near breakeven, not simply drifting toward a
real stop."""

from __future__ import annotations

from datetime import timedelta

import ford_scan


def _row(hours_ago: float, **overrides) -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    entered = ford_scan.now_ct() - timedelta(hours=hours_ago)
    row.update({"trade_id": "T-1", "ticker": "F", "timestamp": entered.isoformat()})
    row.update(overrides)
    return row


def test_a_fresh_position_never_triggers_this_regardless_of_theta_burden():
    # Entered 1 hour ago - hasn't had real time to develop yet, even with
    # a high theta burden.
    row = _row(hours_ago=1.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.10, mark=1.00, pnl_pct=0.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_a_stuck_position_with_high_theta_burden_after_real_time_triggers():
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.08, mark=1.00, pnl_pct=1.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is True
    assert "theta" in note


def test_a_stuck_position_with_low_theta_burden_does_not_trigger():
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.01, mark=1.00, pnl_pct=1.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_a_position_clearly_heading_toward_a_real_loss_is_not_stuck():
    # -25% is well outside the "stuck near breakeven" band - this is what
    # the real price stop is for, not this check.
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.20, mark=1.00, pnl_pct=-25.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_a_position_clearly_winning_is_not_stuck_either():
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.20, mark=1.00, pnl_pct=25.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_missing_theta_never_triggers_or_crashes():
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=None, mark=1.00, pnl_pct=1.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_missing_entry_timestamp_never_triggers_or_crashes():
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row["timestamp"] = ""
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.20, mark=1.00, pnl_pct=1.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_zero_or_negative_mark_never_triggers_or_crashes_on_division():
    row = _row(hours_ago=24.0)
    triggered, note = ford_scan.check_time_efficiency_exit(
        row, theta=-0.20, mark=0.0, pnl_pct=1.0, timestamp=ford_scan.now_ct()
    )
    assert triggered is False


def test_end_to_end_through_evaluate_open_row_actually_fires():
    # Exercises the real call site, not just the isolated function - this
    # is what would have caught passing the wrong value into theta.
    entered = ford_scan.now_ct() - ford_scan.timedelta(hours=30)
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({
        "trade_id": "T-TIME-1", "ticker": "F", "play_type": "SWING",
        "call_or_put": "call", "entry_price": "1.00",
        "option_symbol": "F260821C00100000",
        "delta_at_entry": "0.32", "iv_at_entry": "0.41",
        "timestamp": entered.isoformat(),
        "expiration": (ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        "max_favorable_pct": "0",
    })
    quotes = {
        "F260821C00100000": {
            "symbol": "F260821C00100000", "bid": 0.99, "ask": 1.01,
            "greeks": {"delta": 0.31, "theta": -0.08, "mid_iv": 0.41},
        }
    }
    evaluation = ford_scan.evaluate_open_row(row, quotes, ford_scan.now_ct())
    assert evaluation.get("signal") == "TIME DECAY EXIT"
