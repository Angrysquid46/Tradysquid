from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
import scoreboard
from .runtime import SurgeRuntime
CENTRAL=ZoneInfo("America/Chicago")
def cycle_allowed(now,has_open_position):
    local=now.astimezone(CENTRAL);minute=local.hour*60+local.minute
    return local.weekday()<5 and 8*60+35<=minute<=(15*60+5 if has_open_position else 14*60+35)
def build_scheduler(runtime=None):
    trader=runtime or SurgeRuntime();scheduler=BackgroundScheduler(timezone="America/Chicago")
    def cycle():
        c=scoreboard.connect_db()
        try:
            now=datetime.now(CENTRAL);cycle_open=scoreboard.current_position_status(c,"SURGE") is not None
            if cycle_allowed(now,cycle_open):trader.evaluate(now,c)
        finally:c.close()
    scheduler.add_job(cycle,"cron",second=50,id="surge-paper-cycle",max_instances=1,coalesce=True,misfire_grace_time=20);return scheduler
