"""Tests for the per-ticker exposure cap mechanism. The cap is disabled by
default as of tonight (explicit direction: it only limits concentration,
it doesn't make any trade smarter) - MAX_OPEN_POSITIONS_PER_TICKER defaults
to effectively unlimited. The mechanism itself stays in place and stays
correct, in case a real limit is wanted again later, so these tests set an
explicit cap value rather than depending on whatever the default happens
to be right now."""

from __future__ import annotations

from unittest import mock

import ford_scan


def _row(trade_id: str, ticker: str, outcome: str = "OPEN") -> dict[str, str]:
    row = {field: "" for field in ford_scan.LOG_HEADER}
    row.update({"trade_id": trade_id, "ticker": ticker, "outcome": outcome})
    return row


def _candidate(play_type: str, score: float) -> dict[str, object]:
    return {"play_type": play_type, "score": score}


def test_admits_up_to_an_explicit_cap_when_nothing_is_open_yet():
    eligible = [
        _candidate("REGULAR", 5.0),
        _candidate("SWING", 4.0),
        _candidate("SPREAD", 3.0),
    ]
    with mock.patch.object(ford_scan, "MAX_OPEN_POSITIONS_PER_TICKER", 2):
        selected = ford_scan.apply_ticker_exposure_cap(eligible, rows=[], ticker="F")
    assert len(selected) == 2
    assert [c["play_type"] for c in selected] == ["REGULAR", "SWING"]


def test_reduces_capacity_by_existing_open_positions_on_the_same_ticker():
    rows = [_row("T1", "F", outcome="OPEN")]
    eligible = [_candidate("REGULAR", 5.0), _candidate("SWING", 4.0)]
    with mock.patch.object(ford_scan, "MAX_OPEN_POSITIONS_PER_TICKER", 2):
        selected = ford_scan.apply_ticker_exposure_cap(eligible, rows, ticker="F")
    assert len(selected) == 1
    assert selected[0]["play_type"] == "REGULAR"


def test_admits_nothing_once_the_ticker_is_already_at_an_explicit_capacity():
    rows = [_row("T1", "F", outcome="OPEN"), _row("T2", "F", outcome="OPEN")]
    eligible = [_candidate("REGULAR", 5.0), _candidate("SWING", 4.0)]
    with mock.patch.object(ford_scan, "MAX_OPEN_POSITIONS_PER_TICKER", 2):
        selected = ford_scan.apply_ticker_exposure_cap(eligible, rows, ticker="F")
    assert selected == []


def test_open_positions_on_a_different_ticker_do_not_count_against_this_one():
    rows = [_row("T1", "AAPL", outcome="OPEN"), _row("T2", "AAPL", outcome="OPEN")]
    eligible = [_candidate("REGULAR", 5.0)]
    with mock.patch.object(ford_scan, "MAX_OPEN_POSITIONS_PER_TICKER", 2):
        selected = ford_scan.apply_ticker_exposure_cap(eligible, rows, ticker="F")
    assert len(selected) == 1


def test_closed_positions_on_this_ticker_do_not_count_against_the_cap():
    rows = [
        _row("T1", "F", outcome="WIN"),
        _row("T2", "F", outcome="LOSS"),
        _row("T3", "F", outcome="OPEN"),
    ]
    eligible = [_candidate("REGULAR", 5.0), _candidate("SWING", 4.0)]
    with mock.patch.object(ford_scan, "MAX_OPEN_POSITIONS_PER_TICKER", 2):
        selected = ford_scan.apply_ticker_exposure_cap(eligible, rows, ticker="F")
    assert len(selected) == 1


def test_the_current_default_applies_no_real_limit():
    # This is the actual behavior right now, tonight, per explicit
    # direction - confirms the default itself, not just the mechanism.
    eligible = [_candidate("REGULAR", 5.0), _candidate("SWING", 4.0),
                _candidate("SPREAD", 3.0), _candidate("BULL_PUT", 2.0)]
    selected = ford_scan.apply_ticker_exposure_cap(eligible, rows=[], ticker="F")
    assert len(selected) == len(eligible)

