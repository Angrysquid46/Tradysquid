from __future__ import annotations
import tempfile
from pathlib import Path
from unittest import mock

import chain_synthesis


def test_strikes_near_spot_are_dollar_wide_and_within_band():
    strikes = chain_synthesis.strikes_near_spot(600.0, band_pct=0.03, width=1.0)
    assert strikes[0] >= 600.0 * 0.97
    assert strikes[-1] <= 600.0 * 1.03
    assert all(float(s).is_integer() for s in strikes)


def test_build_candidates_returns_only_strikes_within_the_delta_band():
    candidates = chain_synthesis.build_candidates(
        spot_price=600.0, call_or_put="call", expiration="2026-08-12",
        years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
    )
    assert candidates
    for c in candidates:
        assert chain_synthesis.SPY_0DTE_DELTA_MIN <= abs(c["delta"]) <= chain_synthesis.SPY_0DTE_DELTA_MAX


def test_build_candidates_marks_synthetic_when_no_real_cache_exists():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(chain_synthesis.robinhood_cache, "OPTION_DIR", Path(temp)):
            candidates = chain_synthesis.build_candidates(
                spot_price=600.0, call_or_put="call", expiration="2026-08-12",
                years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
            )
    assert candidates
    assert all(c["price_source"] == "synthetic" for c in candidates)


def test_real_price_override_is_used_for_entry_price_when_affordable():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(chain_synthesis.robinhood_cache, "OPTION_DIR", Path(temp)):
            candidates = chain_synthesis.build_candidates(
                spot_price=600.0, call_or_put="call", expiration="2026-08-12",
                years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
            )
            target = candidates[0]
            real_price = round(target["entry_price"] + 0.10, 2)
            chain_synthesis.robinhood_cache.save_option_bars(
                target["option_symbol"],
                [{"begins_at": "2026-08-12T14:00:00Z", "open_price": str(real_price), "high_price": str(real_price), "low_price": str(real_price), "close_price": str(real_price), "volume": 1}],
            )
            candidates_again = chain_synthesis.build_candidates(
                spot_price=600.0, call_or_put="call", expiration="2026-08-12",
                years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
            )
    updated = next(c for c in candidates_again if c["option_symbol"] == target["option_symbol"])
    assert updated["price_source"] == "real"
    assert updated["entry_price"] == real_price


def test_build_candidates_excludes_a_real_price_that_breaches_the_risk_cap():
    with tempfile.TemporaryDirectory() as temp:
        with mock.patch.object(chain_synthesis.robinhood_cache, "OPTION_DIR", Path(temp)):
            candidates = chain_synthesis.build_candidates(
                spot_price=600.0, call_or_put="call", expiration="2026-08-12",
                years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
            )
            target = candidates[0]
            chain_synthesis.robinhood_cache.save_option_bars(
                target["option_symbol"],
                [{"begins_at": "2026-08-12T14:00:00Z", "open_price": "9.99", "high_price": "9.99", "low_price": "9.99", "close_price": "9.99", "volume": 1}],
            )
            candidates_again = chain_synthesis.build_candidates(
                spot_price=600.0, call_or_put="call", expiration="2026-08-12",
                years_to_expiry=0.002, volatility=0.20, moment_iso="2026-08-12T15:00:00Z",
            )
    symbols_again = [c["option_symbol"] for c in candidates_again]
    assert target["option_symbol"] not in symbols_again
