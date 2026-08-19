"""docs/STRATEGY_RULES.md must match the live registry.

The rules were repeatedly re-derived from scratch, and several
measurements were taken against settings that had stopped being live - a
shared +50/-50 exit none of the strategies use, and ATR thresholds two of
them had been recalibrated away from. Each rediscovery cost time and
produced at least one wrong answer.

A hand-maintained list would have gone stale at the first threshold
change, which is the exact failure being prevented. So the document is
generated, and this test fails until it is regenerated after any change.
"""

from __future__ import annotations

import pathlib

import spy_live_new_strategies as lns
import spy_scanner
import strategy_rules_doc as doc


def test_the_document_matches_the_code():
    """Regenerate with `python strategy_rules_doc.py` when this fails."""
    on_disk = pathlib.Path("docs/STRATEGY_RULES.md")
    assert on_disk.exists(), "run: python strategy_rules_doc.py"
    assert on_disk.read_text(encoding="utf-8") == doc.build(), (
        "docs/STRATEGY_RULES.md is stale - regenerate it"
    )


def test_every_live_strategy_appears():
    body = doc.build()
    for entry in lns.CHANNEL_ROSTER:
        assert entry["play_type"] in body, f"{entry['play_type']} undocumented"


def test_each_strategy_documents_its_own_exit():
    """Nothing shares an exit. Measuring them under one shape is what
    produced the false result that all 13 have an identical payoff."""
    body = doc.build()
    for play, (target, stop, _t) in lns.NEW_STRATEGY_EXITS.items():
        assert f"{target:+.0f}% / {stop:+.0f}%" in body, f"{play} exit missing"


def test_key_levels_is_documented_as_an_underlying_exit():
    """It exits on the underlying, not on premium. Forgetting that made it
    look like the worst strategy and nearly got it deleted."""
    body = doc.build()
    assert "**underlying**" in body
    assert str(spy_scanner.SPY_KEY_LEVELS_STOP_BUFFER_PCT) in body




def test_the_premarket_dead_end_is_recorded():
    """S5 Premarket Breakout scores well and can never fire - its features
    are 0% populated live. Recorded so it is not promoted later."""
    body = doc.build()
    assert "premarket" in body.lower()
    assert "0%" in body


# ---------------------------------------------------------------------------
# The documented rules must match RUNTIME BEHAVIOUR, not just a config dict
# ---------------------------------------------------------------------------

def test_each_strategy_actually_behaves_as_documented():
    """Drives the real exit function at each strategy's own thresholds.

    Checking the config dict only proves the numbers are stored. This
    proves they are USED: just past its own target must take profit, just
    past its own stop must stop out, and just short of either must hold.
    """
    for play, (target, stop, _t) in lns.NEW_STRATEGY_EXITS.items():
        past_target = 1.0 * (1 + (target + 1) / 100)
        past_stop = 1.0 * (1 + (stop - 1) / 100)
        short_of_target = 1.0 * (1 + (target - 5) / 100)
        inside_stop = 1.0 * (1 + (stop + 5) / 100)

        assert lns.new_strategy_exit_signal(
            1.0, past_target, 120, play_type=play)[0] == "TAKE PROFIT", play
        assert lns.new_strategy_exit_signal(
            1.0, past_stop, 120, play_type=play)[0] == "STOP OUT", play
        assert lns.new_strategy_exit_signal(
            1.0, short_of_target, 120, play_type=play)[0] == "HOLD", play
        assert lns.new_strategy_exit_signal(
            1.0, inside_stop, 120, play_type=play)[0] == "HOLD", play


def test_no_strategy_falls_back_to_a_fifty_fifty_default():
    """+50/-50 is not any strategy's rule and must never be applied as one.

    Measuring the whole roster under a shared +50/-50 exit produced an
    entire evening of wrong conclusions - a false "every strategy has the
    same payoff ratio", a portfolio that looked like -$1.25M when it is
    +$112,729, and a proposal to delete the best strategy on the roster.
    Nothing may quietly revert to it.
    """
    for play, (target, stop, _t) in lns.NEW_STRATEGY_EXITS.items():
        assert (target, stop) != (50.0, -50.0), (
            f"{play} is on the +50/-50 default that caused the bad results"
        )
        if target > 50.0:
            assert lns.new_strategy_exit_signal(
                1.0, 1.50, 120, play_type=play)[0] != "TAKE PROFIT", (
                f"{play} took profit at +50% despite a {target:+.0f}% target"
            )


def test_key_levels_never_uses_a_premium_exit():
    """It exits on the underlying. Giving it a premium exit is what made it
    look like the worst strategy when it is the best."""
    assert spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE not in lns.NEW_STRATEGY_EXITS
    assert spy_scanner.SPY_KEY_LEVELS_STOP_BUFFER_PCT > 0
    assert spy_scanner.SPY_KEY_LEVELS_TARGET_R_MULTIPLE > 0


def test_every_strategy_has_a_plain_english_description():
    """A numbers table does not say what a play IS.

    Several of these sound alike - failed breakout vs liquidity sweep,
    midday vs final-30 momentum - and confusing two is how a wrong exit
    gets attached to the wrong idea. A new strategy must not reach the
    roster without one.
    """
    for entry in lns.CHANNEL_ROSTER:
        play = entry["play_type"]
        assert play in doc.PLAY_STYLES, f"{play} has no play-style description"
        assert len(doc.PLAY_STYLES[play]) > 60, f"{play} description is too thin"
    body = doc.build()
    assert "UNDOCUMENTED" not in body


def test_the_descriptions_name_what_makes_similar_plays_different():
    """The pairs that are easiest to confuse must state their distinction."""
    styles = doc.PLAY_STYLES
    assert "10 bars" in styles["SPY_SWEEP_10"]          # vs failed breakout
    assert "final 30" in styles["SPY_TOD_FINAL30"]      # vs midday
    assert "midday" in styles["SPY_TOD_MIDDAY"]
    assert "UNDERLYING" in styles["SPY_KEY_LEVELS"]     # vs premium exits
    assert "ITSELF" in styles["SPY_ORB_IMMEDIATE"]      # vs a retest entry
