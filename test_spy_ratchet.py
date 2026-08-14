"""Tests for the 10 ratchet-floor SPY strategies (SPY_RATCHET_*).

Each variant reuses SPY_0DTE's entry signal (spy_0dte_opening_range_signal,
1-minute bars) and contract selection (scan_spy_0dte_candidates) as-is - no
new code there. What's genuinely new is the exit shape: no fixed take-profit
target, a floor that locks in profit every step_pct once peak gain first
crosses it and ratchets up every further step, with stop_pct only applying
before the first step ever fires. One shared exit function
(spy_ratchet_exit_signal) serves all 10 variants, each fed its own
(step_pct, stop_pct) from SPY_RATCHET_VARIANTS - several tests below exist
specifically to prove each variant's own numbers are actually used, not a
shared/leaked value from whichever variant ran first.

Picked from a 1,680-combo backtest against real Tradier 1-minute SPY history
(2026-08-10) - the 10 best-performing, non-degenerate (step, stop) pairs.
See spy_scanner.py's SPY_RATCHET_VARIANTS docstring/comment for the full
context.
"""

from __future__ import annotations

import spy_scanner


def test_variant_table_has_exactly_ten_entries_each_uniquely_named():
    assert len(spy_scanner.SPY_RATCHET_VARIANTS) == 10
    play_types = [variant["play_type"] for variant in spy_scanner.SPY_RATCHET_VARIANTS]
    assert len(play_types) == len(set(play_types))
    for play_type in play_types:
        assert play_type.startswith("SPY_RATCHET_")


def test_is_spy_ratchet_play_type_recognizes_all_ten_and_nothing_else():
    for variant in spy_scanner.SPY_RATCHET_VARIANTS:
        assert spy_scanner.is_spy_ratchet_play_type(variant["play_type"]) is True
    assert spy_scanner.is_spy_ratchet_play_type("SPY_0DTE_1M") is False
    assert spy_scanner.is_spy_ratchet_play_type("SPY_RATCHET") is False
    assert spy_scanner.is_spy_ratchet_play_type(None) is False


def test_exit_signal_stops_out_before_any_step_ever_fires():
    entry = 2.00
    # -16% stop, peak never reached step_pct (26%), so the base stop governs.
    stop_mark = entry * (1 + (-16.0 - 1.0) / 100)
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        entry, stop_mark, minutes_remaining=200, peak_pct=5.0, step_pct=26.0, stop_pct=-16.0
    )
    assert signal == "STOP OUT"
    assert "before any step fired" in note


def test_exit_signal_holds_between_stop_and_first_step_with_time_left():
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        2.00, 2.05, minutes_remaining=200, peak_pct=5.0, step_pct=26.0, stop_pct=-16.0
    )
    assert signal == "HOLD"


def test_exit_signal_locks_the_floor_exactly_at_the_step_once_crossed():
    entry = 2.00
    step_pct, stop_pct = 26.0, -16.0
    peak = 27.0  # just past the first step
    # Pull back to exactly the locked floor (26%).
    floor_mark = entry * (1 + step_pct / 100)
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        entry, floor_mark, minutes_remaining=200, peak_pct=peak, step_pct=step_pct, stop_pct=stop_pct
    )
    assert signal == "FLOOR STOP"
    assert "26%" in note


def test_exit_signal_ratchets_the_floor_up_on_a_further_step():
    entry = 2.00
    step_pct, stop_pct = 26.0, -16.0
    peak = 55.0  # crossed two steps (26%, 52%)
    below_second_floor = entry * (1 + 51.0 / 100)
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        entry, below_second_floor, minutes_remaining=200, peak_pct=peak, step_pct=step_pct, stop_pct=stop_pct
    )
    assert signal == "FLOOR STOP"
    assert "52%" in note


