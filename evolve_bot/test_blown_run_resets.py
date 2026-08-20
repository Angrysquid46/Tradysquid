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


def test_the_2026_08_14_freeze_was_sizing_and_not_bankruptcy():
    """$478 balance, 5% size, a $0.46 contract - the real numbers.

    This was originally recorded as a blow-out and given a reset. That was
    a misdiagnosis. $478 buys ten $46 contracts; the account was fine. What
    stopped it was sizing 5% of the balance as the amount it could SPEND -
    $23.90 - which cannot buy a $46 contract.

    Treating it as bankruptcy is what produced the reset loop on
    2026-08-20: ten resets in one morning on an untouched $1,000.
    """
    state = _state(478.0)
    assert not bankroll.blown_out(state, 0.46)
    assert bankroll.contracts_for_trade(state, 23.90, 0.46, 0.20) >= 1


def test_a_healthy_run_is_not_blown_out():
    assert bankroll.blown_out(_state(1000.0), 0.46) is False


def test_the_reset_floor_still_is_not_the_test():
    """A balance above RESET_FLOOR can still be unable to buy anything -
    that part of the original finding stands, it just needs a contract
    price the balance genuinely cannot cover."""
    assert 30.0 > bankroll.RESET_FLOOR
    assert bankroll.blown_out(_state(30.0), 0.46) is True


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


# ---------------------------------------------------------------------------
# The reset loop of 2026-08-20
# ---------------------------------------------------------------------------

def test_a_full_bankroll_is_never_blown_out() -> None:
    """The live bug: 10 resets in one morning on an untouched $1,000.

    blown_out judged the POSITION SIZE, and 5% of $1,000 is $50 against a
    0DTE contract costing $109-$177. So a brand-new run declared bankruptcy
    on its first candidate and reset, forever.
    """
    fresh = {"balance": bankroll.STARTING_BALANCE}
    assert not bankroll.blown_out(fresh, 1.09)
    assert bankroll.contracts_for_trade(fresh, 50.0, 1.77, 0.20) == 1


def test_blown_out_is_about_the_balance_not_the_size() -> None:
    assert bankroll.blown_out({"balance": 80.0}, 1.77)  # can, at 88% of it


def test_percentage_sizing_still_applies_when_it_can_fund_more() -> None:
    """The floor is one contract; it is not a cap."""
    assert bankroll.contracts_for_trade({"balance": 5000.0}, 100.0, 1.00, 0.20) == 5
    assert bankroll.contracts_for_trade({"balance": 5000.0}, 200.0, 1.00, 0.20) == 10


def test_a_genuinely_empty_account_still_resets() -> None:
    """The fix must not remove the reset, only stop it firing on a healthy
    account."""
    assert bankroll.contracts_for_trade({"balance": 10.0}, 0.5, 1.77, 0.20) == 0


def test_a_free_contract_does_not_divide_by_zero() -> None:
    assert not bankroll.blown_out({"balance": 1000.0}, 0.0)
