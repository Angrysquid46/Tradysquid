from datetime import datetime, timedelta

import pytest

from bots.blacktide.engine import BLACKTIDE, Decision


NOW = datetime(2026, 8, 25, 10, 0)


def bars(up=True):
    return [{"close": 500 + (i * .35 if up else -i * .35),
             "high": 500.2 + (i * .35 if up else -i * .35),
             "low": 499.8 + (i * .35 if up else -i * .35),
             "volume": 1000 + i * 30} for i in range(60)]


def option(side="call", expiration="2026-08-25", bid=1.00, ask=1.05):
    return {"option_symbol": "SPY_TEST", "side": side, "expiration": expiration,
            "bid": bid, "ask": ask, "delta": .5 if side == "call" else -.5,
            "gamma": .01, "theta": -.05, "iv": .2, "data_class": "VERIFIED_REAL",
            "volume": 100, "open_interest": 100}


def test_requires_tier_a_and_sufficient_bars():
    bot = BLACKTIDE()
    assert bot.decide(as_of=NOW, bankroll=1000, market={"tier": "C"},
                      options={"tier": "A", "contracts": [option()]}, bars=bars()).action == "NO_ACTION"
    assert bot.decide(as_of=NOW, bankroll=1000, market={"tier": "A"},
                      options={"tier": "A", "contracts": [option()]}, bars=[]).action == "NO_ACTION"


def test_entry_is_same_day_long_option_at_ask_and_risk_sized():
    decision = BLACKTIDE().decide(as_of=NOW, bankroll=1000, market={"tier": "A"},
                                 options={"tier": "A", "contracts": [option()]}, bars=bars())
    assert decision.action == "ENTER"
    assert decision.side == "call" and decision.price == 1.05 and decision.contracts == 2


def test_rejects_wrong_expiration_and_fake_liquidity():
    bot = BLACKTIDE()
    for contract in (option(expiration="2026-08-26"), option(bid=0.1, ask=1.0)):
        assert bot.decide(as_of=NOW, bankroll=1000, market={"tier": "A"},
                          options={"tier": "A", "contracts": [contract]}, bars=bars()).action == "NO_ACTION"


def test_one_position_only_and_exit_uses_bid():
    bot = BLACKTIDE()
    enter = bot.decide(as_of=NOW, bankroll=1000, market={"tier": "A"},
                       options={"tier": "A", "contracts": [option()]}, bars=bars())
    bot.apply_entry(enter, trade_id="bt-1", opened_at=NOW)
    with pytest.raises(ValueError):
        bot.apply_entry(enter, trade_id="bt-2", opened_at=NOW)
    exit_decision = bot.decide(as_of=NOW + timedelta(minutes=36), bankroll=790,
                               market={"tier": "A"},
                               options={"tier": "A", "contracts": [option(bid=.90)]}, bars=bars())
    assert exit_decision.action == "EXIT" and exit_decision.price == .90


def test_bust_reset_preserves_parameters_and_advances_generation():
    bot = BLACKTIDE()
    assert bot.decide(as_of=NOW, bankroll=0, market={}, options={}, bars=[]).action == "BUST"
    original = bot.parameters
    bot.reset_generation_after_bust()
    assert bot.generation == 2 and bot.parameters == original


def test_risk_fraction_is_not_bankruptcy_when_one_contract_is_affordable():
    bot = BLACKTIDE()
    result = bot.decide(
        as_of=NOW, bankroll=110, market={"tier": "A"},
        options={"tier": "A", "contracts": [option(bid=1.0, ask=1.05)]}, bars=bars(),
    )
    assert result.action == "NO_ACTION"
    assert "risk allocation" in result.reason


def test_bust_only_when_no_qualifying_contract_is_affordable():
    result = BLACKTIDE().decide(
        as_of=NOW, bankroll=100, market={"tier": "A"},
        options={"tier": "A", "contracts": [option(bid=1.0, ask=1.05)]}, bars=bars(),
    )
    assert result.action == "BUST"


def test_evolution_is_bounded_and_requires_own_completed_sample():
    bot = BLACKTIDE()
    assert bot.evolve([1.0] * 7).opportunity_threshold == .43
    assert bot.evolve([-1.0] * 8).opportunity_threshold == .44
