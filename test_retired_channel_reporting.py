"""A retired channel must not take the whole reporting job down.

spy_scanner popped `ratchet_leaderboard` from CHANNEL_NAMES but both
reporting modules still posted its leaderboard. Every discord-reporting
run then died with "Discord did not acknowledge scorecard
ratchet_leaderboard:report-v5:ratchet_leaderboard:index" - so the cards
that DID have a home stopped updating too, because the exception aborted
the run before reaching them.

The distinction that matters: a logical name the code no longer declares
is retired (skip it), while one still declared that Discord will not
acknowledge is a genuine failure (still raise). Collapsing those two into
"never raise" would hide real breakage.
"""

from __future__ import annotations

import pytest

import performance_reconciliation as pr
import performance_scorecards as ps
import spy_scanner


class _SilentDiscord:
    """Acknowledges nothing - as Discord does for a channel that is gone."""

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def upsert_channel_message(self, logical_name, state, state_key,
                               content, search_token=""):
        self.attempts.append(logical_name)
        return ""


@pytest.mark.parametrize("module", [pr, ps], ids=["reconciliation", "scorecards"])
def test_a_retired_channel_is_skipped_instead_of_killing_the_run(module):
    discord = _SilentDiscord()
    retired = "ratchet_leaderboard"
    assert retired not in spy_scanner.CHANNEL_NAMES, (
        "this test is meaningless if the channel is still declared"
    )
    result = module._require_upsert(
        discord, retired, {}, "report:index", "body", "Retired Leaderboard")
    assert result == ""


@pytest.mark.parametrize("module", [pr, ps], ids=["reconciliation", "scorecards"])
def test_a_live_channel_that_will_not_acknowledge_still_raises(module):
    """The guard must not become a blanket 'ignore all Discord failures'."""
    discord = _SilentDiscord()
    live = pr.STRATEGY_LEADERBOARD_LOGICAL
    assert live in spy_scanner.CHANNEL_NAMES
    with pytest.raises(RuntimeError):
        module._require_upsert(
            discord, live, {}, "report:index", "body", "Strategy Leaderboard")


def test_the_ratchet_leaderboard_has_no_channel_left():
    """Documents why the skip path is reachable at all."""
    assert spy_scanner.CHANNEL_NAMES.get("ratchet_leaderboard") is None
