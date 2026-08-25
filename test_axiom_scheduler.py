"""Real tests for scheduler.py's due()/interval/market-hours logic and
single-instance lock port - its own separate implementation, not imported
from local_information_engine.py, on its own port (never 8765/8081/8876)."""

from __future__ import annotations

import socket
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import bots.claude.scheduler as scheduler


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _db(tmp_path):
    scheduler.DB_PATH = tmp_path / "axiom-test.db"
    return scheduler.connect_db()


def test_job_is_due_when_never_run(tmp_path):
    conn = _db(tmp_path)
    job = scheduler.Job("test-job", timedelta(minutes=5), lambda c: "ok")
    assert scheduler.due(conn, job, datetime(2026, 8, 25, 10, 0, 0)) is True


def test_job_is_not_due_before_its_interval_elapses(tmp_path):
    conn = _db(tmp_path)
    job = scheduler.Job("test-job", timedelta(minutes=5), lambda c: "ok")
    scheduler.set_state(conn, "job:test-job", "2026-08-25T10:00:00")
    assert scheduler.due(conn, job, datetime(2026, 8, 25, 10, 2, 0)) is False


def test_job_is_due_after_its_interval_elapses(tmp_path):
    conn = _db(tmp_path)
    job = scheduler.Job("test-job", timedelta(minutes=5), lambda c: "ok")
    scheduler.set_state(conn, "job:test-job", "2026-08-25T10:00:00")
    assert scheduler.due(conn, job, datetime(2026, 8, 25, 10, 6, 0)) is True


def test_market_hours_only_job_blocked_when_market_closed(tmp_path):
    conn = _db(tmp_path)
    job = scheduler.Job("test-job", timedelta(seconds=1), lambda c: "ok", market_hours_only=True)
    with patch.object(scheduler.market_data, "market_is_open_now", return_value=(False, None)):
        assert scheduler.due(conn, job, datetime(2026, 8, 25, 20, 0, 0)) is False


def test_market_hours_only_job_allowed_when_market_open(tmp_path):
    conn = _db(tmp_path)
    job = scheduler.Job("test-job", timedelta(seconds=1), lambda c: "ok", market_hours_only=True)
    with patch.object(scheduler.market_data, "market_is_open_now", return_value=(True, None)):
        assert scheduler.due(conn, job, datetime(2026, 8, 25, 10, 0, 0)) is True


def test_run_job_records_error_state_without_raising(tmp_path):
    conn = _db(tmp_path)

    def _boom(c):
        raise RuntimeError("boom")

    job = scheduler.Job("failing-job", timedelta(seconds=1), _boom)
    result = scheduler.run_job(conn, job)
    assert "ERROR" in result
    assert scheduler.get_state(conn, "job-error:failing-job") == "1"


def test_lock_port_is_never_a_port_another_repo_process_owns():
    assert scheduler.LOCK_PORT not in (8765, 8081, 8876)


class TestLockPort:
    def setup_method(self) -> None:
        self.original_port = scheduler.LOCK_PORT
        scheduler.LOCK_PORT = _free_port()

    def teardown_method(self) -> None:
        scheduler.LOCK_PORT = self.original_port

    def test_second_instance_fails_to_acquire_lock(self) -> None:
        first = scheduler.acquire_instance_lock()
        try:
            with pytest.raises(RuntimeError):
                scheduler.acquire_instance_lock()
        finally:
            first.close()
