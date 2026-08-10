"""Tests for the standalone SPY 0-1 DTE Expansion-Level strategy - built
entirely separate from SPY_0DTE and SPY_KEY_LEVELS per the same "independent
and unattached" owner direction. These tests exist specifically to prove
this strategy's constants, signal, and exit logic never quietly borrow
either sibling strategy's (delta band, risk cap, stop model, level
calculators), and that its own EMA/MACD/level math is correct in isolation.
"""

from __future__ import annotations

import spy_scanner


def _bar(close: float, high: float | None = None, low: float | None = None, volume: float = 100_000) -> dict:
    return {
        "close": close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
        "volume": volume,
    }


def _option(delta: float, ask: float, option_type: str = "call", strike: float = 600.0, bid: float | None = None) -> dict:
    return {
        "strike": strike,
        "option_type": option_type,
        "bid": bid if bid is not None else max(ask - 0.05, 0.01),
        "ask": ask,
        "open_interest": 500,
        "volume": 200,
        "greeks": {"delta": delta, "theta": -0.3},
        "symbol": f"SPY_TEST_{option_type}_{strike}",
    }


# ---------------------------------------------------------------------------
# Isolation from SPY_0DTE and SPY_KEY_LEVELS
# ---------------------------------------------------------------------------


def test_expansion_play_type_is_distinct_from_siblings():
    assert spy_scanner.SPY_EXPANSION_PLAY_TYPE not in spy_scanner.SPY_0DTE_PLAY_TYPES
    assert spy_scanner.SPY_EXPANSION_PLAY_TYPE != spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE


def test_expansion_exit_signal_uses_its_own_constants_not_0dtes():
    import inspect
    source = inspect.getsource(spy_scanner.spy_expansion_exit_signal)
    assert "SPY_0DTE" not in source
    assert "SPY_KEY_LEVELS" not in source
    assert "SPY_EXPANSION" in source


def test_evaluate_open_row_dispatches_expansion_rows_to_its_own_evaluator():
    row = spy_scanner.blank_row()
    row.update({
        "play_type": spy_scanner.SPY_EXPANSION_PLAY_TYPE,
        "entry_price": "1.00",
        "call_or_put": "call",
        "option_symbol": "MISSING",
    })
    result = spy_scanner.evaluate_open_row(row, {}, spy_scanner.now_ct())
    assert result["signal"] == "HOLD"
    assert "quote" in result["note"].lower()


def test_expansion_close_signal_is_its_own_distinct_string():
    # Regression guard: distinct from both "EOD CLOSE" (SPY_0DTE) and
    # "EXPIRATION CLOSE" (SPY_KEY_LEVELS) so wiring it into main()'s shared
    # close-trigger set can't change either sibling's own behavior.
    import inspect
    source = inspect.getsource(spy_scanner)
    assert '"EXPANSION EOD CLOSE"' in source


# ---------------------------------------------------------------------------
# EMA / MACD math
# ---------------------------------------------------------------------------