def test_exit_signal_does_not_fire_on_a_pullback_that_stays_above_the_floor():
    entry = 2.00
    step_pct, stop_pct = 26.0, -16.0
    peak = 55.0
    above_floor = entry * (1 + 53.0 / 100)
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        entry, above_floor, minutes_remaining=200, peak_pct=peak, step_pct=step_pct, stop_pct=stop_pct
    )
    assert signal == "HOLD"


def test_exit_signal_floor_never_applies_before_its_own_step_is_crossed():
    # Peak sits just under the step - the base stop, not any floor, still
    # governs even on a very negative mark.
    entry = 2.00
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        entry, entry * (1 - 0.20), minutes_remaining=200, peak_pct=25.9, step_pct=26.0, stop_pct=-16.0
    )
    assert signal == "STOP OUT"


def test_exit_signal_forces_a_ratchet_specific_close_as_the_session_ends():
    # Distinct from SPY_0DTE's "EOD CLOSE" - see spy_ratchet_exit_signal's
    # docstring for why this needs its own string in main()'s close-trigger set.
    signal, note = spy_scanner.spy_ratchet_exit_signal(
        2.00, 2.02, minutes_remaining=10, peak_pct=5.0, step_pct=26.0, stop_pct=-16.0
    )
    assert signal == "RATCHET EOD CLOSE"


def test_ratchet_eod_close_and_floor_stop_are_in_the_shared_closing_signals_set():
    # CLOSING_SIGNALS is the single source of truth every close-triggering
    # call site (main()'s scan loop, local_information_engine.py's
    # real-time stream handler, and its REST fallback) checks against - a
    # new signal name missing from it would show up on the live card but
    # never actually close the position until the next full scan cycle.
    assert "FLOOR STOP" in spy_scanner.CLOSING_SIGNALS
    assert "RATCHET EOD CLOSE" in spy_scanner.CLOSING_SIGNALS


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": "T-1", "ticker": "SPY", "outcome": "OPEN",
        "play_type": "SPY_RATCHET_26_16", "call_or_put": "call",
        "entry_price": "2.00", "option_symbol": "SPY260810C00600000",
        "expiration": spy_scanner.now_ct().date().isoformat(),
    })
    row.update(overrides)
    return row


def _quote(bid: float, ask: float) -> dict[str, dict]:
    return {
        "SPY260810C00600000": {
            "symbol": "SPY260810C00600000", "bid": bid, "ask": ask,
            "greeks": {"delta": 0.50, "mid_iv": 0.20, "theta": -0.4},
        }
    }


def test_evaluate_open_row_dispatches_a_ratchet_play_type_to_its_own_evaluator():
    quote = _quote(1.62, 1.68)  # -17ish%, below the -16% base stop
    mid_session = spy_scanner.now_ct().replace(hour=11, minute=0, second=0, microsecond=0)
    evaluation = spy_scanner.evaluate_open_row(_row(), quote, mid_session)
    assert evaluation["signal"] == "STOP OUT"


def test_evaluate_open_row_uses_each_variants_own_step_and_stop_not_a_shared_value():
    # SPY_RATCHET_26_16 stops at -16%; SPY_RATCHET_26_36 (same step, very
    # different stop) must NOT stop out at the same mark - proves the row's
    # own play_type actually selects its own numbers from the table rather
    # than leaking whichever variant's constants happened to run first.
    quote = _quote(1.62, 1.68)  # roughly -17%
    mid_session = spy_scanner.now_ct().replace(hour=11, minute=0, second=0, microsecond=0)
    tight_stop_row = _row(play_type="SPY_RATCHET_26_16")
    wide_stop_row = _row(play_type="SPY_RATCHET_26_36")
    tight_eval = spy_scanner.evaluate_open_row(tight_stop_row, quote, mid_session)
    wide_eval = spy_scanner.evaluate_open_row(wide_stop_row, quote, mid_session)
    assert tight_eval["signal"] == "STOP OUT"
    assert wide_eval["signal"] == "HOLD"


