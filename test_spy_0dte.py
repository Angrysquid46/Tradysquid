"""Tests for the standalone SPY 0DTE plan - built entirely separate from
regular/swing/spread per explicit owner direction, so these tests exist
specifically to confirm it doesn't quietly borrow the old system's
constants (delta bands, contract caps, stop/target) anywhere.

SPY 0DTE is split into two independently-tracked, independently-live-traded
strategies - SPY_0DTE_1M and SPY_0DTE_5M. SPY_0DTE_1M's entry signal is a
live TradingView alert (spy_0dte_tradingview_signal) - the strategy this
system's TradingView webhook was actually built to drive, tied to the Pine
indicator behind the 66.8% backtest. SPY_0DTE_5M keeps the Python
opening-range breakout (spy_0dte_opening_range_signal). Contract selection,
delta band, risk cap, and stop/target/floor/EOD exit rules are identical and
shared between both regardless of entry-signal source. Several tests below
exist specifically to prove the two variants stay isolated from each other
(own cooldown, own exposure accounting, own play_type tag) rather than
silently sharing state, since "both trade fully independently" was an
explicit owner decision, not an incidental default.
"""

from __future__ import annotations

from unittest import mock

import pytest
from unittest import mock

import dynamic_universe
import spy_scanner

# SPY_0DTE_1M and SPY_0DTE_5M were retired 2026-08-17 (see
# spy_scanner.SPY_0DTE_PLAY_TYPES), so the live tuple holds only
# SPY_MANUAL. spy_0dte_exit_signal and its evaluate_open_row dispatch are
# still in the codebase and still matter - restoring a variant is a
# one-line change - so the exit-logic tests below inject the retired play
# types explicitly rather than silently passing against a tuple that no
# longer contains them.
RETIRED_0DTE_PLAY_TYPES = ("SPY_0DTE_1M", "SPY_0DTE_5M", spy_scanner.SPY_MANUAL_PLAY_TYPE)


@pytest.fixture(autouse=True)
def _restore_retired_0dte_play_types():
    with mock.patch.object(spy_scanner, "SPY_0DTE_PLAY_TYPES", RETIRED_0DTE_PLAY_TYPES):
        yield


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
    context = spy_scanner.spy_0dte_opening_range_signal(_opening_range_bars()[:3])
    assert context["qualified"] is False