def test_ema_series_matches_hand_calculation():
    series = spy_scanner.exponential_moving_average_series([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert series == [None, None, 2.0, 3.0, 4.0]


def test_ema_of_constant_series_equals_the_constant():
    assert spy_scanner.exponential_moving_average([100.0] * 30, 12) == 100.0


def test_ema_none_when_insufficient_data():
    assert spy_scanner.exponential_moving_average([1.0, 2.0], 5) is None


def test_ema_direction_bullish_when_fast_above_slow():
    rising = [600.0 + 0.5 * i for i in range(250)]
    direction, fast, slow = spy_scanner.spy_expansion_ema_direction(rising)
    assert direction == "BULLISH"
    assert fast > slow


def test_ema_direction_bearish_when_fast_below_slow():
    falling = [900.0 - 0.5 * i for i in range(250)]
    direction, fast, slow = spy_scanner.spy_expansion_ema_direction(falling)
    assert direction == "BEARISH"
    assert fast < slow


def test_ema_direction_unknown_with_insufficient_history():
    direction, fast, slow = spy_scanner.spy_expansion_ema_direction([600.0] * 50)
    assert direction == "UNKNOWN"
    assert slow is None


def test_macd_color_bright_green_when_above_zero_and_rising():
    assert spy_scanner.spy_expansion_macd_color(0.5, 0.3) == "BRIGHT_GREEN"


def test_macd_color_dark_green_when_above_zero_and_fading():
    assert spy_scanner.spy_expansion_macd_color(0.3, 0.5) == "DARK_GREEN"


def test_macd_color_bright_red_when_below_zero_and_falling():
    assert spy_scanner.spy_expansion_macd_color(-0.5, -0.3) == "BRIGHT_RED"


def test_macd_color_dark_red_when_below_zero_and_recovering():
    assert spy_scanner.spy_expansion_macd_color(-0.3, -0.5) == "DARK_RED"


def test_macd_color_unknown_without_data():
    assert spy_scanner.spy_expansion_macd_color(None, None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Reference levels
# ---------------------------------------------------------------------------


def test_prior_day_range_skips_todays_partial_bar():
    daily_bars = [
        {"date": "2026-08-07", "high": 601.0, "low": 599.0, "close": 600.0},
        {"date": "2026-08-08", "high": 604.0, "low": 602.0, "close": 603.0},
        {"date": "2026-08-10", "high": 610.0, "low": 608.0, "close": 609.0},
    ]
    high, low = spy_scanner.spy_expansion_prior_day_range(daily_bars, "2026-08-10")
    assert (high, low) == (604.0, 602.0)


def test_prior_week_range_only_uses_the_single_prior_iso_week():
    daily_bars = [
        {"date": "2026-07-27", "high": 590.0, "low": 585.0, "close": 588.0},
        {"date": "2026-08-03", "high": 600.0, "low": 595.0, "close": 598.0},
        {"date": "2026-08-07", "high": 605.0, "low": 596.0, "close": 602.0},
        {"date": "2026-08-10", "high": 620.0, "low": 615.0, "close": 618.0},
    ]
    high, low = spy_scanner.spy_expansion_prior_week_range(daily_bars, "2026-08-10")
    assert (high, low) == (605.0, 595.0)


def test_prior_month_range_only_uses_the_single_prior_month():
    daily_bars = [
        {"date": "2026-06-15", "high": 580.0, "low": 575.0, "close": 578.0},
        {"date": "2026-07-01", "high": 600.0, "low": 590.0, "close": 595.0},
        {"date": "2026-07-31", "high": 610.0, "low": 592.0, "close": 605.0},
        {"date": "2026-08-05", "high": 625.0, "low": 620.0, "close": 622.0},
    ]
    high, low = spy_scanner.spy_expansion_prior_month_range(daily_bars, "2026-08-10")
    assert (high, low) == (610.0, 590.0)


def test_nearest_level_finds_closest_within_tolerance():
    levels = {"PDH": 610.0, "PWH": 615.0}
    code, price, distance = spy_scanner.spy_expansion_nearest_level(610.2, levels)
    assert code == "PDH"
    assert price == 610.0
    assert round(distance, 2) == 0.2


def test_nearest_level_none_outside_tolerance():
    levels = {"PDH": 610.0}
    code, price, distance = spy_scanner.spy_expansion_nearest_level(650.0, levels)
    assert (code, price, distance) == (None, None, None)


def test_nearest_level_uses_the_dollar_tolerance_formula_from_the_spec():
    levels = {"PDH": 610.0}
    just_inside = 610.0 + spy_scanner.SPY_EXPANSION_LEVEL_TOLERANCE
    just_outside = 610.0 + spy_scanner.SPY_EXPANSION_LEVEL_TOLERANCE + 0.01
    assert spy_scanner.spy_expansion_nearest_level(just_inside, levels)[0] == "PDH"
    assert spy_scanner.spy_expansion_nearest_level(just_outside, levels)[0] is None


# ---------------------------------------------------------------------------
# Signal state machine
# ---------------------------------------------------------------------------


_BULLISH_READ = {"ema_direction": "BULLISH", "ema_fast": 610, "ema_slow": 600, "macd_histogram": 0.5, "macd_color": "BRIGHT_GREEN"}
_WATCHING_BULLISH_READ = {"ema_direction": "BULLISH", "ema_fast": 610, "ema_slow": 600, "macd_histogram": 0.1, "macd_color": "DARK_GREEN"}
_BEARISH_READ = {"ema_direction": "BEARISH", "ema_fast": 600, "ema_slow": 610, "macd_histogram": -0.5, "macd_color": "BRIGHT_RED"}
_WATCHING_BEARISH_READ = {"ema_direction": "BEARISH", "ema_fast": 600, "ema_slow": 610, "macd_histogram": -0.1, "macd_color": "DARK_RED"}
_LEVELS = {"PDH": 610.0}


def test_signal_no_setup_when_not_near_any_level():
    result = spy_scanner.spy_expansion_signal(
        spot_price=650.0, levels=_LEVELS,
        timeframe_reads={"15m": _BULLISH_READ, "30m": _BULLISH_READ, "1h": _BULLISH_READ},
    )
    assert result["state"] == "NO_SETUP"


def test_signal_call_qualified_when_fully_aligned_bullish():
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _BULLISH_READ, "30m": _BULLISH_READ, "1h": _BULLISH_READ},
    )
    assert result["state"] == "CALL_ENTRY_QUALIFIED"
    assert result["side"] == "call"
    assert result["timeframes_aligned"] is True
    assert result["reference_level_type"] == "PDH"


def test_signal_put_qualified_when_fully_aligned_bearish():
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _BEARISH_READ, "30m": _BEARISH_READ, "1h": _BEARISH_READ},
    )
    assert result["state"] == "PUT_ENTRY_QUALIFIED"
    assert result["side"] == "put"


