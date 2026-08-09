"""evaluate_open_row's reported P&L must agree with what close_row later
independently derives from the same evaluation for the same trade -
otherwise the number Discord announces at close time (which prefers the
live evaluation) can disagree with the number actually stored and summed
into performance totals for that exact trade."""

from __future__ import annotations

import spy_scanner


def test_live_evaluation_pl_matches_what_close_row_would_derive_from_it():
    # A near-worthless long option: bid has dropped to 0, so the mark is
    # the raw (bid+ask)/2 midpoint - here 0.015, which carries a third
    # decimal digit past what entry_price/exit_price are ever stored at.
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": "T-ROUND-1", "ticker": "F", "play_type": "REGULAR",
        "call_or_put": "call", "entry_price": "1.00",
        "option_symbol": "F260821C00100000",
        "delta_at_entry": "0.30", "iv_at_entry": "0.40",
        "timestamp": spy_scanner.now_ct().isoformat(),
        "expiration": (spy_scanner.now_ct().date() + spy_scanner.timedelta(days=10)).isoformat(),
        "max_favorable_pct": "0",
    })
    quotes = {
        "F260821C00100000": {
            "symbol": "F260821C00100000", "bid": 0.00, "ask": 0.03,
            "greeks": {"delta": 0.05, "theta": -0.01, "mid_iv": 0.40},
        }
    }
    evaluation = spy_scanner.evaluate_open_row(row, quotes, spy_scanner.now_ct())
    assert evaluation["signal"] == "STOP OUT"

    # close_row independently re-derives realized P&L from evaluation["mark"],
    # rounding it to the cent first. The live evaluation's own pl_dollars/
    # pl_pct must already match what that independent recomputation gives -
    # not just be "close" to it.
    tracked_exit = round(evaluation["mark"], 2)
    entry = spy_scanner.parse_entry_price(row)
    expected_realized = round((tracked_exit - entry) * 100)
    expected_pct = round(expected_realized / (entry * 100) * 100)

    assert evaluation["pl_dollars"] == expected_realized
    assert evaluation["pl_pct"] == expected_pct


def test_spread_live_evaluation_pl_matches_close_row_sign_convention():
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": "T-ROUND-2", "ticker": "F", "play_type": "SPREAD",
        "call_or_put": "put", "entry_price": "1.00",
        "short_symbol": "F260821P00100000", "long_symbol": "F260821P00095000",
        "delta_at_entry": "-0.15", "iv_at_entry": "0.35",
        "timestamp": spy_scanner.now_ct().isoformat(),
        "expiration": (spy_scanner.now_ct().date() + spy_scanner.timedelta(days=30)).isoformat(),
        "max_favorable_pct": "0",
    })
    quotes = {
        "F260821P00100000": {
            "symbol": "F260821P00100000", "bid": 1.95, "ask": 2.02,
            "greeks": {"delta": -0.35, "theta": -0.03, "mid_iv": 0.38},
        },
        "F260821P00095000": {
            "symbol": "F260821P00095000", "bid": 0.50, "ask": 0.55,
            "greeks": {"delta": -0.15, "theta": -0.01, "mid_iv": 0.36},
        },
    }
    evaluation = spy_scanner.evaluate_open_row(row, quotes, spy_scanner.now_ct())

    tracked_exit = round(evaluation["mark"], 2)
    entry = spy_scanner.parse_entry_price(row)
    expected_realized = round((entry - tracked_exit) * 100)
    expected_pct = round(expected_realized / (entry * 100) * 100)

    assert evaluation["pl_dollars"] == expected_realized
    assert evaluation["pl_pct"] == expected_pct