def test_opening_range_signal_does_not_qualify_while_still_inside_the_range():
    bars = _opening_range_bars() + [_bar(601.5)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is False
    assert "inside the opening range" in context["reason"]


def test_opening_range_signal_fires_bullish_on_a_real_breakout_above():
    bars = _opening_range_bars() + [_bar(602.5)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is True
    assert context["regime"] == "BULLISH / CONTROLLED"
    assert "above" in context["reason"]


def test_opening_range_signal_fires_bearish_on_a_real_breakdown_below():
    bars = _opening_range_bars() + [_bar(599.0)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is True
    assert context["regime"] == "BEARISH / CONTROLLED"
    assert "below" in context["reason"]


def test_opening_range_signal_reflects_the_latest_bar_not_a_stale_first_breakout():
    """Regression guard for a real, severe bug: this used to lock onto
    the FIRST bar that ever broke the opening range and report that
    direction for the rest of the session regardless of what price did
    afterward. Confirmed live 2026-08-14: SPY poked briefly above its
    opening range, then reversed into a real bearish trend well below
    even the range low - the signal kept saying BULLISH all morning off
    that stale early poke, and 5 straight CALL entries opened into it
    and stopped out. A later bar must be able to override an earlier
    one, including flipping the regime entirely on a real reversal."""
    bars = _opening_range_bars() + [_bar(602.5), _bar(603.5)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars)
    assert context["breakout_price"] == 603.5  # the latest bar, not the first breakout

    reversal_bars = _opening_range_bars() + [_bar(602.5), _bar(598.0)]
    reversed_context = spy_scanner.spy_0dte_opening_range_signal(reversal_bars)
    assert reversed_context["regime"] == "BEARISH / CONTROLLED"
    assert reversed_context["breakout_price"] == 598.0


def test_opening_range_signal_returns_to_no_trade_once_price_re_enters_the_range():
    bars = _opening_range_bars() + [_bar(602.5), _bar(601.0)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars)
    assert context["qualified"] is False
    assert "inside the opening range" in context["reason"]


def test_opening_range_signal_scales_bars_needed_to_a_1_minute_interval():
    # SPY_0DTE_1M reads 1-minute bars, not the 5-minute default - bars_needed
    # has to scale with bar_minutes or a 1-minute feed would lock in a range
    # from only the first 6 minutes instead of the real 30-minute window.
    thirty_one_minute_bars = [_bar(600.0 + (i % 3) * 0.2) for i in range(30)]
    context_too_few = spy_scanner.spy_0dte_opening_range_signal(
        thirty_one_minute_bars[:29], bar_minutes=1
    )
    assert context_too_few["qualified"] is False

    bars = thirty_one_minute_bars + [_bar(602.5)]
    context = spy_scanner.spy_0dte_opening_range_signal(bars, bar_minutes=1)
    assert context["qualified"] is True
    assert context["regime"] == "BULLISH / CONTROLLED"


def test_opening_range_signal_5m_and_1m_can_disagree_on_the_same_session():
    # The whole point of tracking both variants separately: they can read
    # the same underlying session differently because they sample it at
    # different granularity. A 5-minute bar can show the range still holding
    # while the finer 1-minute data underneath it has already broken out.
    five_min_bars = _opening_range_bars() + [_bar(601.5)]  # stays inside
    one_min_bars = [_bar(600.0 + (i % 3) * 0.2) for i in range(30)] + [_bar(602.5)]  # breaks out
    context_5m = spy_scanner.spy_0dte_opening_range_signal(five_min_bars, bar_minutes=5)
    context_1m = spy_scanner.spy_0dte_opening_range_signal(one_min_bars, bar_minutes=1)
    assert context_5m["qualified"] is False
    assert context_1m["qualified"] is True


def test_exit_signal_stops_out_at_the_spy_0dte_specific_threshold():
    entry = 2.00
    stop_mark = entry * (1 - spy_scanner.SPY_0DTE_STOP_PCT) - 0.01
    signal, note = spy_scanner.spy_0dte_exit_signal(entry, stop_mark, minutes_remaining=200)
    assert signal == "STOP OUT"


def test_exit_signal_takes_profit_at_the_spy_0dte_specific_threshold():
    entry = 2.00
    target_mark = entry * (1 + spy_scanner.SPY_0DTE_TARGET_PCT) + 0.01
    signal, note = spy_scanner.spy_0dte_exit_signal(entry, target_mark, minutes_remaining=200)
    assert signal == "TAKE PROFIT"


def test_exit_signal_holds_between_stop_and_target_with_time_left():
    signal, note = spy_scanner.spy_0dte_exit_signal(2.00, 2.10, minutes_remaining=200)
    assert signal == "HOLD"


def test_exit_signal_full_stop_still_applies_before_the_trade_has_proven_itself():
    # peak_pct never crossed the floor trigger - the full -50% stop is
    # still what governs, not the raised floor.
    entry = 2.00
    stop_mark = entry * (1 - spy_scanner.SPY_0DTE_STOP_PCT) - 0.01
    signal, note = spy_scanner.spy_0dte_exit_signal(entry, stop_mark, minutes_remaining=200, peak_pct=10.0)
    assert signal == "STOP OUT"


def test_exit_signal_raises_the_floor_once_a_trade_has_proven_itself():
    # Peaked well past the trigger, then pulled back to the floor level -
    # protects the proven move instead of risking the full round-trip.
    entry = 2.00
    peak = spy_scanner.SPY_0DTE_FLOOR_TRIGGER_PCT + 10
    floor_mark = entry * (1 + spy_scanner.SPY_0DTE_FLOOR_PCT / 100) - 0.01
    signal, note = spy_scanner.spy_0dte_exit_signal(entry, floor_mark, minutes_remaining=200, peak_pct=peak)
    assert signal == "BREAKEVEN STOP"
    assert "peaked" in note


def test_exit_signal_does_not_fire_the_floor_on_a_pullback_that_stays_above_it():
    # Proven trade, dipped some, but still well above the raised floor -
    # must hold, not exit on ordinary noise.
    entry = 2.00
    peak = spy_scanner.SPY_0DTE_FLOOR_TRIGGER_PCT + 10
    mark_above_floor = entry * (1 + (spy_scanner.SPY_0DTE_FLOOR_PCT + 5) / 100)
    signal, note = spy_scanner.spy_0dte_exit_signal(entry, mark_above_floor, minutes_remaining=200, peak_pct=peak)
    assert signal == "HOLD"


def test_exit_signal_floor_never_raises_below_its_own_default_stop():
    # Sanity check on the constants themselves: the floor is meant to be
    # a smaller loss than the full stop, not a wider one.
    assert spy_scanner.SPY_0DTE_FLOOR_PCT > -spy_scanner.SPY_0DTE_STOP_PCT * 100


def test_exit_signal_forces_a_close_as_the_session_ends_even_at_flat_pnl():
    # 0DTE never holds overnight - there is no next session to trail into.
    signal, note = spy_scanner.spy_0dte_exit_signal(2.00, 2.02, minutes_remaining=10)
    assert signal == "EOD CLOSE"


def test_candidate_builder_rejects_a_delta_outside_its_own_band():
    chain = [_option(delta=0.20, ask=1.00)]  # below SPY_0DTE_DELTA_MIN
    assert spy_scanner.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0) == []


def test_candidate_builder_accepts_a_contract_priced_well_under_its_own_cap():
    # $2.00 is well under SPY_0DTE_MAX_CONTRACT_ASK - proves ordinary
    # contract prices clear the real, standalone cap this play type uses.
    assert 2.00 < spy_scanner.SPY_0DTE_MAX_CONTRACT_ASK
    chain = [_option(delta=0.50, ask=2.00)]
    candidates = spy_scanner.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0)
    assert len(candidates) == 1
    # Defaults to the 5-minute variant when play_type isn't specified,
    # matching the original single-strategy behavior this builder started as.
    assert candidates[0]["play_type"] == "SPY_0DTE_5M"


def test_candidate_builder_tags_each_variant_with_its_own_play_type():
    # The candidate builder itself is shared - same delta band, same risk
    # cap, same contract selection - for both variants. play_type is the
    # ONE thing that must differ, since it's what keeps their cooldowns,
    # exposure accounting, and learning evidence from mixing together.
    chain = [_option(delta=0.50, ask=2.00)]
    candidates_1m = spy_scanner.scan_spy_0dte_candidates(
        chain, "call", "2026-08-10", 600.0, play_type="SPY_0DTE_1M"
    )
    candidates_5m = spy_scanner.scan_spy_0dte_candidates(
        chain, "call", "2026-08-10", 600.0, play_type="SPY_0DTE_5M"
    )
    assert candidates_1m[0]["play_type"] == "SPY_0DTE_1M"
    assert candidates_5m[0]["play_type"] == "SPY_0DTE_5M"
    # Everything else about the two candidates is identical - only the tag differs.
    for key in candidates_1m[0]:
        if key == "play_type":
            continue
        assert candidates_1m[0][key] == candidates_5m[0][key]


def test_candidate_builder_rejects_a_contract_over_its_own_risk_cap():
    ask = spy_scanner.SPY_0DTE_MAX_CONTRACT_ASK + 1.00
    chain = [_option(delta=0.50, ask=ask)]
    assert spy_scanner.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0) == []


