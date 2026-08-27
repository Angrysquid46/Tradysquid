"""Standalone BLACKTIDE paper-competition process."""

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
    """Return today's exchange-session date in Central time.

    The process is intentionally long-lived: its scheduler decides on every
    weekday cycle whether the 8:30 AM–3:00 PM CT window is open.  A launch
    date is only needed for preflight's same-day-expiration check, so callers
    should never need to restart it merely because the calendar changed.
    """
    return (now or datetime.now(CENTRAL)).astimezone(CENTRAL).date()


def acquire_instance_lock(port: int = INSTANCE_PORT) -> socket.socket:
    lock = socket.socket()
    lock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    lock.bind(("127.0.0.1", port))
    lock.listen(1)
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session",
        type=date.fromisoformat,
        help="optional ISO date for a manual preflight; defaults to today in America/Chicago",
    )
    parser.add_argument("--require-clean-start", action="store_true")
    args = parser.parse_args(argv)
    session_date = args.session or current_session_date()
    require_ready(session_date=session_date, require_clean_start=args.require_clean_start)
    lock = acquire_instance_lock()
    scheduler = build_scheduler()
    stopped = threading.Event()

    def stop(*_args) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        scheduler.start()
        stopped.wait()
    finally:
        scheduler.shutdown(wait=True)
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
