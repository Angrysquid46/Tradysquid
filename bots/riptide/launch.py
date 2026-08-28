"""Standalone long-lived RIPTIDE paper process."""

from __future__ import annotations

import argparse
import signal
import socket
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .env_bootstrap import bootstrap

bootstrap()

from .preflight import INSTANCE_PORT, require_ready
from .scheduler import build_scheduler


CENTRAL = ZoneInfo("America/Chicago")


def current_session_date(now: datetime | None = None) -> date:
    return (now or datetime.now(CENTRAL)).astimezone(CENTRAL).date()


def acquire_instance_lock(port: int = INSTANCE_PORT) -> socket.socket:
    lock = socket.socket()
    lock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    lock.bind(("127.0.0.1", port))
    lock.listen(1)
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=date.fromisoformat)
    parser.add_argument("--require-clean-start", action="store_true")
    args = parser.parse_args(argv)
    require_ready(session_date=args.session or current_session_date(), require_clean_start=args.require_clean_start)
    lock, scheduler, stopped = acquire_instance_lock(), build_scheduler(), threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    try:
        scheduler.start()
        stopped.wait()
    finally:
        scheduler.shutdown(wait=True)
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
