from datetime import datetime
from zoneinfo import ZoneInfo

from bots.riptide.scheduler import build_scheduler, cycle_allowed


def test_riptide_session_window_and_single_job():
    central = ZoneInfo("America/Chicago")
    assert cycle_allowed(datetime(2026, 8, 28, 8, 35, tzinfo=central), has_open_position=False)
    assert not cycle_allowed(datetime(2026, 8, 28, 14, 36, tzinfo=central), has_open_position=False)
    scheduler = build_scheduler()
    assert [job.id for job in scheduler.get_jobs()] == ["riptide-paper-cycle"]
