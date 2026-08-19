"""stop_overshoot_target_pct/compute_stop_overshoot were extracted out of
close_alert_text's inline "Stop overshoot" card logic so a daily rollup
(system_digest_job) can reuse the exact same target_pct math on historical
closed rows instead of drifting from a second copy. Regression coverage:
extracting this broke close_alert_text once already (it prefers
evaluation.get("signal") over the row's stored last_signal, which the
extraction initially lost) - these tests lock in both call shapes.
"""

from __future__ import annotations

import spy_scanner


def _closed_row(**overrides) -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update(
        {
            "ticker": "SPY",
            # SPY_0DTE_1M was retired 2026-08-17, so it no longer resolves
            # through is_spy_0dte_play_type and these assertions silently
            # exercised a different branch. SPY_MANUAL is live and shares the
            # same stop model.
            "play_type": spy_scanner.SPY_MANUAL_PLAY_TYPE,
            "pct_gain_loss": "-40",
            "last_signal": "STOP OUT",
        }
    )
    row.update(overrides)
    return row


def test_target_pct_defaults_to_the_rows_stored_last_signal():
    row = _closed_row(last_signal="STOP OUT")
    target = spy_scanner.stop_overshoot_target_pct(row)
    assert target == -(spy_scanner.SPY_0DTE_STOP_PCT * 100)


def test_target_pct_prefers_an_explicit_close_reason_over_the_stored_one():
    # close_alert_text's use case: a fresh live evaluation can know the
    # close reason before it's been persisted to the row yet.
    row = _closed_row(last_signal="")
    target = spy_scanner.stop_overshoot_target_pct(row, "STOP OUT")
    assert target == -(spy_scanner.SPY_0DTE_STOP_PCT * 100)


def test_target_pct_is_none_for_a_non_stop_close():
    row = _closed_row(last_signal="TAKE PROFIT")
    assert spy_scanner.stop_overshoot_target_pct(row) is None


def test_target_pct_is_none_for_a_retired_spread_row():
    row = _closed_row(play_type="SPREAD", last_signal="STOP OUT")
    assert spy_scanner.stop_overshoot_target_pct(row) is None


def test_compute_stop_overshoot_returns_none_when_the_stop_held():
    row = _closed_row(pct_gain_loss=str(-(spy_scanner.SPY_0DTE_STOP_PCT * 100)))
    assert spy_scanner.compute_stop_overshoot(row) is None


def test_compute_stop_overshoot_returns_the_slip_when_the_stop_didnt_hold():
    target = -(spy_scanner.SPY_0DTE_STOP_PCT * 100)
    row = _closed_row(pct_gain_loss=str(target - 10))
    overshoot = spy_scanner.compute_stop_overshoot(row)
    assert overshoot == -10




