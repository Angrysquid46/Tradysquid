"""GROK paper cycle scheduler."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

import scoreboard
from bots.grok import BOT_NAME
from bots.grok.market_adapter import GrokMarketAdapter
from bots.grok.runtime import GrokRuntime

CENTRAL = ZoneInfo("America/Chicago")


def cycle_allowed(now: datetime, has_open_position: bool) -> bool:
    local = now.replace(tzinfo=CENTRAL) if now.tzinfo is None else now.astimezone(CENTRAL)
    minute = local.hour * 60 + local.minute
    if local.weekday() >= 5:
        return False
    # Allow management later when a position is open
    end = 15 * 60 + 5 if has_open_position else 14 * 60 + 35
    return 8 * 60 + 35 <= minute <= end


def build_runtime() -> GrokRuntime:
    adapter = GrokMarketAdapter()
    # APScheduler executes cycle() on a worker thread. This connection belongs
    # to the long-lived runtime and therefore must explicitly permit that
    # operational handoff; short-lived scheduler bookkeeping connections stay
    # thread-bound below.
    conn = scoreboard.connect_db(check_same_thread=False)
    return GrokRuntime(
        scoreboard_conn=conn,
        get_features=adapter.features,
        get_chain=adapter.chain,
        get_underlying=adapter.underlying,
        is_session_open=adapter.is_session_open,
        minutes_to_close=adapter.minutes_to_close,
        provider_ok=adapter.provider_ok,
    )


def build_scheduler(runtime: GrokRuntime | None = None) -> BackgroundScheduler:
    trader = runtime or build_runtime()
    scheduler = BackgroundScheduler(timezone="America/Chicago")

    def cycle() -> None:
        c = scoreboard.connect_db()
        try:
            now = datetime.now(CENTRAL)
            open_pos = scoreboard.current_position_status(c, BOT_NAME) is not None
            if cycle_allowed(now, open_pos):
                trader.cycle()
        finally:
            c.close()

    scheduler.add_job(
        cycle,
        "cron",
        second=50,
        id="grok-paper-cycle",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=20,
    )
    return scheduler
