"""Nothing may open a position the market cannot fill or exit.

2026-08-19: three 0DTE positions on SPY260819C00769000 were opened at
17:32 - two and a half hours after the 15:00 close, on a contract that had
already expired. Unclosable: no market to exit into, and the option had
settled. They sat OPEN in the trade log.

Two batches that day carried /force-all-strategies text while the
command-bot access log shows no interaction at either time. The log is
continuous - 114-120 entries an hour with no gaps - so that is real
evidence, not a missing record. The trigger was never identified.

That is exactly why the guard lives in candidate_to_row, the single point
all six entry paths funnel through, rather than in any caller. Whatever
reaches it, an expired or after-hours entry is refused.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import spy_scanner as s


def _candidate(expiration: str, play_type: str = "SPY_OPENING_GAP_FADE"):
    return {
        "play_type": play_type, "call_or_put": "call", "strike": "769",
        "expiration": expiration, "entry_price": 0.46, "cost_or_credit": "0.46",
        "delta": 0.35, "theta": -0.05, "iv": 0.2, "pop": 35.0,
        "max_profit": "UNLIMITED", "max_risk": 46.0, "breakeven": 769.46,
        "option_symbol": "SPY260819C00769000", "score": 35.0,
        "setup_reason": "test", "spot_at_entry": 770.0,
        "open_interest": 5000, "volume": 2000, "bid": 0.44, "ask": 0.46,
        "bid_ask_width": 0.02, "expiration_tier": "0DTE",
    }


def _at(hour: int, minute: int = 0):
    return s.now_ct().replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_an_expired_contract_is_refused():
    """The exact 2026-08-19 case: yesterday's expiry, opened today."""
    yesterday = (s.now_ct().date() - timedelta(days=1)).isoformat()
    with pytest.raises(s.UntradeableEntry, match="expired"):
        s.assert_tradeable_entry(_candidate(yesterday), _at(10, 0))


def test_opening_after_the_close_is_refused():
    """17:32 on a 15:00 close - no fill, no exit, and a 0DTE already gone."""
    today = s.now_ct().date().isoformat()
    after_close = _at(17, 32)
    with pytest.raises(s.UntradeableEntry, match="closed"):
        s.assert_tradeable_entry(_candidate(today), after_close)


def test_opening_before_the_open_is_refused():
    today = s.now_ct().date().isoformat()
    with pytest.raises(s.UntradeableEntry, match="closed"):
        s.assert_tradeable_entry(_candidate(today), _at(6, 15))


def test_candidate_to_row_itself_refuses_not_just_the_helper():
    """The guard must sit on the choke point, so an unknown caller cannot
    bypass it - the 2026-08-19 batches had no identified caller."""
    today = s.now_ct().date().isoformat()
    with pytest.raises(s.UntradeableEntry):
        s.candidate_to_row(_candidate(today), [], _at(17, 32))


def test_a_normal_intraday_entry_is_still_allowed(monkeypatch):
    """The guard must not block real trading."""
    today = s.now_ct().date().isoformat()
    monkeypatch.setattr(s, "market_is_open_now", lambda: (True, s.now_ct()))
    s.assert_tradeable_entry(_candidate(today), _at(10, 0))          # no raise
    row = s.candidate_to_row(_candidate(today), [], _at(10, 0))
    assert row["expiration"] == today
    assert row["outcome"] == "OPEN"


def test_a_future_expiration_is_allowed_while_open(monkeypatch):
    monkeypatch.setattr(s, "market_is_open_now", lambda: (True, s.now_ct()))
    future = (s.now_ct().date() + timedelta(days=5)).isoformat()
    s.assert_tradeable_entry(_candidate(future), _at(10, 0))          # no raise
