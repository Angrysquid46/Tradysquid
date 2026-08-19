from __future__ import annotations

import backtest_exit
import spy_scanner as s


def test_stop_out_before_any_step_has_fired():
    signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.24, minutes_remaining=120, peak_pct=0.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert signal == "STOP OUT"


def test_take_profit_past_target():
    signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.80, minutes_remaining=120, peak_pct=60.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert signal == "TAKE PROFIT"


def test_breakeven_stop_once_floor_has_raised():
    signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.415, minutes_remaining=120, peak_pct=35.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert signal == "BREAKEVEN STOP"


def test_eod_close_inside_the_closing_window():
    signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.52, minutes_remaining=10, peak_pct=4.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert signal == "EOD CLOSE"


def test_hold_with_no_exit_condition_met():
    signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.52, minutes_remaining=120, peak_pct=4.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert signal == "HOLD"


def test_a_tighter_stop_variant_stops_out_where_the_default_would_still_hold():
    tight_signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.40, minutes_remaining=120, peak_pct=0.0,
        stop_pct=0.15, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    default_signal, _ = backtest_exit.backtest_exit_signal(
        entry_price=0.50, mark=0.40, minutes_remaining=120, peak_pct=0.0,
        stop_pct=0.50, target_pct=0.50, floor_pct=-15.0, floor_trigger_pct=30.0,
    )
    assert tight_signal == "STOP OUT"
    assert default_signal == "HOLD"


def test_matches_the_live_exit_function_when_fed_the_live_defaults():
    """Drift guard: the two functions' logic must stay identical. Sweep a
    range of mark/peak/minutes combinations and confirm the parameterized
    clone matches the live spy_premium_exit_signal exactly when given the
    live module's own current constants."""
    scenarios = [
        (0.50, 0.20, 120, 0.0),
        (0.50, 0.80, 120, 60.0),
        (0.50, 0.415, 120, 35.0),
        (0.50, 0.52, 10, 4.0),
        (0.50, 0.52, 120, 4.0),
        (1.20, 0.90, 5, 15.0),
        (2.00, 3.10, 120, 55.0),
    ]
    for entry_price, mark, minutes_remaining, peak_pct in scenarios:
        live_signal, _ = s.spy_premium_exit_signal(entry_price, mark, minutes_remaining, peak_pct)
        clone_signal, _ = backtest_exit.backtest_exit_signal(
            entry_price, mark, minutes_remaining, peak_pct,
            stop_pct=s.SPY_STOP_PCT, target_pct=s.SPY_TARGET_PCT,
            floor_pct=s.SPY_FLOOR_PCT, floor_trigger_pct=s.SPY_FLOOR_TRIGGER_PCT,
        )
        assert clone_signal == live_signal, (entry_price, mark, minutes_remaining, peak_pct)
