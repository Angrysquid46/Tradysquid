"""Tests for the standalone SPY 0DTE plan - built entirely separate from
regular/swing/spread per explicit owner direction, so these tests exist
specifically to confirm it doesn't quietly borrow the old system's
constants (delta bands, contract caps, stop/target) anywhere.
"""

from __future__ import annotations

import ford_scan


def _bar(price: float, high: float | None = None, low: float | None = None, volume: float = 100_000) -> dict:
    return {
        "close": price,
        "high": high if high is not None else price,
        "low": low if low is not None else price,
        "volume": volume,
    }


def _opening_range_bars(range_low: float = 600.0, range_high: float = 602.0) -> list[dict]:
    # 6 bars = 30 minutes at 5min/bar, alternating between the range edges.
    return [
        _bar(600.5, high=601.0, low=600.0),
        _bar(601.5, high=602.0, low=601.0),
        _bar(600.8, high=601.2, low=600.5),
        _bar(601.2, high=601.8, low=600.8),
        _bar(600.3, high=600.9, low=600.0),
        _bar(601.7, high=602.0, low=601.2),
    ]


def _option(delta: float, ask: float, bid: float | None = None, strike: float = 600.0) -> dict:
    return {
        "strike": strike,
        "option_type": "call",
        "bid": bid if bid is not None else max(ask - 0.05, 0.01),
        "ask": ask,
        "open_interest": 500,
        "volume": 200,
        "greeks": {"delta": delta, "theta": -0.3},
    }


def test_opening_range_signal_does_not_qualify_before_the_range_is_established():
    context = ford_scan.spy_0dte_opening_range_signal(_opening_range_bars()[:3])
    assert context["qualified"] is False


def test_opening_range_signal_does_not_qualify_while_still_inside_the_range():
    bars = _opening_range_bars() + [_bar(601.5)]
    context = ford_scan.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is False
    assert "inside the opening range" in context["reason"]


def test_opening_range_signal_fires_bullish_on_a_real_breakout_above():
    bars = _opening_range_bars() + [_bar(602.5)]
    context = ford_scan.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is True
    assert context["regime"] == "BULLISH / CONTROLLED"
    assert "broke above" in context["reason"]


def test_opening_range_signal_fires_bearish_on_a_real_breakdown_below():
    bars = _opening_range_bars() + [_bar(599.0)]
    context = ford_scan.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is True
    assert context["regime"] == "BEARISH / CONTROLLED"
    assert "broke below" in context["reason"]


def test_opening_range_signal_only_fires_on_the_first_bar_that_breaks_out():
    # A second, further breakout bar must not change which bar the
    # signal reports - it fires once per session, at the first breach.
    bars = _opening_range_bars() + [_bar(602.5), _bar(603.5)]
    context = ford_scan.spy_0dte_opening_range_signal(bars)
    assert context["breakout_price"] == 602.5


def test_exit_signal_stops_out_at_the_spy_0dte_specific_threshold():
    entry = 2.00
    stop_mark = entry * (1 - ford_scan.SPY_0DTE_STOP_PCT) - 0.01
    signal, note = ford_scan.spy_0dte_exit_signal(entry, stop_mark, minutes_remaining=200)
    assert signal == "STOP OUT"


def test_exit_signal_takes_profit_at_the_spy_0dte_specific_threshold():
    entry = 2.00
    target_mark = entry * (1 + ford_scan.SPY_0DTE_TARGET_PCT) + 0.01
    signal, note = ford_scan.spy_0dte_exit_signal(entry, target_mark, minutes_remaining=200)
    assert signal == "TAKE PROFIT"


def test_exit_signal_holds_between_stop_and_target_with_time_left():
    signal, note = ford_scan.spy_0dte_exit_signal(2.00, 2.10, minutes_remaining=200)
    assert signal == "HOLD"


def test_exit_signal_full_stop_still_applies_before_the_trade_has_proven_itself():
    # peak_pct never crossed the floor trigger - the full -50% stop is
    # still what governs, not the raised floor.
    entry = 2.00
    stop_mark = entry * (1 - ford_scan.SPY_0DTE_STOP_PCT) - 0.01
    signal, note = ford_scan.spy_0dte_exit_signal(entry, stop_mark, minutes_remaining=200, peak_pct=10.0)
    assert signal == "STOP OUT"


def test_exit_signal_raises_the_floor_once_a_trade_has_proven_itself():
    # Peaked well past the trigger, then pulled back to the floor level -
    # protects the proven move instead of risking the full round-trip.
    entry = 2.00
    peak = ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT + 10
    floor_mark = entry * (1 + ford_scan.SPY_0DTE_FLOOR_PCT / 100) - 0.01
    signal, note = ford_scan.spy_0dte_exit_signal(entry, floor_mark, minutes_remaining=200, peak_pct=peak)
    assert signal == "BREAKEVEN STOP"
    assert "peaked" in note


