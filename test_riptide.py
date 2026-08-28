from datetime import datetime, timedelta

import pytest

from bots.riptide.engine import Riptide


NOW = datetime(2026, 8, 28, 10, 0)


def bars(direction: str = "call"):
    rows = [{"close": 500 + i * .03, "high": 500.05 + i * .03, "low": 499.95 + i * .03, "volume": 1000} for i in range(32)]
    base = rows[-1]["close"]
    if direction == "call":
        closes = [base + .05, base + .25, base + .55]
    else:
        closes = [base - .05, base - .25, base - .55]
    rows.extend({"close": close, "high": close + .05, "low": close - .05, "volume": 1500} for close in closes)
    return rows


def option(side="call", *, bid=1.0, ask=1.05, expiration=None):
    return {"option_symbol": "SPY260828C00500000", "side": side, "expiration": expiration or NOW.date().isoformat(), "bid": bid, "ask": ask, "delta": .45 if side == "call" else -.45, "gamma": .01, "theta": -.05, "iv": .2, "data_class": "VERIFIED_REAL", "volume": 100, "open_interest": 500}


def test_riptide_requires_tier_a_and_causal_breakout():
    engine = Riptide()
    assert engine.decide(as_of=NOW, bankroll=1000, market={"tier": "C"}, options={"tier": "A", "contracts": [option()]}, bars=bars()).action == "NO_ACTION"
    assert engine.decide(as_of=NOW, bankroll=1000, market={"tier": "A"}, options={"tier": "A", "contracts": [option("put")]}, bars=bars("put")).side == "put"


def test_riptide_uses_liquid_same_day_ask_entry_and_bid_exit():
    engine = Riptide()
    enter = engine.decide(as_of=NOW, bankroll=1000, market={"tier": "A"}, options={"tier": "A", "contracts": [option()]}, bars=bars())
    assert enter.action == "ENTER" and enter.price == 1.05 and enter.contracts == 3
    engine.apply_entry(enter, trade_id="r-1", opened_at=NOW)
    exit_decision = engine.decide(as_of=NOW + timedelta(minutes=1), bankroll=685, market={"tier": "A"}, options={"tier": "A", "contracts": [option(bid=1.55)]}, bars=bars())
    assert exit_decision.action == "EXIT" and exit_decision.price == 1.55


def test_riptide_rejects_wide_or_wrong_expiration_contracts():
    engine = Riptide()
    for contract in (option(bid=.5, ask=1.05), option(expiration="2026-08-29")):
        assert engine.decide(as_of=NOW, bankroll=1000, market={"tier": "A"}, options={"tier": "A", "contracts": [contract]}, bars=bars()).action == "NO_ACTION"


def test_riptide_evolution_is_bounded_and_own_outcome_only():
    engine = Riptide()
    assert engine.evolve([-1.0] * 11).breakout_volume_ratio == pytest.approx(1.18)
    assert engine.evolve([-1.0] * 12).breakout_volume_ratio == pytest.approx(1.20)
