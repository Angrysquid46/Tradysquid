"""GROK launch — start the independent paper competitor."""

from __future__ import annotations

import argparse
import logging
import signal
import socket
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bots.grok.preflight import run_preflight
from bots.grok.scheduler import build_runtime, build_scheduler

CENTRAL = ZoneInfo("America/Chicago")
INSTANCE_PORT = 8894  # distinct from other competitors

logger = logging.getLogger("grok.launch")


def current_session_date() -> date:
    return datetime.now(CENTRAL).date()


def acquire_instance_lock(port: int = INSTANCE_PORT) -> socket.socket:
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


def require_ready(session: date, require_clean_start: bool) -> None:
    import scoreboard as sb
    from bots.grok import BOT_NAME

    conn = sb.connect_db()
    try:
        pos = sb.current_position_status(conn, BOT_NAME)
        if require_clean_start and pos is not None:
            raise SystemExit("GROK has an open position; refuse --require-clean-start")
        result = run_preflight(
            scoreboard_available=True,
            market_data_available=True,
            today_0dte_available=True,
            provider_reachable=True,
            no_open_position=(pos is None) if require_clean_start else True,
            session_open=True,
        )
        if not result.ok and require_clean_start:
            raise SystemExit(f"GROK preflight failed: {result.failures}")
        for w in result.warnings:
            logger.warning(w)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GROK independent SPY 0DTE paper competitor")
    parser.add_argument("--session", type=date.fromisoformat, default=None)
    parser.add_argument("--require-clean-start", action="store_true")
    args = parser.parse_args(argv)

    require_ready(args.session or current_session_date(), args.require_clean_start)
    lock = acquire_instance_lock()
    runtime = build_runtime()
    runtime.start()
    scheduler = build_scheduler(runtime)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    logger.info("GROK paper competitor is live on port %s", INSTANCE_PORT)
    try:
        scheduler.start()
        stop.wait()
    finally:
        scheduler.shutdown(wait=True)
        runtime.stop()
        lock.close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
