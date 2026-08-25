from datetime import datetime
from zoneinfo import ZoneInfo

from bots.blacktide.scheduler import build_scheduler, cycle_allowed


def test_scheduler_is_inert_until_started_and_has_one_coalesced_job():
    scheduler = build_scheduler()
    jobs = scheduler.get_jobs()
    assert scheduler.running is False
    assert [job.id for job in jobs] == ["blacktide-paper-cycle"]
    assert jobs[0].max_instances == 1
    assert jobs[0].coalesce is True


def test_closed_market_and_late_entries_are_blocked_but_open_trade_gets_exit_window():
    ct = ZoneInfo("America/Chicago")
    assert cycle_allowed(datetime(2026, 8, 26, 8, 29, tzinfo=ct), has_open_position=False) is False
    assert cycle_allowed(datetime(2026, 8, 26, 10, 0, tzinfo=ct), has_open_position=False) is True
    assert cycle_allowed(datetime(2026, 8, 26, 14, 21, tzinfo=ct), has_open_position=False) is False
    assert cycle_allowed(datetime(2026, 8, 26, 15, 1, tzinfo=ct), has_open_position=True) is True
    assert cycle_allowed(datetime(2026, 8, 26, 15, 6, tzinfo=ct), has_open_position=True) is False
    assert cycle_allowed(datetime(2026, 8, 29, 10, 0, tzinfo=ct), has_open_position=True) is False
