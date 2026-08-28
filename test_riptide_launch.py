import socket
from datetime import datetime
from zoneinfo import ZoneInfo

from bots.riptide.launch import acquire_instance_lock, current_session_date


def test_riptide_single_instance_lock_rejects_duplicate_process():
    first = acquire_instance_lock(0)
    port = first.getsockname()[1]
    try:
        try:
            acquire_instance_lock(port)
        except OSError:
            pass
        else:
            raise AssertionError("duplicate RIPTIDE lock unexpectedly acquired")
    finally:
        first.close()


def test_riptide_session_date_uses_central_time():
    now = datetime(2026, 8, 28, 4, 30, tzinfo=ZoneInfo("UTC"))
    assert current_session_date(now).isoformat() == "2026-08-27"