def test_candidate_builder_carries_the_tradingview_event_id_through():
    """Needed so a candidate that becomes a real row can tell main()'s
    open loop which alert to mark consumed (_mark_tradingview_event_if_opened) -
    without this, there'd be no way to know, at the point a row is
    actually created, which TradingView alert it came from."""
    chain = [_option(delta=0.50, ask=2.00)]
    context = {"regime": "BULLISH / CONTROLLED", "reason": "buy alert", "tradingview_event_id": 42}
    candidates = spy_scanner.scan_spy_0dte_candidates(
        chain, "call", "2026-08-10", 600.0, market_context=context, play_type="SPY_0DTE_1M"
    )
    assert candidates[0]["tradingview_event_id"] == 42


def test_candidate_builder_leaves_tradingview_event_id_none_without_a_market_context():
    chain = [_option(delta=0.50, ask=2.00)]
    candidates = spy_scanner.scan_spy_0dte_candidates(chain, "call", "2026-08-10", 600.0)
    assert candidates[0]["tradingview_event_id"] is None


def test_candidate_survives_candidate_to_row_without_a_keyerror():
    # candidate_to_row reads cost_or_credit/pop/max_profit/max_risk/
    # breakeven/option_symbol directly off every candidate regardless of
    # play_type - a real bug let scan_spy_0dte_candidates ship without
    # several of them, which would only surface as a crash the moment a
    # real SPY 0DTE trade actually tried to open, not in any report.
    chain = [_option(delta=0.50, ask=1.20, strike=600.0)]
    candidates = spy_scanner.scan_spy_0dte_candidates(
        chain, "call", "2026-08-10", 600.0,
        market_context={"reason": "broke above the opening range at $601.50", "regime": "BULLISH / CONTROLLED"},
    )
    assert len(candidates) == 1
    original_ticker = spy_scanner.TICKER
    spy_scanner.TICKER = "SPY"
    try:
        row = spy_scanner.candidate_to_row(candidates[0], [], spy_scanner.now_ct())
    finally:
        spy_scanner.TICKER = original_ticker
    assert row["play_type"] == "SPY_0DTE_5M"
    assert row["ticker"] == "SPY"
    assert row["cost_or_credit"] == "1.2"
    assert row["max_risk"] == "120.0"
    assert "opening range" in row["setup_reason"]
    assert "BULLISH" in row["market_regime"]


