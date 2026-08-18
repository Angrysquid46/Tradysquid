"""Tests for the 2021-2026 backfill.

The whole design exists because the provider meters requests: roughly 62
months are missing and a free tier allows a handful of calls a day, so no
single run can finish. A backfill that forgets what it already pulled
would spend its entire quota re-fetching the same months forever and never
close the gap.

The other half is trust. Robinhood returned 2,340 consecutive synthetic
bars - flat price, zero volume - for a range past its retention, with no
error. Nothing may reach the store until it has been checked against bars
we already have.
"""

from __future__ import annotations

import sqlite3

import pytest

import spy_gap_backfill as gb


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE minute_bars (ticker TEXT, bar_time TEXT, open REAL, "
        "high REAL, low REAL, close REAL, volume REAL, bar_count REAL, "
        "average REAL, regular_session INTEGER, PRIMARY KEY (ticker, bar_time))"
    )
    # A known-good March 2021 to verify a provider against.
    for minute in range(200):
        hh, mm = divmod(9 * 60 + 30 + minute, 60)
        c.execute(
            "INSERT INTO minute_bars VALUES ('SPY',?,?,?,?,?,?,NULL,NULL,1)",
            (f"2021-03-01T{hh:02d}:{mm:02d}:00", 390.0, 390.5, 389.5,
             390.0 + minute * 0.01, 1000),
        )
    c.commit()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path=None):
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(gb, "STATE_PATH",
                            pathlib.Path(d) / "gap-backfill.json")
        yield


def _bars(day="2021-03-01", n=200, flat=False, volume=1000):
    out = []
    for minute in range(n):
        hh, mm = divmod(9 * 60 + 30 + minute, 60)
        out.append({
            "bar_time": f"{day}T{hh:02d}:{mm:02d}:00",
            "open": 390.0, "high": 390.5, "low": 389.5,
            "close": 390.0 if flat else 390.0 + minute * 0.01,
            "volume": volume,
        })
    return out


# ---------------------------------------------------------------------------
# Resumability - the reason a daily cap is survivable
# ---------------------------------------------------------------------------

def test_months_are_pulled_newest_first():
    """A run that stops early must still have delivered the months closest
    to the regime being traded."""
    pending = gb.pending_months({"done": []})
    assert pending[0] == gb.GAP_LAST_MONTH
    assert pending[-1] == gb.GAP_FIRST_MONTH
    assert pending == sorted(pending, reverse=True)


def test_completed_months_are_never_fetched_again():
    """Without this the quota is spent re-fetching the same months every
    day and the gap never closes."""
    every = gb.months_between(gb.GAP_FIRST_MONTH, gb.GAP_LAST_MONTH)
    done = every[-10:]
    pending = gb.pending_months({"done": done})
    assert not (set(pending) & set(done))
    assert len(pending) == len(every) - 10


def test_the_gap_is_the_expected_size():
    every = gb.months_between(gb.GAP_FIRST_MONTH, gb.GAP_LAST_MONTH)
    assert 60 <= len(every) <= 65, len(every)


def test_a_rate_limit_stops_the_run_cleanly_and_keeps_progress(conn, monkeypatch):
    """Hitting the cap is the expected outcome, not a failure - progress so
    far must survive it."""
    calls = {"n": 0}

    def _fetch(month):
        calls["n"] += 1
        if calls["n"] > 3:
            raise gb.RateLimited("5 calls per day")
        return _bars(day=f"{month}-01")

    monkeypatch.setattr(gb, "verify_against_store", lambda *a, **k: {"ok": True})
    result = gb.backfill(conn, _fetch, max_months=25, build_features=False)

    assert "rate limited" in result.stopped_because
    # One call is spent proving the provider against a known month before
    # any write, so three allowed calls complete two months.
    assert len(result.months_done) == 2
    assert gb.read_state()["done"] == sorted(result.months_done)
    assert result.remaining > 0


