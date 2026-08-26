"""Real tests for contract_selection.py's filters."""

from __future__ import annotations

from datetime import date

import market_data_store as store

from bots.claude.contract_selection import select_contract
from bots.claude.parameters import HYPOTHESIS_DEFAULTS

PARAMS = dict(HYPOTHESIS_DEFAULTS["trend_continuation"])
TODAY = date(2026, 8, 25)


def _contract(**overrides) -> dict:
    base = {
        "option_symbol": "SPY260825C00500000",
        "expiration": "2026-08-25",
        "strike": 500.0,
        "side": "call",
        "bid": 3.9,
        "ask": 4.0,
        "delta": 0.45,
        "data_class": store.VERIFIED_REAL,
    }
    base.update(overrides)
    return base


def test_selects_eligible_call_contract():
    contract = select_contract([_contract()], "CALL", TODAY, PARAMS)
    assert contract is not None
    assert contract["option_symbol"] == "SPY260825C00500000"


def test_rejects_non_0dte_expiration():
    contract = _contract(expiration="2026-08-26")
    assert select_contract([contract], "CALL", TODAY, PARAMS) is None


def test_rejects_non_verified_real_data_class():
    contract = _contract(data_class=store.REAL_WITH_LIMITATIONS)
    assert select_contract([contract], "CALL", TODAY, PARAMS) is None


def test_rejects_delta_outside_band():
    too_low = _contract(delta=0.10)
    too_high = _contract(delta=0.90)
    assert select_contract([too_low], "CALL", TODAY, PARAMS) is None
    assert select_contract([too_high], "CALL", TODAY, PARAMS) is None


def test_rejects_ask_above_premium_cap():
    contract = _contract(ask=501.0, bid=500.0)
    assert select_contract([contract], "CALL", TODAY, PARAMS) is None


def test_rejects_wide_spread():
    contract = _contract(bid=1.0, ask=4.0)  # (4-1)/2.5 = 1.2, way over 0.15
    assert select_contract([contract], "CALL", TODAY, PARAMS) is None


def test_rejects_wrong_side():
    put_contract = _contract(side="put")
    assert select_contract([put_contract], "CALL", TODAY, PARAMS) is None


def test_picks_delta_closest_to_band_midpoint():
    near_mid = _contract(option_symbol="NEAR", delta=0.45)
    edge = _contract(option_symbol="EDGE", delta=0.36)
    chosen = select_contract([edge, near_mid], "CALL", TODAY, PARAMS)
    assert chosen["option_symbol"] == "NEAR"


def test_returns_none_for_empty_chain():
    assert select_contract([], "CALL", TODAY, PARAMS) is None


# --- confidence-biased targeting (owner directive 2026-08-26: aggression
# should scale with conviction) ---

def test_default_confidence_still_picks_band_midpoint():
    near_mid = _contract(option_symbol="NEAR", delta=0.45)
    edge = _contract(option_symbol="EDGE", delta=0.36)
    chosen = select_contract([edge, near_mid], "CALL", TODAY, PARAMS)
    assert chosen["option_symbol"] == "NEAR"


def test_high_confidence_reaches_toward_delta_min_cheaper_leg():
    """High conviction should prefer the cheaper/further-OTM leg of the
    band (closer to delta_min=0.35) over the midpoint."""
    near_min = _contract(option_symbol="NEAR_MIN", delta=0.36)
    near_mid = _contract(option_symbol="NEAR_MID", delta=0.45)
    chosen = select_contract([near_min, near_mid], "CALL", TODAY, PARAMS, confidence=1.0)
    assert chosen["option_symbol"] == "NEAR_MIN"


def test_low_confidence_reaches_toward_delta_max_safer_leg():
    """Low conviction (still enough to fire, just barely) should prefer
    the pricier/safer leg of the band (closer to delta_max=0.55)."""
    near_mid = _contract(option_symbol="NEAR_MID", delta=0.45)
    near_max = _contract(option_symbol="NEAR_MAX", delta=0.54)
    chosen = select_contract([near_mid, near_max], "CALL", TODAY, PARAMS, confidence=0.0)
    assert chosen["option_symbol"] == "NEAR_MAX"


def test_confidence_is_clamped_to_valid_range():
    """Out-of-range confidence (a caller bug, not expected in practice)
    must not push the target delta outside the configured band."""
    near_min = _contract(option_symbol="NEAR_MIN", delta=0.36)
    chosen = select_contract([near_min], "CALL", TODAY, PARAMS, confidence=5.0)
    assert chosen["option_symbol"] == "NEAR_MIN"
