from dataclasses import replace

from bots.blacktide.amcte import (
    MarketState, MarketVector, build_vector, classify_state, opportunity,
)


def test_all_approved_market_states_are_reachable():
    cases = {
        MarketState.DISORDER: (.01, 0, .2, .03, .9, .2),
        MarketState.BALANCE: (.05, 0, .4, .005, .7, .2),
        MarketState.PRESSURE_BUILD: (.15, .10, .4, .015, .7, .2),
        MarketState.IGNITION: (.25, .10, .4, .015, .6, .5),
        MarketState.EXPANSION: (.45, .05, .55, .015, .4, .2),
        MarketState.MATURE_EXPANSION: (.45, .01, .55, .015, .4, .2),
        MarketState.EXHAUSTION: (.35, -.05, .35, .015, .5, .2),
        MarketState.FAILED_EXPANSION: (.25, -.01, .20, .015, .6, .2),
        MarketState.REVERSAL_CONTROL: (.28, .11, .35, .015, .5, .2),
    }
    for expected, args in cases.items():
        assert classify_state(*args) is expected


def _vector(state=MarketState.IGNITION):
    return MarketVector(
        500, .9, .9, .01, .01, .8, .9, .015, .8, .95,
        .8, .2, .6, .3, .1, state,
    )


def test_all_approved_entry_families_are_mapped():
    expected = {
        MarketState.IGNITION: "IGNITION_TRANSITION",
        MarketState.EXPANSION: "CONTROLLED_CONTINUATION",
        MarketState.MATURE_EXPANSION: "CONTROLLED_CONTINUATION",
        MarketState.FAILED_EXPANSION: "FAILED_CONTROL_REVERSAL",
        MarketState.REVERSAL_CONTROL: "FAILED_CONTROL_REVERSAL",
        MarketState.PRESSURE_BUILD: "PRESSURE_COMPRESSION_RELEASE",
    }
    for state, family in expected.items():
        found = opportunity(replace(_vector(), state=state), threshold=0)
        assert found is not None and found.family == family


def test_insufficient_completed_primary_history_fails_closed():
    bars = [{"close": 500, "high": 501, "low": 499, "volume": 100}] * 44
    assert build_vector(bars, options_quality=1) is None


def test_bad_options_quality_explicitly_returns_no_trade():
    assert opportunity(replace(_vector(), options_quality=.64), threshold=0) is None