def test_a_second_run_continues_where_the_first_stopped(conn, monkeypatch):
    monkeypatch.setattr(gb, "verify_against_store", lambda *a, **k: {"ok": True})
    seen: list[str] = []

    def _fetch(month):
        seen.append(month)
        if len(seen) > 2:
            raise gb.RateLimited("quota")
        return _bars(day=f"{month}-01")

    gb.backfill(conn, _fetch, max_months=25, build_features=False)
    completed = set(gb.read_state()["done"])
    seen.clear()
    gb.backfill(conn, _fetch, max_months=25, build_features=False)

    assert completed, "the first run completed nothing"
    assert not (completed & set(seen)), "a COMPLETED month was fetched again"
    # A month that was attempted but cut off mid-run is not complete, so
    # retrying it is correct - only finished work may be skipped.


def test_one_bad_month_does_not_abort_the_whole_backfill(conn, monkeypatch):
    monkeypatch.setattr(gb, "verify_against_store", lambda *a, **k: {"ok": True})

    def _fetch(month):
        if month.endswith("-06"):
            raise RuntimeError("provider hiccup")
        return _bars(day=f"{month}-01")

    result = gb.backfill(conn, _fetch, max_months=5, build_features=False)
    assert len(result.months_done) >= 3
    assert gb.read_state()["failed"], "the failing month was not recorded"


# ---------------------------------------------------------------------------
# Trust - nothing is written until it is checked
# ---------------------------------------------------------------------------

def test_synthetic_bars_are_detected():
    """The exact shape Robinhood returned past its retention."""
    assert gb.looks_synthetic(_bars(flat=True, volume=0)) is True
    assert gb.looks_synthetic(_bars(flat=True, volume=1000)) is True
    assert gb.looks_synthetic(_bars(volume=0)) is True
    assert gb.looks_synthetic(_bars()) is False


def test_a_provider_matching_the_store_verifies(conn):
    check = gb.verify_against_store(conn, "2021-03", _bars())
    assert check["compared"] >= 100
    assert check["worst_diff_pct"] < 0.5


def test_a_provider_disagreeing_with_the_store_is_rejected(conn):
    wrong = [dict(b, close=b["close"] * 1.05) for b in _bars()]
    with pytest.raises(gb.SuspectData, match="disagrees"):
        gb.verify_against_store(conn, "2021-03", wrong)


def test_synthetic_data_is_rejected_before_any_write(conn):
    with pytest.raises(gb.SuspectData, match="synthetic"):
        gb.verify_against_store(conn, "2021-03", _bars(flat=True, volume=0))


def test_too_little_overlap_is_rejected_rather_than_assumed_good(conn):
    with pytest.raises(gb.SuspectData, match="too few"):
        gb.verify_against_store(conn, "2021-03", _bars(n=40))


def test_nothing_is_written_when_verification_fails(conn, monkeypatch):
    """The check is worthless if the rows land anyway."""
    before = conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]

    def _fetch(month):
        return _bars(flat=True, volume=0)

    result = gb.backfill(conn, _fetch, max_months=3, build_features=False)
    after = conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
    assert after == before
    assert result.bars_written == 0


def test_an_entitlement_gap_is_not_reported_as_a_rate_limit(conn, monkeypatch):
    """Verified live: Alpha Vantage's free tier answers "This is a premium
    endpoint" for every intraday shape, including outputsize=compact. A
    rate limit clears on its own; an entitlement gap never does. Conflating
    them would leave the backfill claiming forever that it is waiting for
    quota that will never arrive."""
    def _fetch(month):
        raise gb.NotEntitled("This is a premium endpoint")

    result = gb.backfill(conn, _fetch, max_months=5, build_features=False)
    assert "not entitled" in result.stopped_because
    assert "rate limited" not in result.stopped_because
    assert result.bars_written == 0
    assert result.remaining > 0


def test_a_premium_response_is_classified_as_not_entitled(monkeypatch):
    import spy_gap_backfill as g

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"Information": "Thank you for using Alpha Vantage! "
                                   "This is a premium endpoint. You may subscribe..."}

    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "x")
    monkeypatch.setattr(g, "__name__", g.__name__)
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    with pytest.raises(g.NotEntitled):
        g.fetch_month_alphavantage("2021-03")


def test_a_throttle_response_is_still_a_rate_limit(monkeypatch):
    import spy_gap_backfill as g

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"Note": "Please consider spreading out your free API "
                            "requests more sparingly."}

    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "x")
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    with pytest.raises(g.RateLimited):
        g.fetch_month_alphavantage("2021-03")
