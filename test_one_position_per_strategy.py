"""Tests for the per-strategy single-open-position gate. Owner: "as long
as we do 1 trade at a time we have a 500 limit... yes it's per trader not
all together, 13 traders a max of 13 and so on." Confirmed live before
this was added that this wasn't actually true - SPY_KEY_LEVELS had
stacked up to 6 concurrent open positions, SPY_0DTE_5M up to 4 - because
recently_tracked only ever blocked re-entering the EXACT same contract,
never a second position under the same strategy on a different strike."""

from __future__ import annotations

import spy_scanner


def _row(trade_id: str, play_type: str, outcome: str = "OPEN") -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({"trade_id": trade_id, "play_type": play_type, "outcome": outcome})
    return row


def _candidate(play_type: str, score: float) -> dict[str, object]:
    return {"play_type": play_type, "score": score}


def test_has_open_position_is_false_with_no_rows():
    assert spy_scanner.has_open_position([], "SPY_KEY_LEVELS") is False


def test_has_open_position_is_true_when_that_play_type_has_an_open_row():
    rows = [_row("T1", "SPY_KEY_LEVELS", outcome="OPEN")]
    assert spy_scanner.has_open_position(rows, "SPY_KEY_LEVELS") is True


def test_has_open_position_is_true_regardless_of_strike_or_expiration():
    """The real gap this closes: recently_tracked keys on the exact
    contract (strike/expiration/side), so a different strike qualifying
    on the next scan wasn't blocked - has_open_position only cares about
    play_type and outcome, not which specific contract is held."""
    row = _row("T1", "SPY_KEY_LEVELS", outcome="OPEN")
    row["strike"] = "770"
    assert spy_scanner.has_open_position([row], "SPY_KEY_LEVELS") is True


def test_has_open_position_ignores_closed_rows():
    rows = [_row("T1", "SPY_KEY_LEVELS", outcome="WIN"), _row("T2", "SPY_KEY_LEVELS", outcome="LOSS")]
    assert spy_scanner.has_open_position(rows, "SPY_KEY_LEVELS") is False


def test_has_open_position_ignores_other_play_types():
    rows = [_row("T1", "SPY_0DTE_1M", outcome="OPEN")]
    assert spy_scanner.has_open_position(rows, "SPY_KEY_LEVELS") is False


def test_dedupe_by_play_type_keeps_only_the_first_seen_per_play_type():
    candidates = [
        _candidate("SPY_0DTE_1M", 90.0),
        _candidate("SPY_KEY_LEVELS", 80.0),
        _candidate("SPY_0DTE_1M", 70.0),
    ]
    deduped = spy_scanner.dedupe_by_play_type(candidates)
    assert [c["play_type"] for c in deduped] == ["SPY_0DTE_1M", "SPY_KEY_LEVELS"]


def test_dedupe_by_play_type_keeps_the_best_scored_candidate_when_sorted_first():
    """dedupe_by_play_type trusts its input is already score-sorted
    (main() sorts before calling it) - this confirms that contract: the
    highest-scored candidate for a play_type survives when it's first."""
    candidates = sorted(
        [
            _candidate("SPY_0DTE_1M", 55.0),
            _candidate("SPY_0DTE_1M", 91.0),
            _candidate("SPY_0DTE_1M", 72.0),
        ],
        key=lambda c: c["score"],
        reverse=True,
    )
    deduped = spy_scanner.dedupe_by_play_type(candidates)
    assert len(deduped) == 1
    assert deduped[0]["score"] == 91.0


def test_dedupe_by_play_type_does_not_touch_different_strategies():
    candidates = [
        _candidate("SPY_RATCHET_26_16", 60.0),
        _candidate("SPY_RATCHET_30_16", 55.0),
        _candidate("SPY_KEY_LEVELS", 40.0),
    ]
    deduped = spy_scanner.dedupe_by_play_type(candidates)
    assert len(deduped) == 3
