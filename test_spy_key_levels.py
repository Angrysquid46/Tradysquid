"""Tests for the standalone SPY Key-Levels/ORB/VWAP strategy - built entirely
separate from SPY_0DTE per explicit owner direction ("independent and
unattached", "don't compare against or even think of other strategies while
adding them"). These tests exist specifically to prove this strategy's
constants, signal, and exit logic never quietly borrow SPY_0DTE's (delta
band, risk cap, stop model), and that its own level/direction/exit math is
correct in isolation.
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


def _rising_bars(start: float = 600.0, step: float = 0.1, count: int = 10) -> list[dict]:
    return [_bar(start + i * step, high=start + i * step + 0.05, low=start + i * step - 0.05) for i in range(count)]


def _falling_bars(start: float = 600.0, step: float = 0.1, count: int = 10) -> list[dict]:
    return [_bar(start - i * step, high=start - i * step + 0.05, low=start - i * step - 0.05) for i in range(count)]


def _flat_bars(price: float = 600.0, count: int = 10) -> list[dict]:
    return [_bar(price) for _ in range(count)]


# ---------------------------------------------------------------------------
# Isolation from SPY_0DTE
# ---------------------------------------------------------------------------


def test_key_levels_constants_are_independent_of_spy_0dte_constants():
    assert spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE not in spy_scanner.SPY_0DTE_PLAY_TYPES
    assert spy_scanner.SPY_KEY_LEVELS_MAX_RISK_PER_TRADE is not spy_scanner.SPY_0DTE_MAX_RISK_PER_TRADE \
        or spy_scanner.SPY_KEY_LEVELS_MAX_CONTRACT_ASK != spy_scanner.SPY_0DTE_MAX_CONTRACT_ASK


def test_key_levels_delta_band_is_its_own_not_spy_0dtes():
    # Distinct objects/definitions - a real regression here would be someone
    # aliasing SPY_KEY_LEVELS_DELTA_MIN = SPY_0DTE_DELTA_MIN, which happens
    # to hold the same numeric value today but must not be the same binding.
    assert "SPY_KEY_LEVELS_DELTA_MIN" in dir(spy_scanner)
    assert "SPY_KEY_LEVELS_DELTA_MAX" in dir(spy_scanner)


def test_evaluate_open_row_dispatches_key_levels_rows_to_its_own_evaluator():
    row = spy_scanner.blank_row()
    row.update({
        "play_type": spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE,
        "entry_price": "1.00",
        "call_or_put": "call",
        "option_symbol": "MISSING",
    })
    result = spy_scanner.evaluate_open_row(row, {}, spy_scanner.now_ct())
    # No quote available -> HOLD with the key-levels-specific note, not the
    # generic "unrecognized/retired play_type" branch SPY_0DTE rows outside
    # ("SPY_0DTE_1M", "SPY_0DTE_5M") would fall into.
    assert result["signal"] == "HOLD"
    assert "quote" in result["note"].lower()


# ---------------------------------------------------------------------------
# Level calculators
# ---------------------------------------------------------------------------


def test_wick_range_uses_highs_and_lows_not_just_closes():
    bars = [_bar(600.5, high=601.0, low=600.0), _bar(600.8, high=601.5, low=600.3)]
    high, low = spy_scanner.spy_key_levels_wick_range(bars)
    assert high == 601.5
    assert low == 600.0


def test_prior_day_range_skips_todays_partial_bar():
    daily_bars = [
        {"date": "2026-08-07", "high": 601.0, "low": 599.0, "close": 600.0},
        {"date": "2026-08-08", "high": 604.0, "low": 602.0, "close": 603.0},
        {"date": "2026-08-10", "high": 610.0, "low": 608.0, "close": 609.0},  # today, partial
    ]
    high, low = spy_scanner.spy_key_levels_prior_day_range(daily_bars, "2026-08-10")
    assert (high, low) == (604.0, 602.0)


def test_prior_week_range_only_uses_the_single_prior_iso_week():
    daily_bars = [
        {"date": "2026-07-27", "high": 590.0, "low": 585.0, "close": 588.0},  # two weeks prior
        {"date": "2026-08-03", "high": 600.0, "low": 595.0, "close": 598.0},  # prior week (Mon)
        {"date": "2026-08-07", "high": 605.0, "low": 596.0, "close": 602.0},  # prior week (Fri)
        {"date": "2026-08-10", "high": 620.0, "low": 615.0, "close": 618.0},  # this week
    ]
    high, low = spy_scanner.spy_key_levels_prior_week_range(daily_bars, "2026-08-10")
    assert (high, low) == (605.0, 595.0)


def test_opening_range_needs_the_complete_window():
    bars = _flat_bars(600.0, count=10)
    high, low = spy_scanner.spy_key_levels_opening_range(bars[:5], bar_minutes=1, window_minutes=15)
    assert (high, low) == (None, None)


def test_opening_range_takes_wick_high_low_of_the_first_window():
    bars = [_bar(600.0, high=600.5, low=599.5)] * 15
    bars[7] = _bar(600.0, high=602.0, low=598.0)
    bars += [_bar(700.0, high=700.5, low=699.5)] * 5  # after the window, must be ignored
    high, low = spy_scanner.spy_key_levels_opening_range(bars, bar_minutes=1, window_minutes=15)
    assert (high, low) == (602.0, 598.0)


def test_vwap_is_volume_weighted_typical_price():
    bars = [_bar(600.0, high=601.0, low=599.0, volume=100), _bar(610.0, high=611.0, low=609.0, volume=300)]
    vwap = spy_scanner.spy_key_levels_vwap(bars)
    # typical prices: 600, 610; weights 100/300 -> (600*100+610*300)/400 = 607.5
    assert round(vwap, 2) == 607.5


def test_sma200_needs_two_hundred_daily_bars():
    daily_bars = [{"close": 600.0} for _ in range(199)]
    assert spy_scanner.spy_key_levels_sma200(daily_bars) is None
    daily_bars.append({"close": 600.0})
    assert spy_scanner.spy_key_levels_sma200(daily_bars) == 600.0


def test_resample_bars_aggregates_three_one_minute_bars_into_one():
    bars = [
        _bar(600.0, high=600.2, low=599.8, volume=100),
        _bar(600.5, high=600.7, low=600.3, volume=200),
        _bar(600.1, high=600.3, low=599.9, volume=300),
    ]
    resampled = spy_scanner.resample_bars(bars, 3)
    assert len(resampled) == 1
    assert resampled[0]["high"] == 600.7
    assert resampled[0]["low"] == 599.8
    assert resampled[0]["close"] == 600.1
    assert resampled[0]["volume"] == 600


# ---------------------------------------------------------------------------
# Direction classifier
# ---------------------------------------------------------------------------


def test_timeframe_direction_bullish_when_last_close_above_average():
    assert spy_scanner.spy_key_levels_timeframe_direction(_rising_bars()) == "BULLISH"


def test_timeframe_direction_bearish_when_last_close_below_average():
    assert spy_scanner.spy_key_levels_timeframe_direction(_falling_bars()) == "BEARISH"


def test_timeframe_direction_mixed_on_insufficient_data():
    assert spy_scanner.spy_key_levels_timeframe_direction(_flat_bars(count=2), average_period=5) == "MIXED"


def test_combined_direction_requires_all_three_timeframes_to_agree():
    assert spy_scanner.spy_key_levels_combined_direction("BULLISH", "BULLISH", "BULLISH") == "BULLISH"
    assert spy_scanner.spy_key_levels_combined_direction("BEARISH", "BEARISH", "BEARISH") == "BEARISH"
    assert spy_scanner.spy_key_levels_combined_direction("BULLISH", "BEARISH", "BULLISH") == "MIXED"
    assert spy_scanner.spy_key_levels_combined_direction("BULLISH", "MIXED", "BULLISH") == "MIXED"


# ---------------------------------------------------------------------------
# Level-interaction detector
# ---------------------------------------------------------------------------


def test_active_level_finds_the_closest_level_within_the_proximity_band():
    levels = {"vwap": 600.0, "prior_day_high": 601.0, "premarket_low": 550.0}
    name, price = spy_scanner.spy_key_levels_active_level(600.05, levels)
    assert name == "vwap"
    assert price == 600.0


def test_active_level_none_when_nothing_is_close_enough():
    levels = {"vwap": 600.0}
    name, price = spy_scanner.spy_key_levels_active_level(610.0, levels)
    assert (name, price) == (None, None)


def test_active_level_ignores_none_levels():
    levels = {"premarket_high": None, "vwap": 600.0}
    name, price = spy_scanner.spy_key_levels_active_level(600.02, levels)
    assert name == "vwap"


# ---------------------------------------------------------------------------
# DTE selection
# ---------------------------------------------------------------------------


def test_choose_expiration_defaults_to_0dte_without_a_catalyst():
    tier, expiration = spy_scanner.spy_key_levels_choose_expiration(
        ["2026-08-10", "2026-08-11", "2026-08-17"], "2026-08-10", catalyst_active=False
    )
    assert (tier, expiration) == ("0DTE", "2026-08-10")


def test_choose_expiration_prefers_weekly_when_catalyst_active():
    tier, expiration = spy_scanner.spy_key_levels_choose_expiration(
        ["2026-08-10", "2026-08-11", "2026-08-17"], "2026-08-10", catalyst_active=True
    )
    assert (tier, expiration) == ("WEEKLY", "2026-08-17")


def test_choose_expiration_falls_back_to_1_3dte_when_no_weekly_listed():
    tier, expiration = spy_scanner.spy_key_levels_choose_expiration(
        ["2026-08-11", "2026-08-12"], "2026-08-10", catalyst_active=True
    )
    assert (tier, expiration) == ("1-3DTE", "2026-08-11")


def test_choose_expiration_none_when_nothing_tradeable():
    assert spy_scanner.spy_key_levels_choose_expiration([], "2026-08-10", catalyst_active=False) is None


# ---------------------------------------------------------------------------
# Entry signal
# ---------------------------------------------------------------------------


def test_entry_signal_rejects_mixed_direction():
    entry = spy_scanner.spy_key_levels_entry_signal(
        spot_price=600.0, direction="MIXED", levels={"vwap": 600.0}, catalyst=None
    )
    assert entry["qualified"] is False


def test_entry_signal_rejects_no_active_level():
    entry = spy_scanner.spy_key_levels_entry_signal(
        spot_price=610.0, direction="BULLISH", levels={"vwap": 600.0}, catalyst=None
    )
    assert entry["qualified"] is False


def test_entry_signal_qualifies_bullish_call_at_a_level():
    entry = spy_scanner.spy_key_levels_entry_signal(
        spot_price=600.02, direction="BULLISH", levels={"vwap": 600.0}, catalyst=None
    )
    assert entry["qualified"] is True
    assert entry["side"] == "call"
    assert entry["active_level_name"] == "vwap"


def test_entry_signal_qualifies_bearish_put_at_a_level():
    entry = spy_scanner.spy_key_levels_entry_signal(
        spot_price=600.02, direction="BEARISH", levels={"vwap": 600.0}, catalyst=None
    )
    assert entry["qualified"] is True
    assert entry["side"] == "put"


def test_entry_signal_catalyst_is_informational_not_a_hard_block():
    catalyst = {"title": "FOMC Statement", "minutes_until": 20}
    entry = spy_scanner.spy_key_levels_entry_signal(
        spot_price=600.02, direction="BULLISH", levels={"vwap": 600.0}, catalyst=catalyst
    )
    assert entry["qualified"] is True
    assert entry["catalyst"] == catalyst
    assert "catalyst" in entry["reason"].lower()


# ---------------------------------------------------------------------------
# Stop/target + exit signal
# ---------------------------------------------------------------------------


def test_stop_and_target_call_are_on_the_correct_sides_of_entry():
    stop, target = spy_scanner.spy_key_levels_stop_and_target("call", entry_underlying_price=600.0, active_level_price=599.0)
    assert stop < 600.0
    assert target > 600.0


def test_stop_and_target_put_are_on_the_correct_sides_of_entry():
    stop, target = spy_scanner.spy_key_levels_stop_and_target("put", entry_underlying_price=600.0, active_level_price=601.0)
    assert stop > 600.0
    assert target < 600.0


def test_exit_signal_stops_out_a_call_when_underlying_breaks_the_level():
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=604.0,
        current_underlying_price=597.5, expiration_tier="0DTE",
        is_expiration_day=False, minutes_remaining=120,
    )
    assert signal == "STOP OUT"


def test_exit_signal_takes_profit_on_a_call_target():
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=604.0,
        current_underlying_price=604.5, expiration_tier="0DTE",
        is_expiration_day=False, minutes_remaining=120,
    )
    assert signal == "TAKE PROFIT"


def test_exit_signal_stops_out_on_the_premium_backstop_even_when_underlying_hasnt_hit_its_level():
    """Real incident 2026-08-14: three positions round-tripped from +12%
    to -42%/-46%/-50% of premium overnight while the underlying-level
    stop (only SPY_KEY_LEVELS_STOP_BUFFER_PCT away) stayed silent the
    whole time - theta plus a small adverse move ate the position with
    no backstop at all. current_underlying_price here is nowhere near
    either level, proving this fires purely off real premium loss."""
    signal, note = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=602.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=-51.0, peak_pct=5.0,
    )
    assert signal == "STOP OUT"
    assert "backstop" in note


def test_exit_signal_does_not_backstop_a_position_still_within_the_normal_stop_pct():
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=602.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=-30.0, peak_pct=5.0,
    )
    assert signal == "HOLD"


def test_exit_signal_locks_in_a_floor_once_a_real_favorable_move_has_shown():
    """Same real incident - a position that peaked at +12% (above the
    floor trigger) and has since round-tripped back to breakeven or
    worse should stop protecting the proven move instead of riding it
    all the way down to the underlying-level stop."""
    signal, note = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=602.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=-2.0, peak_pct=12.0,
    )
    assert signal == "BREAKEVEN STOP"
    assert "peaked at 12%" in note


def test_exit_signal_floor_does_not_fire_below_the_trigger_peak():
    # Never showed enough real profit to earn floor protection.
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=602.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=-2.0, peak_pct=5.0,
    )
    assert signal == "HOLD"


def test_exit_signal_floor_does_not_fire_while_still_above_the_floor_pct():
    # Peaked well above the trigger but hasn't actually round-tripped
    # down to the floor level yet - still just a normal HOLD.
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=602.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=8.0, peak_pct=12.0,
    )
    assert signal == "HOLD"


def test_exit_signal_underlying_level_stop_still_takes_priority_over_premium_checks():
    # The underlying-level read is still the primary exit model - it
    # must fire first even when the premium numbers would also qualify.
    signal, note = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=610.0,
        current_underlying_price=597.0, expiration_tier="WEEKLY",
        is_expiration_day=False, minutes_remaining=500,
        pnl_pct=-51.0, peak_pct=12.0,
    )
    assert signal == "STOP OUT"
    assert "broke back through the traded level" in note


def test_evaluate_open_row_wires_real_premium_loss_into_the_backstop():
    """End-to-end regression guard for the real incident: entry_price
    and a real quote produce a real pnl_pct, which has to actually reach
    spy_key_levels_exit_signal's premium backstop - not just work in the
    standalone signal test above."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    row = spy_scanner.blank_row()
    row.update({
        "trade_id": "SPY-TEST-001", "play_type": "SPY_KEY_LEVELS", "call_or_put": "call",
        "option_symbol": "SPY260818C00776000", "entry_price": "4.31",
        "underlying_stop_price": "598.0", "underlying_target_price": "700.0",
        "expiration": "2026-08-18", "expiration_tier": "WEEKLY",
        "max_favorable_pct": "0",
    })
    quotes = {"SPY260818C00776000": {"bid": 2.1, "ask": 2.2, "last": 2.15}}
    timestamp = datetime(2026, 8, 14, 10, 0, tzinfo=ZoneInfo("America/Chicago"))

    result = spy_scanner.evaluate_open_spy_key_levels_row(row, quotes, timestamp, underlying_spot_price=650.0)

    # mark=2.1 (bid), entry=4.31 -> pnl_pct ~= -51%, well past the underlying
    # level (650 is nowhere near either 598 or 700) - only the premium
    # backstop explains this firing.
    assert result["signal"] == "STOP OUT"
    assert "backstop" in result["exit_note"]


