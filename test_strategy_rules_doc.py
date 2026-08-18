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


def test_retired_things_are_listed_as_retired():
    """So they are not resurrected or re-measured."""
    body = doc.build()
    for dead in ("ratchet", "SPY_GAP_CONT_25", "SPY_SWEEP_5",
                 "SPY_GAP_CONT_100", "SPY_EXPANSION_LEVEL"):
        assert dead in body, f"{dead} not recorded as retired"


def test_the_premarket_dead_end_is_recorded():
    """S5 Premarket Breakout scores well and can never fire - its features
    are 0% populated live. Recorded so it is not promoted later."""
    body = doc.build()
    assert "premarket" in body.lower()
    assert "0%" in body