def test_evaluate_open_row_locks_the_floor_for_a_ratchet_position():
    row = _row(max_favorable_pct="27")  # already past the 26% step
    floor_quote = _quote(2.51, 2.55)  # ~26-27%, at/near the locked floor
    mid_session = spy_scanner.now_ct().replace(hour=11, minute=0, second=0, microsecond=0)
    evaluation = spy_scanner.evaluate_open_row(row, floor_quote, mid_session)
    assert evaluation["signal"] in ("FLOOR STOP", "HOLD")


def test_evaluate_open_row_closes_a_ratchet_position_near_session_end():
    quote = _quote(1.98, 2.02)
    close_ish = spy_scanner.now_ct().replace(hour=14, minute=50, second=0, microsecond=0)
    evaluation = spy_scanner.evaluate_open_row(_row(), quote, close_ish)
    assert evaluation["signal"] == "RATCHET EOD CLOSE"


def test_evaluate_open_row_still_rejects_a_retired_play_type():
    row = _row(play_type="SPY_0DTE")
    evaluation = spy_scanner.evaluate_open_row(row, {}, spy_scanner.now_ct())
    assert evaluation["signal"] == "HOLD"
    assert "Unrecognized or retired play_type" in evaluation["note"]


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


def test_candidate_builder_tags_a_ratchet_candidate_with_its_own_play_type():
    # scan_spy_0dte_candidates is reused as-is (not duplicated) for every
    # ratchet variant - play_type is the one thing that must differ.
    chain = [_option(delta=0.50, ask=2.00)]
    candidates = spy_scanner.scan_spy_0dte_candidates(
        chain, "call", "2026-08-10", 600.0, play_type="SPY_RATCHET_26_16"
    )
    assert len(candidates) == 1
    assert candidates[0]["play_type"] == "SPY_RATCHET_26_16"


def test_entry_card_title_names_the_ratchet_variant():
    row = _row(play_type="SPY_RATCHET_26_16")
    content = spy_scanner.entry_alert_text(row)
    assert "SPY_RATCHET_26_16 LONG CALL" in content


def test_entry_card_shows_the_ratchet_floor_line_not_a_fixed_target():
    row = _row(play_type="SPY_RATCHET_26_16")
    content = spy_scanner.entry_alert_text(row)
    assert "Ratchet floor" in content
    assert "locks in every 26% gain" in content
    assert "**Target:**" not in content


def test_entry_card_still_shows_a_fixed_target_for_non_ratchet_play_types():
    row = _row(play_type="SPY_0DTE_5M")
    content = spy_scanner.entry_alert_text(row)
    assert "**Target:**" in content
    assert "Ratchet floor" not in content


def test_close_card_overshoot_uses_the_rows_own_ratchet_stop_not_the_legacy_single_leg_stop():
    # The generic close_alert_text overshoot annotation used to fall
    # through to SINGLE_STOP_PCT (the retired 15% stop) for any play_type
    # that wasn't SPY_0DTE - a real bug for ratchet rows specifically,
    # since -16% (SPY_RATCHET_26_16's real stop) is nowhere close to -15%.
    row = _row(play_type="SPY_RATCHET_26_16", outcome="LOSS", pct_gain_loss="-40")
    evaluation = {"signal": "STOP OUT", "pl_pct": -40, "pl_dollars": -80, "mark": 1.20}
    content = spy_scanner.close_alert_text(row, evaluation)
    assert "Stop overshoot" in content
    assert "target -16%" in content


def test_default_trade_types_enabled_pauses_every_ratchet_variant_in_code():
    # Code-level fallback must default to paused for every variant, same
    # rule as every other play type - a missing config key must never
    # silently enable a leveraged, backtest-only play type.
    for variant in spy_scanner.SPY_RATCHET_VARIANTS:
        assert spy_scanner.DEFAULT_TRADE_TYPES_ENABLED[variant["play_type"].lower()] is False


