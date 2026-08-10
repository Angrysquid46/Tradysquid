"""Tests for the economic-calendar provider used only by the SPY Key-Levels
strategy's catalyst check: FRED (structured, authoritative) checked first,
Finnhub news-keyword scan (heuristic fallback) checked second. No network
calls - _fetch_release_dates/_fetch_general_news are monkeypatched so these
stay fast and deterministic, and Finnhub is disabled by default (autouse
fixture) so FRED-only tests can't accidentally pass because of a stray
Fed-speaker headline in the live feed."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import economic_calendar as ec

_REAL_FETCH_GENERAL_NEWS = ec._fetch_general_news


@pytest.fixture(autouse=True)
def _disable_finnhub_by_default(monkeypatch):
    """Every test gets Finnhub fully disabled unless it explicitly wires up
    _fetch_general_news itself - keeps FRED-only tests deterministic."""
    monkeypatch.setattr(ec, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(ec, "_news_cache", None)
    monkeypatch.setattr(ec, "_fetch_general_news", lambda: [])


def _release(release_name: str, days_from_today: int) -> dict:
    when = date.today() + timedelta(days=days_from_today)
    return {"release_id": 1, "release_name": release_name, "date": when.isoformat()}


def _article(headline: str, hours_ago: float) -> dict:
    published = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"headline": headline, "datetime": published.timestamp(), "source": "Test"}


# ---------------------------------------------------------------------------
# FRED
# ---------------------------------------------------------------------------


def test_no_api_key_fails_open(monkeypatch):
    monkeypatch.setattr(ec, "FRED_API_KEY", "")
    monkeypatch.setattr(ec, "_cache", None)
    assert ec._fetch_release_dates() == []
    assert ec.active_or_upcoming_catalyst() is None


def test_fetch_error_fails_open_not_closed(monkeypatch):
    def _boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(ec, "_fetch_release_dates", _boom)
    assert ec.active_or_upcoming_catalyst() is None


def test_low_impact_release_is_ignored(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [_release("CBOE Market Statistics", 0)])
    assert ec.active_or_upcoming_catalyst() is None


def test_high_impact_release_today_is_flagged(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [_release("Employment Situation", 0)])
    result = ec.active_or_upcoming_catalyst()
    assert result is not None
    assert result["title"] == "Employment Situation"
    assert result["days_until"] == 0
    assert result["source"] == "FRED releases/dates"


def test_high_impact_release_outside_window_is_not_flagged(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [_release("Consumer Price Index", 3)])
    assert ec.active_or_upcoming_catalyst(window_days=0) is None
    assert ec.active_or_upcoming_catalyst(window_days=3) is not None


def test_fomc_keyword_matches_case_insensitively(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [_release("FOMC Press Release", 0)])
    result = ec.active_or_upcoming_catalyst()
    assert result["title"] == "FOMC Press Release"


def test_nearest_high_impact_release_wins_when_multiple_qualify(monkeypatch):
    monkeypatch.setattr(
        ec,
        "_fetch_release_dates",
        lambda: [_release("Gross Domestic Product", 2), _release("Consumer Price Index", 0)],
    )
    result = ec.active_or_upcoming_catalyst(window_days=5)
    assert result["title"] == "Consumer Price Index"
    assert result["days_until"] == 0


# ---------------------------------------------------------------------------
# Finnhub news-keyword fallback
# ---------------------------------------------------------------------------


def test_finnhub_fallback_only_runs_when_fred_finds_nothing(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [])
    monkeypatch.setattr(ec, "_fetch_general_news", lambda: [_article("Powell speaks on rate outlook", 0.5)])
    result = ec.active_or_upcoming_catalyst()
    assert result is not None
    assert result["source"] == "Finnhub news keyword match"


def test_fred_hit_takes_precedence_over_finnhub_fallback(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [_release("Consumer Price Index", 0)])
    monkeypatch.setattr(ec, "_fetch_general_news", lambda: [_article("Powell speaks on rate outlook", 0.5)])
    result = ec.active_or_upcoming_catalyst()
    assert result["source"] == "FRED releases/dates"


def test_finnhub_fallback_ignores_headlines_without_fed_keywords(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [])
    monkeypatch.setattr(ec, "_fetch_general_news", lambda: [_article("Oil prices rise on supply concerns", 0.5)])
    assert ec.active_or_upcoming_catalyst() is None


def test_finnhub_fallback_ignores_stale_headlines_outside_lookback(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [])
    monkeypatch.setattr(ec, "_fetch_general_news", lambda: [_article("FOMC minutes released", 12)])
    assert ec.active_or_upcoming_catalyst() is None


def test_finnhub_fallback_picks_the_most_recent_matching_headline(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [])
    monkeypatch.setattr(
        ec,
        "_fetch_general_news",
        lambda: [
            _article("Fed Chair Powell testifies before Congress", 2.0),
            _article("Federal Reserve governor speaks at conference", 0.25),
        ],
    )
    result = ec.active_or_upcoming_catalyst()
    assert result["title"] == "Federal Reserve governor speaks at conference"


def test_finnhub_fallback_fails_open_on_fetch_error(monkeypatch):
    monkeypatch.setattr(ec, "_fetch_release_dates", lambda: [])

    def _boom():
        raise RuntimeError("finnhub down")

    monkeypatch.setattr(ec, "_fetch_general_news", _boom)
    assert ec.active_or_upcoming_catalyst() is None


def test_finnhub_disabled_without_api_key():
    # The autouse fixture replaces _fetch_general_news with a stub, so call
    # the real function directly to confirm IT fails open on a missing key,
    # not just the test double.
    assert _REAL_FETCH_GENERAL_NEWS() == []