def test_signal_watching_bullish_when_macd_confirmation_missing():
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _WATCHING_BULLISH_READ, "30m": _BULLISH_READ, "1h": _BULLISH_READ},
    )
    assert result["state"] == "WATCHING_BULLISH_LEVEL"


def test_signal_watching_bearish_when_macd_confirmation_missing():
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _WATCHING_BEARISH_READ, "30m": _BEARISH_READ, "1h": _BEARISH_READ},
    )
    assert result["state"] == "WATCHING_BEARISH_LEVEL"


def test_signal_no_setup_when_ema_structure_mixed_across_timeframes():
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _BULLISH_READ, "30m": _BEARISH_READ, "1h": _BULLISH_READ},
    )
    assert result["state"] == "NO_SETUP"


def test_signal_requires_all_three_timeframes_not_a_majority():
    # Two of three bright-green, one still dark - must NOT qualify, since
    # the spec requires alignment "on the required higher timeframes"
    # (all of them), not a majority vote like a different strategy's design.
    result = spy_scanner.spy_expansion_signal(
        spot_price=610.2, levels=_LEVELS,
        timeframe_reads={"15m": _BULLISH_READ, "30m": _BULLISH_READ, "1h": _WATCHING_BULLISH_READ},
    )
    assert result["state"] == "WATCHING_BULLISH_LEVEL"


# ---------------------------------------------------------------------------
# Expiration selection
# ---------------------------------------------------------------------------


def test_choose_expiration_prefers_0dte_when_listed():
    assert spy_scanner.spy_expansion_choose_expiration(
        ["2026-08-10", "2026-08-11"], "2026-08-10"
    ) == "2026-08-10"


def test_choose_expiration_falls_back_to_1dte():
    assert spy_scanner.spy_expansion_choose_expiration(
        ["2026-08-11", "2026-08-13"], "2026-08-10"
    ) == "2026-08-11"


def test_choose_expiration_none_when_neither_0dte_nor_1dte_listed():
    assert spy_scanner.spy_expansion_choose_expiration(["2026-08-15"], "2026-08-10") is None


# ---------------------------------------------------------------------------
# Stop/target/exit
# ---------------------------------------------------------------------------


def test_stop_and_target_percentages_match_configured_constants():
    stop, target = spy_scanner.spy_expansion_stop_and_target("call", 2.00)
    assert stop == round(2.00 * (1 - spy_scanner.SPY_EXPANSION_STOP_PCT), 4)
    assert target == round(2.00 * (1 + spy_scanner.SPY_EXPANSION_TARGET_PCT), 4)


def test_exit_signal_stops_out():
    signal, _ = spy_scanner.spy_expansion_exit_signal(2.00, 1.00, 200, 0.0)
    assert signal == "STOP OUT"


def test_exit_signal_takes_profit():
    signal, _ = spy_scanner.spy_expansion_exit_signal(2.00, 3.00, 200, 0.0)
    assert signal == "TAKE PROFIT"


def test_exit_signal_forces_close_near_session_end():
    signal, _ = spy_scanner.spy_expansion_exit_signal(2.00, 1.98, 10, 5.0)
    assert signal == "EXPANSION EOD CLOSE"


def test_exit_signal_breakeven_floor_after_peak():
    # peak_pct=35 clears the floor trigger (30); mark=1.69 puts pnl at -15.5%,
    # past the -15% floor but nowhere near the full -50% stop - must use the
    # tightened floor, not the original stop.
    signal, note = spy_scanner.spy_expansion_exit_signal(2.00, 1.69, 200, 35.0)
    assert signal == "BREAKEVEN STOP"


# ---------------------------------------------------------------------------
# Candidate builder
# ---------------------------------------------------------------------------


def test_candidate_builder_respects_its_own_delta_band():
    signal = {"side": "call", "reference_level_type": "PDH", "reason": "test"}
    chain = [_option(delta=0.10, ask=1.0), _option(delta=0.50, ask=1.5)]
    candidates = spy_scanner.scan_spy_expansion_candidates(chain, signal, "2026-08-10", spot_price=600.0)
    assert len(candidates) == 1
    assert candidates[0]["delta"] == 0.5
    assert candidates[0]["play_type"] == spy_scanner.SPY_EXPANSION_PLAY_TYPE


def test_candidate_builder_filters_to_the_requested_side_only():
    signal = {"side": "put", "reference_level_type": "PWL", "reason": "test"}
    chain = [_option(delta=0.50, ask=1.0, option_type="call"), _option(delta=0.50, ask=1.0, option_type="put")]
    candidates = spy_scanner.scan_spy_expansion_candidates(chain, signal, "2026-08-10", spot_price=600.0)
    assert len(candidates) == 1
    assert candidates[0]["call_or_put"] == "put"