def test_spy_0dte_defaults_paused_when_config_is_silent():
    # The code-level fallback (not the live config, which this session
    # intentionally flips on) must still default to paused - a missing
    # config key must never silently enable a leveraged, single-regime-
    # backtested play type, for EITHER variant.
    assert spy_scanner.DEFAULT_TRADE_TYPES_ENABLED["spy_0dte_1m"] is False
    assert spy_scanner.DEFAULT_TRADE_TYPES_ENABLED["spy_0dte_5m"] is False


def test_no_scanner_driven_0dte_variant_is_live_any_more():
    """The retirement itself. SPY_MANUAL must stay - it is the play type an
    owner-opened position carries, not a scanner strategy, so dropping it
    would strand a manual trade with no exit evaluator."""
    import importlib
    module = importlib.reload(spy_scanner)
    try:
        assert module.SPY_0DTE_PLAY_TYPES == (module.SPY_MANUAL_PLAY_TYPE,)
        assert module.is_spy_0dte_play_type("SPY_0DTE_1M") is False
        assert module.is_spy_0dte_play_type("SPY_0DTE_5M") is False
        assert module.is_spy_0dte_play_type(module.SPY_MANUAL_PLAY_TYPE) is True
    finally:
        importlib.reload(module)


def test_is_spy_0dte_play_type_recognizes_both_variants_and_nothing_else():
    assert spy_scanner.is_spy_0dte_play_type("SPY_0DTE_1M") is True
    assert spy_scanner.is_spy_0dte_play_type("SPY_0DTE_5M") is True
    # The bare pre-split string is now retired, not a live variant.
    assert spy_scanner.is_spy_0dte_play_type("SPY_0DTE") is False
    assert spy_scanner.is_spy_0dte_play_type("REGULAR") is False
    assert spy_scanner.is_spy_0dte_play_type(None) is False


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": "T-1", "ticker": "SPY", "outcome": "OPEN",
        "play_type": "SPY_0DTE_1M", "call_or_put": "call",
        "entry_price": "2.00", "option_symbol": "SPY260810C00600000",
        "expiration": spy_scanner.now_ct().date().isoformat(),
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
    evaluation = spy_scanner.evaluate_open_row(_row(), quote, spy_scanner.now_ct())
    assert evaluation["signal"] == "STOP OUT"


def test_evaluate_open_row_closes_a_spy_0dte_position_near_session_end():
    quote = {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": 1.98, "ask": 2.02,
            "greeks": {"delta": 0.50, "mid_iv": 0.20, "theta": -0.4},
        }
    }
    close_ish = spy_scanner.now_ct().replace(hour=14, minute=50, second=0, microsecond=0)
    evaluation = spy_scanner.evaluate_open_row(_row(), quote, close_ish)
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
    row = _row(max_favorable_pct=str(spy_scanner.SPY_0DTE_FLOOR_TRIGGER_PCT + 10))
    evaluation = spy_scanner.evaluate_open_row(row, quote, spy_scanner.now_ct())
    assert evaluation["signal"] == "BREAKEVEN STOP"


