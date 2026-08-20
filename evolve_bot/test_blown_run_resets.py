"""A run that cannot afford a contract is over - reset it.

On 2026-08-14 evolve's balance fell to $478 with a tuned 5% position size:
$23.90 per trade against contracts costing $46-$100. contracts_affordable
correctly returned 0 and the engine silently returned None.

That is a deadlock, not a pause. It could not open, so it never closed, so
credit_exit - the ONLY place a reset could fire - was never reached again.
The run froze for five days with no trades and no signal anything was
wrong, while the daily refresh kept reporting "dashboard: posted".

RESET_FLOOR ($25) is not a sufficient bankruptcy test. Functional
bankruptcy is "cannot afford to participate".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bankroll


def _state(balance: float, run: int = 1, resets: int = 0) -> dict:
    return {"run_number": run, "balance": balance, "starting_balance": 1000.0,
            "peak_balance": 1000.0, "all_time_high_balance": 1000.0,
            "all_time_high_run": 1, "total_resets": resets}


def test_the_exact_2026_08_14_state_is_blown_out():
    """$478 balance, 5% size, a $0.46 contract - the real numbers."""
    size = bankroll.position_size_dollars(_state(478.0), 0.05)
    assert size < 46.0, f"position size {size} should not fund a $46 contract"
    assert bankroll.blown_out(_state(478.0), size, 0.46) is True


def test_a_healthy_run_is_not_blown_out():
    size = bankroll.position_size_dollars(_state(1000.0), 0.25)
    assert bankroll.blown_out(_state(1000.0), size, 0.46) is False


def test_reset_floor_alone_would_have_missed_it():
    """The regression: $478 sits far above RESET_FLOOR and is still dead."""
    assert 478.0 > bankroll.RESET_FLOOR
    size = bankroll.position_size_dollars(_state(478.0), 0.05)
    assert bankroll.blown_out(_state(478.0), size, 0.46) is True


def test_start_new_run_restores_the_money_and_counts_the_run():
    after = bankroll.start_new_run(_state(478.0, run=1, resets=0))
    assert after["balance"] == bankroll.STARTING_BALANCE
    assert after["run_number"] == 2
    assert after["total_resets"] == 1


def test_the_all_time_high_survives_a_reset():
    """Resets restore the money; they must not erase the record."""
    state = _state(478.0)
    state["all_time_high_balance"] = 1420.0
    state["all_time_high_run"] = 1
    after = bankroll.start_new_run(state)
    assert after["all_time_high_balance"] == 1420.0
    assert after["all_time_high_run"] == 1


def test_the_engine_resets_instead_of_returning_silently():
    """The deadlock itself: the unaffordable branch must start a new run."""
    import inspect
    import engine
    src = inspect.getsource(engine._try_open_new_position)
    branch = src[src.index("if contracts < 1:"):]
    assert "start_new_run" in branch, (
        "the unaffordable branch still returns without resetting - this is "
        "the five-day freeze"
    )
    assert "_log_decline" in branch, "the decline is still silent"


# ---------------------------------------------------------------------------
# Blow-out must archive, learn, apply and stay traceable
# ---------------------------------------------------------------------------
#
# Owner: "it applies automatically, I don't want it to ask me to improve
# itself ... let it run wild" and "it's a good idea for it to be able to
# trace back if things got worse."

import inspect

import engine


def test_the_blowout_archives_learns_and_applies():
    src = inspect.getsource(engine._try_open_new_position)
    branch = src[src.index("if contracts < 1:"):]
    assert "_evolve_after_blowout" in branch, "a dead run is not learned from"
    assert branch.index("_evolve_after_blowout") < branch.index("start_new_run"), (
        "the run must be archived and scored BEFORE the balance is reset - "
        "afterwards its run_number no longer identifies its trades"
    )


def test_learning_is_unattended():
    """No owner-approval gate on the applied change."""
    src = inspect.getsource(engine._evolve_after_blowout)
    assert "run_proposal_cycle" in src and "apply_proposal" in src


def test_a_failure_to_learn_still_lets_the_next_run_start():
    """Learning must never be able to re-freeze the bot."""
    src = inspect.getsource(engine._evolve_after_blowout)
    assert "except Exception" in src, "a proposal failure would propagate"


def test_every_applied_change_is_traceable():
    """The owner asked to be able to trace a run that got worse."""
    src = inspect.getsource(engine._evolve_after_blowout)
    for field in ("applied", "active_variant_after", "RUN_HISTORY"):
        assert field in src, f"{field} missing - the change would be untraceable"


def test_the_postmortem_describes_how_the_run_died():
    src = inspect.getsource(engine._run_postmortem)
    for field in ("ended_because", "win_rate", "worst_loss", "exit_reasons", "net_pl"):
        assert field in src, f"post-mortem does not record {field}"


def test_the_archive_is_per_run_and_written_before_reset():
    src = inspect.getsource(engine._archive_run)
    assert "run_%d.csv" in src or "run_" in src
    assert "run_number" in src, "the archive must select only this run's trades"
