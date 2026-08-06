"""Tests for the self-healing lock-port acquisition. Before this, a stale
process left holding the lock port (the single most common startup failure
tonight) meant the whole point of a one-click launcher was defeated - it
would wait forever, every 10 seconds, for a human to go run a separate
PowerShell cleanup script. Now it tries to clear the holder itself once,
and only falls back to "already running" if that genuinely doesn't help."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

import tradysquid_supervisor as supervisor


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class SelfHealingLockPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_port = supervisor.LOCK_PORT
        supervisor.LOCK_PORT = _free_port()

    def tearDown(self) -> None:
        supervisor.LOCK_PORT = self.original_port

    def test_binds_immediately_when_nothing_holds_the_port(self) -> None:
        with patch.object(supervisor, "_clear_stale_port_holder") as clear_mock:
            listener = supervisor.acquire_instance_lock()
        listener.close()
        clear_mock.assert_not_called()

    def test_clears_a_stale_holder_and_retries_successfully(self) -> None:
        occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupier.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        occupier.bind((supervisor.LOCK_HOST, supervisor.LOCK_PORT))
        occupier.listen(1)

        def fake_clear() -> bool:
            # Simulates the stale process actually being killed: the port
            # becomes free as a side effect, same as in real use.
            occupier.close()
            return True

        with patch.object(supervisor, "_clear_stale_port_holder", side_effect=fake_clear):
            listener = supervisor.acquire_instance_lock()
        listener.close()

    def test_raises_if_nothing_was_found_to_clear(self) -> None:
        occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupier.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        occupier.bind((supervisor.LOCK_HOST, supervisor.LOCK_PORT))
        occupier.listen(1)
        try:
            with patch.object(supervisor, "_clear_stale_port_holder", return_value=False):
                with self.assertRaises(RuntimeError):
                    supervisor.acquire_instance_lock()
        finally:
            occupier.close()

    def test_raises_if_the_port_is_still_held_after_a_clear_attempt(self) -> None:
        # A genuinely live, healthy second instance racing to start at the
        # same moment: clearing "succeeds" (nothing wrong happened) but the
        # port is still legitimately in use, so this must still back off
        # safely rather than fighting a real concurrent instance.
        occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupier.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        occupier.bind((supervisor.LOCK_HOST, supervisor.LOCK_PORT))
        occupier.listen(1)
        try:
            with patch.object(supervisor, "_clear_stale_port_holder", return_value=True):
                with self.assertRaises(RuntimeError):
                    supervisor.acquire_instance_lock()
        finally:
            occupier.close()


if __name__ == "__main__":
    unittest.main()
