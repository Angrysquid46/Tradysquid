from __future__ import annotations

import os
import subprocess
import sys
import pytest

import market_api_budget as budget


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "DB_PATH", tmp_path / "budget.db")
    budget.reset_for_test()
    yield
    budget.reset_for_test()


class FakeResponse:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_record_response_headers_parses_real_shaped_response():
    response = FakeResponse({
        "X-Ratelimit-Allowed": "120", "X-Ratelimit-Used": "1",
        "X-Ratelimit-Available": "119", "X-Ratelimit-Expiry": "1787593740000",
    })
    state = budget.record_response_headers(response)
    assert state == {"allowed": 120, "used": 1, "available": 119, "expiry": 1787593740000}
    assert budget.current_state() == state


def test_record_response_headers_returns_none_when_headers_missing():
    response = FakeResponse({})
    assert budget.record_response_headers(response) is None
    assert budget.current_state() is None


def test_record_response_headers_returns_none_for_malformed_values():
    response = FakeResponse({
        "X-Ratelimit-Allowed": "not-a-number", "X-Ratelimit-Used": "1",
        "X-Ratelimit-Available": "119", "X-Ratelimit-Expiry": "1787593740000",
    })
    assert budget.record_response_headers(response) is None


def test_record_response_headers_handles_object_with_no_headers_attribute():
    assert budget.record_response_headers(object()) is None


# --- request_allowed ---------------------------------------------------------

ALWAYS_ALLOWED_PRIORITIES = [
    budget.PRIORITY_OPEN_POSITION_SAFETY,
    budget.PRIORITY_EXIT_CRITICAL_DATA,
    budget.PRIORITY_ENTRY_CRITICAL_DATA,
]
GATED_PRIORITIES = [
    budget.PRIORITY_SHARED_SPY_OBSERVATIONS,
    budget.PRIORITY_SHARED_OPTIONS_COLLECTION,
    budget.PRIORITY_SECONDARY_CONTEXT,
    budget.PRIORITY_NONESSENTIAL_RESEARCH,
    budget.PRIORITY_RIVALRY_PRESENTATION,
]


def _set_available_fraction(fraction: float) -> None:
    allowed = 120
    available = int(allowed * fraction)
    budget.record_response_headers(FakeResponse({
        "X-Ratelimit-Allowed": str(allowed),
        "X-Ratelimit-Used": str(allowed - available),
        "X-Ratelimit-Available": str(available),
        "X-Ratelimit-Expiry": "1787593740000",
    }))


def test_priorities_one_through_three_cannot_fabricate_provider_capacity():
    _set_available_fraction(0.0)
    for priority in ALWAYS_ALLOWED_PRIORITIES:
        assert budget.request_allowed(priority) is False


def test_all_priorities_allowed_when_no_telemetry_recorded_yet():
    for priority in ALWAYS_ALLOWED_PRIORITIES + GATED_PRIORITIES:
        assert budget.request_allowed(priority) is True


def test_gated_priorities_allowed_with_plenty_of_budget():
    _set_available_fraction(0.9)
    for priority in GATED_PRIORITIES:
        assert budget.request_allowed(priority) is True


def test_shared_observation_priorities_blocked_below_twenty_percent():
    _set_available_fraction(0.1)
    assert budget.request_allowed(budget.PRIORITY_SHARED_SPY_OBSERVATIONS) is False
    assert budget.request_allowed(budget.PRIORITY_SHARED_OPTIONS_COLLECTION) is False


def test_shared_observation_priorities_preserve_final_twenty_percent():
    _set_available_fraction(0.20)
    assert budget.request_allowed(budget.PRIORITY_SHARED_SPY_OBSERVATIONS) is False


def test_secondary_priorities_blocked_below_forty_percent_but_shared_observations_still_allowed():
    _set_available_fraction(0.3)
    assert budget.request_allowed(budget.PRIORITY_SHARED_SPY_OBSERVATIONS) is True
    assert budget.request_allowed(budget.PRIORITY_SECONDARY_CONTEXT) is False
    assert budget.request_allowed(budget.PRIORITY_NONESSENTIAL_RESEARCH) is False
    assert budget.request_allowed(budget.PRIORITY_RIVALRY_PRESENTATION) is False


def test_secondary_priorities_preserve_final_forty_percent():
    _set_available_fraction(0.40)
    for priority in (
        budget.PRIORITY_SECONDARY_CONTEXT,
        budget.PRIORITY_NONESSENTIAL_RESEARCH,
        budget.PRIORITY_RIVALRY_PRESENTATION,
    ):
        assert budget.request_allowed(priority) is False


def test_cross_process_reservations_are_atomic(tmp_path):
    shared = tmp_path / "cross-process.db"
    monkey_headers = FakeResponse({
        "X-Ratelimit-Allowed": "10", "X-Ratelimit-Used": "0",
        "X-Ratelimit-Available": "10", "X-Ratelimit-Expiry": "1787593740000",
    })
    original = budget.DB_PATH
    budget.DB_PATH = shared
    try:
        budget.record_response_headers(monkey_headers)
    finally:
        budget.DB_PATH = original
    code = (
        "import market_api_budget as b; "
        "print(sum(b.request_allowed(b.PRIORITY_OPEN_POSITION_SAFETY) for _ in range(8)))"
    )
    env = dict(os.environ, TRADYSQUID_API_BUDGET_DB=str(shared))
    processes = [subprocess.Popen(
        [sys.executable, "-c", code], cwd=os.getcwd(),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for _ in range(2)]
    totals = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        totals.append(int(stdout.strip()))
    assert sum(totals) == 10
