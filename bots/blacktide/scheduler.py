"""Autonomous paper scheduler; importing it never starts a process."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .env_bootstrap import bootstrap

bootstrap()

import scoreboard
from apscheduler.schedulers.background import BackgroundScheduler

from .runtime import BlacktideRuntime

CENTRAL = ZoneInfo("America/Chicago")


def cycle_allowed(now: datetime, *, has_open_position: bool) -> bool:
    local = now.astimezone(CENTRAL)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    if has_open_position:
        return 8 * 60 + 30 <= minutes <= 15 * 60 + 5
    # No new position late enough that the 35-minute maximum hold would
    # require an exit after the regular session.
    return 8 * 60 + 30 <= minutes <= 14 * 60 + 20


def build_scheduler(runtime: BlacktideRuntime | None = None) -> BackgroundScheduler:
    trader = runtime or BlacktideRuntime()
    scheduler = BackgroundScheduler(timezone="America/Chicago")

    def cycle() -> None:
        connection = scoreboard.connect_db()
        try:
            now = datetime.now(CENTRAL)
            has_open = scoreboard.current_position_status(connection, "BLACKTIDE") is not None
            if cycle_allowed(now, has_open_position=has_open):
                trader.evaluate(now, connection)
        finally:
            connection.close()

    scheduler.add_job(cycle, "cron", second=20, id="blacktide-paper-cycle",
                      max_instances=1, coalesce=True, misfire_grace_time=20)
    return scheduler
