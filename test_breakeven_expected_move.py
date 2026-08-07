"""Tests for the breakeven-vs-expected-move note: purely informational,
answers a real question nothing else surfaces - does this contract need a
bigger-than-typical move to reach breakeven, given its own implied
volatility and time to expiration. Not a filter - there isn't yet real
evidence for where a cutoff should sit, so this only adds honest
information to the thesis text."""

from __future__ import annotations

import ford_scan


def _option(delta: float, iv: float = 0.40, **overrides) -> dict:
    option = {
        "bid": 0.45, "ask": 0.50, "strike": 100.0,
        "open_interest": 500, "volume": 50,
        "greeks": {"delta": delta, "mid_iv": iv},
    }
    option.update(overrides)
    return option


def test_a_breakeven_note_appears_when_spot_price_is_provided():
    chain = [_option(0.55, strike=100.0)]
    candidates = ford_scan.scan_single_legs(
        chain, "call", "2026-09-14", "REGULAR", spot_price=99.0
    )
    assert len(candidates) == 1
    assert candidates[0]["breakeven_moves_note"] != ""
    assert "expected move" in candidates[0]["breakeven_moves_note"]


def test_no_note_when_spot_price_is_not_provided():
    # Every existing caller not yet passing spot_price must keep working
    # exactly as before - this stays purely additive.
    chain = [_option(0.55, strike=100.0)]
    candidates = ford_scan.scan_single_legs(chain, "call", "2026-09-14", "REGULAR")
    assert len(candidates) == 1
    assert candidates[0]["breakeven_moves_note"] == ""


def test_a_close_breakeven_is_described_as_inside_a_typical_move():
    # Strike right at spot, cheap premium - breakeven very close to spot,
    # should read as "inside" a typical move for any reasonable IV.
    chain = [_option(0.55, iv=0.60, strike=100.0, ask=0.30, bid=0.28)]
    candidates = ford_scan.scan_single_legs(
        chain, "call", "2026-09-14", "REGULAR", spot_price=100.0
    )
    assert "inside" in candidates[0]["breakeven_moves_note"]


def test_a_far_breakeven_with_low_iv_and_short_dte_reads_as_beyond():
    # Deep OTM-ish breakeven relative to spot, very low IV, short DTE -
    # expected move is small, breakeven distance is large, should read
    # as "beyond" a typical move.
    chain = [_option(0.55, iv=0.05, strike=130.0, ask=0.50, bid=0.48)]
    candidates = ford_scan.scan_single_legs(
        chain, "call", "2026-08-14", "REGULAR", spot_price=100.0
    )
    assert "beyond" in candidates[0]["breakeven_moves_note"]


def test_this_never_filters_out_a_candidate_it_only_annotates_it():
    # Confirms the change is purely additive - same candidate count with
    # or without spot_price, only the note differs.
    chain = [_option(0.55, strike=100.0)]
    without = ford_scan.scan_single_legs(chain, "call", "2026-09-14", "REGULAR")
    with_spot = ford_scan.scan_single_legs(
        chain, "call", "2026-09-14", "REGULAR", spot_price=99.0
    )
    assert len(without) == len(with_spot) == 1


def test_the_thesis_text_includes_the_breakeven_note_when_present():
    chain = [_option(0.55, strike=100.0)]
    candidates = ford_scan.scan_single_legs(
        chain, "call", "2026-09-14", "REGULAR", spot_price=99.0
    )
    row = ford_scan.candidate_to_row(candidates[0], rows=[], timestamp=ford_scan.now_ct())
    assert "expected move" in row["thesis"]
