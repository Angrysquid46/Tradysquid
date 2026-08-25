from bots.blacktide.scheduler import build_scheduler


def test_scheduler_is_inert_until_started_and_has_one_coalesced_job():
    scheduler = build_scheduler()
    jobs = scheduler.get_jobs()
    assert scheduler.running is False
    assert [job.id for job in jobs] == ["blacktide-paper-cycle"]
    assert jobs[0].max_instances == 1
    assert jobs[0].coalesce is True
