"""Autonomous paper scheduler; importing it never starts a process."""

from __future__ import annotations

from datetime import datetime

import scoreboard
from apscheduler.schedulers.background import BackgroundScheduler

from .runtime import BlacktideRuntime


def build_scheduler(runtime: BlacktideRuntime | None = None) -> BackgroundScheduler:
    trader = runtime or BlacktideRuntime()
    scheduler = BackgroundScheduler(timezone="America/Chicago")

    def cycle() -> None:
        connection = scoreboard.connect_db()
        try:
            trader.evaluate(datetime.now().astimezone(), connection)
        finally:
            connection.close()

    scheduler.add_job(cycle, "cron", second=20, id="blacktide-paper-cycle",
                      max_instances=1, coalesce=True, misfire_grace_time=20)
    return scheduler
