import socket

import pytest

from bots.blacktide.launch import acquire_instance_lock


def test_single_instance_lock_rejects_duplicate_process():
    first = acquire_instance_lock(0)
    port = first.getsockname()[1]
    try:
        with pytest.raises(OSError):
            acquire_instance_lock(port)
    finally:
        first.close()
