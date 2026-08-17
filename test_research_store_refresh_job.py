"""The research store must record each session as it happens.

It had gone five years stale - ending 2021-05-06 while the system traded
2026 - because nothing was recording sessions. That is unrecoverable
damage: no provider sells real 1-minute history beyond about a month, so
any session not captured within that window is gone permanently.

Robinhood makes this worse than a plain gap. Asked for a range past its
retention it returns `interpolated: true` bars - flat price, zero volume -
instead of an error. A probe for May 2026 came back 2,340 bars of which
zero were real. Ingesting those would write a flat, zero-volume week into
the store that nothing downstream would flag.
"""

from __future__ import annotations

import local_information_engine as engine
import spy_research_refresh as srr


def test_interpolated_bars_are_rejected():
    """Robinhood's gap-fill, verified live: 2,340 bars, 0 real."""
    assert srr._is_synthetic({"interpolated": True, "volume": 0}) is True
    assert srr._is_synthetic({"interpolated": False, "volume": 1000}) is False


def test_zero_volume_bars_are_rejected():
    """A regular-hours SPY minute never trades zero shares, so zero volume
    means synthesized even when the flag is absent."""
    assert srr._is_synthetic({"volume": 0}) is True
    assert srr._is_synthetic({"volume": 0.0}) is True
    assert srr._is_synthetic({"volume": 500}) is False


def test_a_synthetic_payload_ingests_nothing():
    """The exact shape Robinhood returned for a range past its retention."""
    flat = [
        {"time": f"2026-05-01T13:{minute:02d}:00", "open": 772.68,
         "high": 772.68, "low": 772.68, "close": 772.68,
         "volume": 0, "interpolated": True}
        for minute in range(30)
    ]
    assert srr._rows_from_timesales(flat) == []


def test_real_bars_still_ingest_alongside_synthetic_ones():
    mixed = [
        {"time": "2026-08-17T09:30:00", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 1000},
        {"time": "2026-08-17T09:31:00", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 0, "interpolated": True},
    ]
    rows = srr._rows_from_timesales(mixed)
    assert [r[1] for r in rows] == ["2026-08-17T09:30:00"]


def test_the_refresh_job_is_scheduled_and_runs_after_the_close():
    """Must not be market_hours_only - the session it needs to record is
    only complete once the market has closed."""
    job = {j.name: j for j in engine.JOBS}["research-store-refresh"]
    assert job.market_hours_only is False
    assert job.background is True
    assert job.interval.total_seconds() <= 6 * 3600


def test_the_job_exists_because_nothing_else_records_sessions():
    names = [j.name for j in engine.JOBS]
    assert "research-store-refresh" in names
