from __future__ import annotations
import tempfile
from pathlib import Path

import bankroll


def test_default_state_starts_at_starting_balance():
    state = bankroll.default_state()
    assert state["balance"] == bankroll.STARTING_BALANCE
    assert state["run_number"] == 1
    assert state["total_resets"] == 0


def test_load_state_returns_default_when_file_missing():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bankroll.json"
        state = bankroll.load_state(path)
        assert state == bankroll.default_state()


def test_save_and_load_round_trips():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bankroll.json"
        state = bankroll.default_state()
        state["balance"] = 1234.56
        bankroll.save_state(path, state)
        loaded = bankroll.load_state(path)
        assert loaded["balance"] == 1234.56


def test_load_state_fails_open_on_corrupt_file():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bankroll.json"
        path.write_text("not valid json{{{", encoding="utf-8")
        assert bankroll.load_state(path) == bankroll.default_state()


def test_position_size_is_a_percent_of_current_balance_not_a_fixed_cap():
    state = bankroll.default_state()
    state["balance"] = 2000.0
    assert bankroll.position_size_dollars(state) == 2000.0 * bankroll.POSITION_SIZE_PCT
    state["balance"] = 100.0
    assert bankroll.position_size_dollars(state) == 100.0 * bankroll.POSITION_SIZE_PCT


def test_contracts_affordable_rounds_down_to_whole_contracts():
    # $150 position, $0.50 premium -> $50/contract -> 3 whole contracts, not 3.0 exactly by luck
    assert bankroll.contracts_affordable(150.0, 0.50) == 3
    # $149 position, $0.50 premium -> 2 whole contracts (2.98 rounds down, never up)
    assert bankroll.contracts_affordable(149.0, 0.50) == 2


def test_contracts_affordable_is_zero_when_position_size_cant_afford_one():
    assert bankroll.contracts_affordable(10.0, 5.00) == 0


def test_contracts_affordable_is_zero_for_a_worthless_or_free_option():
    assert bankroll.contracts_affordable(100.0, 0.0) == 0


def test_debit_entry_subtracts_cost_immediately():
    state = bankroll.default_state()
    updated = bankroll.debit_entry(state, 150.0)
    assert updated["balance"] == bankroll.STARTING_BALANCE - 150.0
    assert state["balance"] == bankroll.STARTING_BALANCE  # original untouched


def test_debit_entry_never_goes_negative_even_if_overdrawn():
    state = bankroll.default_state()
    state["balance"] = 50.0
    updated = bankroll.debit_entry(state, 500.0)
    assert updated["balance"] == 0.0


def test_debit_then_credit_nets_to_the_same_result_as_a_single_pl_update():
    # Buy for $150, sell for $180 later -> net +$30, same as one pl_dollars=30 update.
    state = bankroll.default_state()
    state = bankroll.debit_entry(state, 150.0)
    state = bankroll.credit_exit(state, 180.0)
    assert state["balance"] == bankroll.STARTING_BALANCE + 30.0


def test_credit_exit_tracks_the_peak():
    state = bankroll.default_state()
    state = bankroll.credit_exit(state, 500.0)
    assert state["peak_balance"] == bankroll.STARTING_BALANCE + 500.0
    state = bankroll.credit_exit(state, -200.0)
    # A pullback doesn't erase the peak already reached.
    assert state["peak_balance"] == bankroll.STARTING_BALANCE + 500.0


def test_credit_exit_tracks_all_time_high_across_runs():
    state = bankroll.default_state()
    state = bankroll.credit_exit(state, 800.0)
    assert state["all_time_high_balance"] == bankroll.STARTING_BALANCE + 800.0
    assert state["all_time_high_run"] == 1


def test_credit_exit_resets_on_blowup():
    state = bankroll.default_state()
    state["balance"] = 40.0
    state = bankroll.credit_exit(state, -30.0)  # -> 10.0, below RESET_FLOOR
    assert state["balance"] == bankroll.STARTING_BALANCE
    assert state["run_number"] == 2
    assert state["total_resets"] == 1


def test_credit_exit_does_not_reset_above_the_floor():
    state = bankroll.default_state()
    state["balance"] = 100.0
    state = bankroll.credit_exit(state, -50.0)  # -> 50.0, above RESET_FLOOR
    assert state["balance"] == 50.0
    assert state["run_number"] == 1
    assert state["total_resets"] == 0


def test_reset_preserves_the_all_time_high_from_the_prior_run():
    state = bankroll.default_state()
    state = bankroll.credit_exit(state, 2000.0)  # big win, ATH = 3000
    state["balance"] = 40.0
    state = bankroll.credit_exit(state, -30.0)  # blow up, reset to run 2
    assert state["run_number"] == 2
    assert state["balance"] == bankroll.STARTING_BALANCE
    assert state["all_time_high_balance"] == bankroll.STARTING_BALANCE + 2000.0
    assert state["all_time_high_run"] == 1