def test_evaluate_open_row_treats_the_5m_variant_identically_to_the_1m_variant():
    # Same exit rules for both - only entry-signal bar interval differs
    # between the two variants, never the exit management.
    quote = {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": 0.98, "ask": 1.02,
            "greeks": {"delta": 0.45, "mid_iv": 0.20, "theta": -0.4},
        }
    }
    row = _row(play_type="SPY_0DTE_5M")
    evaluation = spy_scanner.evaluate_open_row(row, quote, spy_scanner.now_ct())
    assert evaluation["signal"] == "STOP OUT"


def test_evaluate_open_row_no_longer_recognizes_the_pre_split_play_type():
    # The bare "SPY_0DTE" string (before the 1m/5m split) is now a retired
    # play_type, same as any other historical row from a dropped strategy -
    # it must not silently keep evaluating against live exit rules.
    row = _row(play_type="SPY_0DTE")
    evaluation = spy_scanner.evaluate_open_row(row, {}, spy_scanner.now_ct())
    assert evaluation["signal"] == "HOLD"
    assert "Unrecognized or retired play_type" in evaluation["note"]


def test_recently_tracked_cooldown_does_not_cross_contaminate_the_two_variants():
    # A cooldown on the 1-minute variant's exact contract must never block
    # the 5-minute variant from opening the same contract - they trade
    # fully independently by owner decision, and play_type is what keeps
    # their cooldowns from bleeding into each other. recently_tracked keys
    # on the module-level TICKER, not row["ticker"], so the fixture row has
    # to match whatever TICKER actually is in this test process.
    now = spy_scanner.now_ct()
    existing_open_1m = _row(
        ticker=spy_scanner.TICKER, play_type="SPY_0DTE_1M", strike="600", expiration="2026-08-10"
    )
    rows = [existing_open_1m]
    candidate_5m = {
        "play_type": "SPY_0DTE_5M", "call_or_put": "call",
        "strike": "600", "expiration": "2026-08-10",
    }
    candidate_1m = {
        "play_type": "SPY_0DTE_1M", "call_or_put": "call",
        "strike": "600", "expiration": "2026-08-10",
    }
    assert spy_scanner.recently_tracked(rows, candidate_5m, now) is False
    assert spy_scanner.recently_tracked(rows, candidate_1m, now) is True


def _tradingview_event(event_type: str, event_id: int = 1, payload: dict | None = None, received_at: str | None = None) -> dict:
    return {
        "id": event_id,
        "event_type": event_type,
        "received_at": received_at or spy_scanner.datetime.now().astimezone().isoformat(timespec="seconds"),
        "payload": payload or {},
    }


def test_tradingview_direction_recognizes_common_buy_conventions():
    for event_type in ("buy", "BUY", "long", "Call"):
        assert spy_scanner.spy_0dte_tradingview_direction(_tradingview_event(event_type)) == "BULLISH"


def test_tradingview_direction_recognizes_common_sell_conventions():
    for event_type in ("sell", "SELL", "short", "Put"):
        assert spy_scanner.spy_0dte_tradingview_direction(_tradingview_event(event_type)) == "BEARISH"


def test_tradingview_direction_falls_back_to_payload_action_field():
    event = _tradingview_event("alert", payload={"action": "buy", "price": 774.5})
    assert spy_scanner.spy_0dte_tradingview_direction(event) == "BULLISH"


def test_tradingview_direction_falls_back_to_json_encoded_payload():
    import json
    event = _tradingview_event("alert", payload=json.dumps({"strategy_action": "sell"}))
    assert spy_scanner.spy_0dte_tradingview_direction(event) == "BEARISH"


def test_tradingview_direction_returns_none_when_unrecognized():
    assert spy_scanner.spy_0dte_tradingview_direction(_tradingview_event("breakout")) is None


