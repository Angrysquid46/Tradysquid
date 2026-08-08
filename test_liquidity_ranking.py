"""Liquidity used to be a weak tiebreaker in scan_single_legs' score - a
strike that barely cleared the entry floor could still outscore one with
10x its real depth if its delta fit was marginally better. Real depth
should meaningfully outrank a contract that's merely legal, not be
swamped by a small delta difference."""

from __future__ import annotations

import ford_scan


def _option(delta: float, volume: int, open_interest: int, **overrides) -> dict:
    option = {
        "bid": 0.58, "ask": 0.65, "strike": 12.5,
        "open_interest": open_interest, "volume": volume,
        "greeks": {"delta": delta},
    }
    option.update(overrides)
    return option


def test_much_deeper_liquidity_outranks_a_marginally_better_delta_fit():
    # Both clear the entry floor (volume>=200, OI>=500). Thin one sits
    # closer to the "ideal" middle of the delta band; deep one is
    # slightly further off but has 10x the real depth on both axes.
    thin = _option(delta=-0.55, volume=210, open_interest=520, strike=12.5)
    deep = _option(delta=-0.50, volume=3000, open_interest=8000, strike=13.0)
    candidates = ford_scan.scan_single_legs([thin, deep], "put", "2026-08-21", "REGULAR")
    by_strike = {c["strike"]: c["score"] for c in candidates}
    assert by_strike[ford_scan.fmt_strike(13.0)] > by_strike[ford_scan.fmt_strike(12.5)]


def test_a_small_delta_edge_no_longer_beats_a_large_liquidity_gap():
    # Same idea, tighter delta gap this time - the liquidity difference
    # alone should still be decisive.
    thin = _option(delta=-0.52, volume=205, open_interest=505, strike=12.5)
    deep = _option(delta=-0.50, volume=5000, open_interest=15000, strike=13.0)
    candidates = ford_scan.scan_single_legs([thin, deep], "put", "2026-08-21", "REGULAR")
    by_strike = {c["strike"]: c["score"] for c in candidates}
    assert by_strike[ford_scan.fmt_strike(13.0)] > by_strike[ford_scan.fmt_strike(12.5)]