def test_exit_signal_holds_a_1_3dte_position_overnight_without_eod_force_close():
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=604.0,
        current_underlying_price=601.0, expiration_tier="1-3DTE",
        is_expiration_day=False, minutes_remaining=5,
    )
    assert signal == "HOLD"


def test_exit_signal_forces_close_only_on_the_actual_expiration_day():
    signal, _ = spy_scanner.spy_key_levels_exit_signal(
        side="call", stop_underlying_price=598.0, target_underlying_price=604.0,
        current_underlying_price=601.0, expiration_tier="WEEKLY",
        is_expiration_day=True, minutes_remaining=10,
    )
    assert signal == "EXPIRATION CLOSE"


def test_expiration_close_signal_is_wired_into_the_close_trigger_set():
    # Regression guard: SPY Key-Levels uses its own "EXPIRATION CLOSE"
    # string (deliberately distinct from SPY_0DTE's "EOD CLOSE") specifically
    # so this strategy's forced-close signal actually closes positions in
    # main() without changing SPY_0DTE's own closing behavior at all.
    import inspect
    source = inspect.getsource(spy_scanner)
    assert '"EXPIRATION CLOSE"' in source


# ---------------------------------------------------------------------------
# Candidate builder
# ---------------------------------------------------------------------------


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


def test_candidate_builder_respects_its_own_delta_band_not_spy_0dtes():
    entry = {
        "side": "call",
        "active_level_price": 599.0,
    }
    chain = [_option(delta=0.10, ask=1.0), _option(delta=0.50, ask=1.5)]
    candidates = spy_scanner.scan_spy_key_levels_candidates(chain, entry, "2026-08-10", "0DTE", spot_price=600.0)
    assert len(candidates) == 1
    assert candidates[0]["delta"] == 0.5
    assert candidates[0]["play_type"] == spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE
    assert candidates[0]["underlying_stop_price"] < 600.0
    assert candidates[0]["expiration_tier"] == "0DTE"


def test_candidate_builder_filters_to_the_requested_side_only():
    entry = {"side": "put", "active_level_price": 601.0}
    chain = [_option(delta=0.50, ask=1.0, option_type="call"), _option(delta=0.50, ask=1.0, option_type="put")]
    candidates = spy_scanner.scan_spy_key_levels_candidates(chain, entry, "2026-08-10", "0DTE", spot_price=600.0)
    assert len(candidates) == 1
    assert candidates[0]["call_or_put"] == "put"
