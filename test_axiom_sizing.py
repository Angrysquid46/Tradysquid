"""Real tests for sizing.py - bounded by available bankroll and the
premium cap, no separate fractional-risk parameter."""

from __future__ import annotations

from bots.claude.parameters import HYPOTHESIS_DEFAULTS
from bots.claude.sizing import position_size

PARAMS = dict(HYPOTHESIS_DEFAULTS["trend_continuation"])


def test_sizes_one_contract_when_bankroll_covers_exactly_one():
    assert position_size(400.0, 4.0, PARAMS) == 1  # 4.0*100 = $400


def test_sizes_multiple_contracts_when_bankroll_allows():
    assert position_size(900.0, 4.0, PARAMS) == 2  # floor(900/400) = 2


def test_floors_down_rather_than_rounding():
    assert position_size(799.0, 4.0, PARAMS) == 1  # floor(799/400) = 1, not 2


def test_zero_when_bankroll_too_small():
    assert position_size(100.0, 4.0, PARAMS) == 0


def test_zero_when_ask_exceeds_premium_cap():
    assert position_size(10000.0, 500.0, PARAMS) == 0


def test_zero_when_bankroll_not_positive():
    assert position_size(0.0, 4.0, PARAMS) == 0
    assert position_size(-50.0, 4.0, PARAMS) == 0
