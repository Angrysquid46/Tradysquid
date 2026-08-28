"""RIPTIDE scheduler: aggressive cadence while market-hours and flat-safe."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

import scoreboard

from .runtime import RiptideRuntime


CENTRAL = ZoneInfo("America/Chicago")


def cycle_allowed(now: datetime, *, has_open_position: bool) -> bool:
    local = now.astimezone(CENTRAL)
    if local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    return 8 * 60 + 35 <= minute <= (15 * 60 + 5 if has_open_position else 14 * 60 + 35)


def build_scheduler(runtime: RiptideRuntime | None = None) -> BackgroundScheduler:
    trader = runtime or RiptideRuntime()
    scheduler = BackgroundScheduler(timezone="America/Chicago")

    def cycle() -> None:
        connection = scoreboard.connect_db()
        try:
            now = datetime.now(CENTRAL)
            open_position = scoreboard.current_position_status(connection, "RIPTIDE") is not None
            if cycle_allowed(now, has_open_position=open_position):
                trader.evaluate(now, connection)
        finally:
            connection.close()

    scheduler.add_job(cycle, "cron", second=35, id="riptide-paper-cycle", max_instances=1, coalesce=True, misfire_grace_time=20)
    return scheduler