def test_tradingview_direction_returns_none_when_both_sides_mentioned():
    # A message like "buy/sell zone" that mentions both conventions is
    # genuinely ambiguous - must not guess a direction from it.
    assert spy_scanner.spy_0dte_tradingview_direction(_tradingview_event("buy or sell")) is None


















def test_consumed_event_tracking_round_trips_through_the_state_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        original = spy_scanner.SPY_TRADINGVIEW_CONSUMED_EVENT_PATH
        spy_scanner.SPY_TRADINGVIEW_CONSUMED_EVENT_PATH = Path(tmp) / "consumed.json"
        try:
            assert spy_scanner._tradingview_event_already_consumed("SPY_0DTE_1M", 55) is False
            spy_scanner._tradingview_event_mark_consumed("SPY_0DTE_1M", 55)
            assert spy_scanner._tradingview_event_already_consumed("SPY_0DTE_1M", 55) is True
            assert spy_scanner._tradingview_event_already_consumed("SPY_0DTE_1M", 56) is False
            # A different play_type must not see the first one's consumption.
            assert spy_scanner._tradingview_event_already_consumed("SPY_RATCHET_26_16", 55) is False
        finally:
            spy_scanner.SPY_TRADINGVIEW_CONSUMED_EVENT_PATH = original


def test_mark_tradingview_event_if_opened_marks_consumed_when_present():
    with mock.patch.object(spy_scanner, "_tradingview_event_mark_consumed") as fake_mark:
        spy_scanner._mark_tradingview_event_if_opened(
            {"play_type": "SPY_0DTE_1M", "tradingview_event_id": 77}
        )
    fake_mark.assert_called_once_with("SPY_0DTE_1M", 77)


def test_mark_tradingview_event_if_opened_does_nothing_for_a_non_tradingview_candidate():
    # SPY_0DTE_5M/Key-Levels/Expansion-Level candidates never carry a
    # tradingview_event_id (see the candidate builder's None default) -
    # this must be a clean no-op for them, not a KeyError or a spurious mark.
    with mock.patch.object(spy_scanner, "_tradingview_event_mark_consumed") as fake_mark:
        spy_scanner._mark_tradingview_event_if_opened(
            {"play_type": "SPY_0DTE_5M", "tradingview_event_id": None}
        )
    fake_mark.assert_not_called()






def test_recent_tradingview_signal_reads_without_claiming_the_event():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dynamic-universe-test.db"
        connection = dynamic_universe.connect(db_path)
        try:
            dynamic_universe.enqueue_event(
                "tradingview", "buy", "SPY", {"action": "buy"}, connection=connection
            )
            found = dynamic_universe.recent_tradingview_signal("SPY", 3600, connection=connection)
            assert found is not None
            assert found["event_type"] == "buy"
            # Still PENDING - a read-only lookup must not claim/consume the
            # row, since the existing provider-event-queue job owns that
            # lifecycle for posting the Discord research card.
            assert found["status"] == "PENDING"
            row = connection.execute(
                "SELECT status FROM provider_events WHERE id=?", (found["id"],)
            ).fetchone()
            assert row["status"] == "PENDING"
        finally:
            connection.close()


def test_recent_tradingview_signal_ignores_events_outside_the_freshness_window():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dynamic-universe-test.db"
        connection = dynamic_universe.connect(db_path)
        try:
            stale_time = (spy_scanner.datetime.now().astimezone() - spy_scanner.timedelta(hours=1)).isoformat(timespec="seconds")
            connection.execute(
                """
                INSERT INTO provider_events(event_key, provider, event_type, symbol, priority, received_at, available_at, payload_json)
                VALUES ('stale-key', 'tradingview', 'buy', 'SPY', 0, ?, ?, '{}')
                """,
                (stale_time, stale_time),
            )
            connection.commit()
            found = dynamic_universe.recent_tradingview_signal("SPY", 180, connection=connection)
            assert found is None
        finally:
            connection.close()


def test_recent_tradingview_signal_ignores_a_different_symbol():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dynamic-universe-test.db"
        connection = dynamic_universe.connect(db_path)
        try:
            dynamic_universe.enqueue_event(
                "tradingview", "buy", "QQQ", {"action": "buy"}, connection=connection
            )
            found = dynamic_universe.recent_tradingview_signal("SPY", 3600, connection=connection)
            assert found is None
        finally:
            connection.close()