def test_trade_types_enabled_actually_reads_the_config_flag_per_variant():
    # Real bug caught while building this: trade_types_enabled() only
    # applies a configured() override to a key that already exists in
    # DEFAULT_TRADE_TYPES_ENABLED - adding a key only to config/scanner.json
    # without also adding it to DEFAULT_TRADE_TYPES_ENABLED means the
    # config flag is silently ignored and the variant can never trade.
    enabled = spy_scanner.trade_types_enabled()
    for variant in spy_scanner.SPY_RATCHET_VARIANTS:
        assert variant["play_type"].lower() in enabled


def test_run_spy_ratchet_variants_gates_each_variant_independently():
    added_labels = []

    def add_candidates(label, found):
        added_labels.append(label)

    enabled = {variant["play_type"].lower(): False for variant in spy_scanner.SPY_RATCHET_VARIANTS}
    enabled[spy_scanner.SPY_RATCHET_VARIANTS[0]["play_type"].lower()] = True

    original_get_strikes = spy_scanner.get_strikes
    original_filter_strikes = spy_scanner.filter_strikes
    original_get_chain = spy_scanner.get_chain
    original_opening_range_signal = spy_scanner.spy_0dte_opening_range_signal
    spy_scanner.get_strikes = lambda ticker, exp: [600.0]
    spy_scanner.filter_strikes = lambda strikes, spot: strikes
    spy_scanner.get_chain = lambda ticker, exp: [
        {"strike": 600.0, "option_type": "call", "symbol": "SPY260810C00600000",
         "bid": 1.95, "ask": 2.00, "open_interest": 500, "volume": 200,
         "greeks": {"delta": 0.50, "theta": -0.3}}
    ]
    spy_scanner.spy_0dte_opening_range_signal = lambda intraday_history, *, bar_minutes: {
        "qualified": True, "regime": "BULLISH / CONTROLLED", "reason": "test",
    }
    try:
        spy_scanner._run_spy_ratchet_variants(
            today_str="2026-08-10", spot_price=600.0, intraday_1m=[],
            candidates=[], quote_map={}, add_candidates=add_candidates, enabled=enabled,
        )
    finally:
        spy_scanner.get_strikes = original_get_strikes
        spy_scanner.filter_strikes = original_filter_strikes
        spy_scanner.get_chain = original_get_chain
        spy_scanner.spy_0dte_opening_range_signal = original_opening_range_signal

    assert len(added_labels) == 1
    assert spy_scanner.SPY_RATCHET_VARIANTS[0]["play_type"] in added_labels[0]


def test_run_spy_ratchet_variants_computes_the_shared_signal_only_once():
    """The signal is identical for all 10 variants - computing it once
    and reusing it, rather than once per variant, is the whole point of
    the shared-entry design (see the module docstring)."""
    calls = []
    enabled = {variant["play_type"].lower(): True for variant in spy_scanner.SPY_RATCHET_VARIANTS}

    original_get_strikes = spy_scanner.get_strikes
    original_filter_strikes = spy_scanner.filter_strikes
    original_get_chain = spy_scanner.get_chain
    original_opening_range_signal = spy_scanner.spy_0dte_opening_range_signal
    spy_scanner.get_strikes = lambda ticker, exp: [600.0]
    spy_scanner.filter_strikes = lambda strikes, spot: strikes
    spy_scanner.get_chain = lambda ticker, exp: []

    def fake_signal(intraday_history, *, bar_minutes):
        calls.append(bar_minutes)
        return {"qualified": False, "regime": "NO TRADE", "reason": "test"}

    spy_scanner.spy_0dte_opening_range_signal = fake_signal
    try:
        spy_scanner._run_spy_ratchet_variants(
            today_str="2026-08-10", spot_price=600.0, intraday_1m=[],
            candidates=[], quote_map={}, add_candidates=lambda *a: None, enabled=enabled,
        )
    finally:
        spy_scanner.get_strikes = original_get_strikes
        spy_scanner.filter_strikes = original_filter_strikes
        spy_scanner.get_chain = original_get_chain
        spy_scanner.spy_0dte_opening_range_signal = original_opening_range_signal

    assert calls == [1]  # one call, 1-minute bars - not one per variant