def test_exit_signal_does_not_fire_the_floor_on_a_pullback_that_stays_above_it():
    # Proven trade, dipped some, but still well above the raised floor -
    # must hold, not exit on ordinary noise.
    entry = 2.00
    peak = ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT + 10
    mark_above_floor = entry * (1 + (ford_scan.SPY_0DTE_FLOOR_PCT + 5) / 100)
    signal, note = ford_scan.spy_0dte_exit_signal(entry, mark_above_floor, minutes_remaining=200, peak_pct=peak)
    assert signal == "HOLD"


def test_exit_signal_floor_never_raises_below_its_own_default_stop():
    # Sanity check on the constants themselves: the floor is meant to be
    # a smaller loss than the full stop, not a wider one.
    assert ford_scan.SPY_0DTE_FLOOR_PCT > -ford_scan.SPY_0DTE_STOP_PCT * 100


def test_exit_signal_forces_a_close_as_the_session_ends_even_at_flat_pnl():
    # 0DTE never holds overnight - there is no next session to trail into.
    signal, note = ford_scan.spy_0dte_exit_signal(2.00, 2.02, minutes_remaining=10)
    assert signal == "EOD CLOSE"


def test_candidate_builder_rejects_a_delta_outside_its_own_band():
    chain = [_option(delta=0.20, ask=1.00)]  # below SPY_0DTE_DELTA_MIN
    assert ford_scan.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0) == []


def test_candidate_builder_accepts_a_contract_priced_above_the_shared_system_cap():
    # $2.00 > the OTHER play types' MAX_CONTRACT_ASK ($1.00) but well
    # under SPY_0DTE_MAX_CONTRACT_ASK - proves this reads its own cap,
    # not the borrowed one.
    assert ford_scan.MAX_CONTRACT_ASK < 2.00 < ford_scan.SPY_0DTE_MAX_CONTRACT_ASK
    chain = [_option(delta=0.50, ask=2.00)]
    candidates = ford_scan.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0)
    assert len(candidates) == 1
    assert candidates[0]["play_type"] == "SPY_0DTE"


def test_candidate_builder_rejects_a_contract_over_its_own_risk_cap():
    ask = ford_scan.SPY_0DTE_MAX_CONTRACT_ASK + 1.00
    chain = [_option(delta=0.50, ask=ask)]
    assert ford_scan.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0) == []


def test_spy_0dte_defaults_paused_when_config_is_silent():
    # The code-level fallback (not the live config, which this session
    # intentionally flips on) must still default to paused - a missing
    # config key must never silently enable a leveraged, single-regime-
    # backtested play type.
    assert ford_scan.DEFAULT_TRADE_TYPES_ENABLED["spy_0dte"] is False


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({
        "trade_id": "T-1", "ticker": "SPY", "outcome": "OPEN",
        "play_type": "SPY_0DTE", "call_or_put": "call",
        "entry_price": "2.00", "option_symbol": "SPY260810C00600000",
        "expiration": ford_scan.now_ct().date().isoformat(),
    })
    row.update(overrides)
    return row


def test_evaluate_open_row_stops_out_a_spy_0dte_position():
    quote = {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": 0.98, "ask": 1.02,
            "greeks": {"delta": 0.45, "mid_iv": 0.20, "theta": -0.4},
        }
    }
    evaluation = ford_scan.evaluate_open_row(_row(), quote, ford_scan.now_ct())
    assert evaluation["signal"] == "STOP OUT"


def test_evaluate_open_row_closes_a_spy_0dte_position_near_session_end():
    quote = {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": 1.98, "ask": 2.02,
            "greeks": {"delta": 0.50, "mid_iv": 0.20, "theta": -0.4},
        }
    }
    close_ish = ford_scan.now_ct().replace(hour=14, minute=50, second=0, microsecond=0)
    evaluation = ford_scan.evaluate_open_row(_row(), quote, close_ish)
    assert evaluation["signal"] == "EOD CLOSE"


def test_evaluate_open_row_raises_the_floor_after_a_spy_0dte_position_has_proven_itself():
    # Already peaked well past the floor trigger (tracked in
    # max_favorable_pct, same field every other play type uses), now
    # pulled back to the floor level - must protect the proven move
    # instead of riding it all the way to the full -50% stop.
    quote = {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": 1.60, "ask": 1.65,
            "greeks": {"delta": 0.55, "mid_iv": 0.20, "theta": -0.4},
        }
    }
    row = _row(max_favorable_pct=str(ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT + 10))
    evaluation = ford_scan.evaluate_open_row(row, quote, ford_scan.now_ct())
    assert evaluation["signal"] == "BREAKEVEN STOP"
