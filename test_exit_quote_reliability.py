"""conservative_option_exit trusted whatever bid a quote returned with no
sanity check on how wide the surrounding spread was - a contract that went
essentially untraded between entry and the next check could hand back a
throwaway bid nobody would actually fill at, and evaluate_open_row would
close the position at that price and call it a real loss. Traced directly
to two live trades: CLF (-77% in 21 minutes on a ~1% adverse underlying
move) and NIO (-98%, exit price $0.01). quote_is_reliable_for_exit gates
that path - an implausibly wide spread now falls back to "quote
unavailable, hold at last tracked values" instead of being acted on."""

from __future__ import annotations

import ford_scan


def _row(**overrides):
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({
        "trade_id": "T-QUOTE-1", "ticker": "F", "play_type": "REGULAR",
        "call_or_put": "put", "entry_price": "0.65",
        "option_symbol": "F260821P00100000",
        "delta_at_entry": "-0.57", "iv_at_entry": "1.21",
        "timestamp": ford_scan.now_ct().isoformat(),
        "expiration": (ford_scan.now_ct().date() + ford_scan.timedelta(days=10)).isoformat(),
        "max_favorable_pct": "0",
        "last_mark": "0.60",
        "current_pl_pct": "-8.0",
        "current_pl_dollars": "-5.0",
    })
    row.update(overrides)
    return row


def test_a_wide_spread_quote_is_treated_as_unreliable():
    # bid=0.15, ask=0.65 on a real fair value well above the bid - the
    # CLF shape exactly: a huge spread around a thin bid.
    quote = {"bid": 0.15, "ask": 0.65, "greeks": {"delta": -0.57}}
    assert ford_scan.quote_is_reliable_for_exit(quote) is False


def test_a_normal_spread_quote_is_reliable():
    quote = {"bid": 0.58, "ask": 0.65, "greeks": {"delta": -0.57}}
    assert ford_scan.quote_is_reliable_for_exit(quote) is True


def test_an_unreliable_quote_never_forces_a_stop_out():
    row = _row()
    quotes = {"F260821P00100000": {"bid": 0.15, "ask": 0.65, "greeks": {"delta": -0.57}}}
    evaluation = ford_scan.evaluate_open_row(row, quotes, ford_scan.now_ct())
    assert evaluation["signal"] == "HOLD"
    assert evaluation["note"] == "Live option quote unavailable; showing last tracked values."
    # Must fall back to the last KNOWN good tracked values, not a number
    # derived from the untrustworthy quote.
    assert evaluation["mark"] == 0.60
    assert evaluation["pl_pct"] == -8.0


def test_a_reliable_quote_still_evaluates_normally():
    row = _row()
    quotes = {"F260821P00100000": {"bid": 0.58, "ask": 0.65, "greeks": {"delta": -0.57}}}
    evaluation = ford_scan.evaluate_open_row(row, quotes, ford_scan.now_ct())
    assert evaluation["signal"] != "HOLD" or "quote unavailable" not in evaluation.get("note", "")


def test_a_wide_spread_leg_blocks_a_spread_close_too():
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({
        "trade_id": "T-QUOTE-SPREAD", "ticker": "F", "play_type": "SPREAD",
        "call_or_put": "put", "entry_price": "1.00",
        "short_symbol": "F260821P00100000", "long_symbol": "F260821P00095000",
        "delta_at_entry": "-0.15", "iv_at_entry": "0.35",
        "timestamp": ford_scan.now_ct().isoformat(),
        "expiration": (ford_scan.now_ct().date() + ford_scan.timedelta(days=30)).isoformat(),
        "max_favorable_pct": "0",
        "last_mark": "0.90",
        "current_pl_pct": "-10.0",
        "current_pl_dollars": "-10.0",
    })
    quotes = {
        # Short leg quote is untrustworthy - huge spread.
        "F260821P00100000": {"bid": 0.20, "ask": 1.90, "greeks": {"delta": -0.35}},
        "F260821P00095000": {"bid": 0.50, "ask": 0.55, "greeks": {"delta": -0.15}},
    }
    evaluation = ford_scan.evaluate_open_row(row, quotes, ford_scan.now_ct())
    assert evaluation["signal"] == "HOLD"
    assert evaluation["mark"] == 0.90
