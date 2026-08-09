"""Tests for the split delta ranges: two independent sources converged on
the same finding - a single 0.20-0.80 range was too wide to define one
coherent strategy. Regular and swing now use their own, narrower ranges."""

from __future__ import annotations

import spy_scanner


def _option(delta: float, **overrides) -> dict:
    option = {
        "bid": 0.45, "ask": 0.50, "strike": 100.0,
        "open_interest": 500, "volume": 200,
        "greeks": {"delta": delta},
    }
    option.update(overrides)
    return option


def test_regular_accepts_a_delta_inside_its_narrower_range():
    chain = [_option(0.55)]  # inside 0.45-0.65, outside the old 0.20-0.80... well within both
    candidates = spy_scanner.scan_single_legs(chain, "call", "2026-08-14", "REGULAR")
    assert len(candidates) == 1


def test_regular_rejects_a_delta_too_low_for_its_range_but_inside_the_old_one():
    # 0.25 was allowed under the old shared 0.20-0.80 range - must now be
    # rejected under regular's narrower 0.45-0.65.
    chain = [_option(0.25)]
    candidates = spy_scanner.scan_single_legs(chain, "call", "2026-08-14", "REGULAR")
    assert candidates == []


def test_swing_accepts_a_delta_inside_its_own_range():
    chain = [_option(0.62)]  # inside swing's 0.55-0.70
    candidates = spy_scanner.scan_single_legs(chain, "call", "2026-08-14", "SWING")
    assert len(candidates) == 1


def test_swing_accepts_a_lower_delta_that_regular_would_reject():
    # Swing's floor widened to 0.35 (see SWING_LEG_DELTA_MIN in spy_scanner.py -
    # SOFI/HL's real validated edge lives at 0.31-0.51 delta, below
    # regular's 0.45 floor) so swing's range is now a superset of
    # regular's, not a separate narrower one. 0.38 is below regular's
    # 0.45 floor but inside swing's 0.35 floor - confirms swing genuinely
    # reaches lower delta than regular does.
    chain = [_option(0.38)]
    assert spy_scanner.scan_single_legs(chain, "call", "2026-08-14", "REGULAR") == []
    assert len(spy_scanner.scan_single_legs(chain, "call", "2026-08-14", "SWING")) == 1


def test_the_old_shared_constants_still_exist_for_backward_compatibility():
    assert spy_scanner.SINGLE_LEG_DELTA_MIN == 0.20
    assert spy_scanner.SINGLE_LEG_DELTA_MAX == 0.80
