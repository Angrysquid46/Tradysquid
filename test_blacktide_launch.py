import socket
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bots.blacktide.launch import acquire_instance_lock, current_session_date


def test_single_instance_lock_rejects_duplicate_process():
    first = acquire_instance_lock(0)
    port = first.getsockname()[1]
    try:
        with pytest.raises(OSError):
            acquire_instance_lock(port)
    finally:
        first.close()


def test_default_session_date_uses_central_time_not_the_machine_timezone():
    utc = ZoneInfo("UTC")
    # It is still Wednesday evening in Chicago when it is Thursday UTC.
    now = datetime(2026, 8, 27, 4, 30, tzinfo=utc)
    assert current_session_date(now).isoformat() == "2026-08-26"
