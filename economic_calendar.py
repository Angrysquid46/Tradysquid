"""Economic-calendar provider for the SPY Key-Levels/ORB/VWAP strategy.

Standalone module, not shared with any other strategy. Two independent
sources feed active_or_upcoming_catalyst, checked in this order:

1. FRED (Federal Reserve Economic Data) /fred/releases/dates - structured,
   authoritative day-granularity release dates (CPI, the jobs report, GDP,
   FOMC statement day, etc.), gated behind FRED_API_KEY. This has no
   Fed-speaker calendar and no time-of-day - it can only answer "is there a
   high-impact release today," never "how many minutes until it" or
   "is a Fed official speaking."
2. Finnhub /news (general category) - a free-tier endpoint (Finnhub's own
   /calendar/economic requires a paid plan; confirmed by a live 403-style
   "no access" response on a free key before this was written). This is a
   real-time headline feed, not a calendar: it is keyword-matched for
   Fed-speaker-adjacent language (Powell, FOMC, "Fed Chair", etc.) within a
   short recency window. It can only ever tell you a Fed-speaker headline
   was JUST published, never that one is scheduled or approaching - a
   fundamentally weaker, noisier signal than a real calendar, offered only
   because Finnhub's actual calendar endpoint isn't reachable on a free key.

Both fail open, never closed: with no key configured, or on any request/
parse error, active_or_upcoming_catalyst returns None (no catalyst) rather
than raising - a broken or unreachable feed must never silently freeze this
strategy's entries.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
FRED_BASE_URL = "https://api.stlouisfed.org/fred/releases/dates"
SESSION = requests.Session()

# Release-name substrings (case-insensitive) that count as high-impact for
# this strategy's purposes - matches the source spec's examples (Fed
# announcements, major economic releases) without trying to keyword-match
# every one of FRED's ~300 releases, most of which are minor/regional.
HIGH_IMPACT_RELEASE_KEYWORDS = (
    "consumer price index",
    "producer price index",
    "employment situation",
    "gross domestic product",
    "personal income",  # covers "Personal Income and Outlays" (PCE)
    "federal open market committee",
    "fomc",
    "retail sales",
    "advance monthly sales",
)

# Day-based, not minute-based - FRED release dates carry no time-of-day, so
# there is no honest way to report "minutes until." Default 0 means "only
# a release scheduled for today counts."
CATALYST_LOOKAHEAD_DAYS = int(os.environ.get("SPY_KEY_LEVELS_CATALYST_LOOKAHEAD_DAYS", "0"))
_CACHE_TTL_SECONDS = 60 * 60
_cache: tuple[float, list[dict[str, Any]]] | None = None


def _fetch_release_dates() -> list[dict[str, Any]]:
    global _cache
    now = time.time()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]
    if not FRED_API_KEY:
        return []
    today = datetime.now(timezone.utc).date()
    params = {
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "realtime_start": today.isoformat(),
        "realtime_end": (today + timedelta(days=max(CATALYST_LOOKAHEAD_DAYS, 0) + 1)).isoformat(),
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
    }
    try:
        response = SESSION.get(FRED_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return _cache[1] if _cache is not None else []
    releases = payload.get("release_dates", []) if isinstance(payload, dict) else []
    events = [event for event in releases if isinstance(event, dict)]
    _cache = (now, events)
    return events


def _fred_catalyst(window_days: int) -> dict[str, Any] | None:
    try:
        events = _fetch_release_dates()
    except Exception:
        return None
    today = datetime.now(timezone.utc).date()
    best: dict[str, Any] | None = None
    best_days_until: int | None = None
    for event in events:
        release_name = str(event.get("release_name") or "")
        if not any(keyword in release_name.lower() for keyword in HIGH_IMPACT_RELEASE_KEYWORDS):
            continue
        raw_date = event.get("date")
        if not raw_date:
            continue
        try:
            event_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            continue
        days_until = (event_date - today).days
        if 0 <= days_until <= window_days:
            if best_days_until is None or days_until < best_days_until:
                best = {
                    "title": release_name,
                    "impact": "High",
                    "days_until": days_until,
                    "minutes_until": 0 if days_until == 0 else None,
                    "source": "FRED releases/dates",
                }
                best_days_until = days_until
    return best


FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# Headline substrings (case-insensitive) that suggest a Fed official is
# actively speaking or a rate decision is in the news right now - a coarse
# proxy for "Fed speaker," not a confirmed schedule. Deliberately broad
# names/titles rather than narrow phrasing, since headlines vary a lot.
FED_SPEAKER_NEWS_KEYWORDS = (
    "powell", "fomc", "federal reserve", "fed chair", "fed chairman",
    "fed governor", "fed president", "fed official", "fed speaks",
    "fed's", "rate decision", "interest rate decision",
)

# How recent a matching headline has to be to still count as "active" - a
# news article, unlike a calendar entry, has no future schedule to check,
# only a publish time already in the past.
NEWS_LOOKBACK_HOURS = float(os.environ.get("SPY_KEY_LEVELS_NEWS_LOOKBACK_HOURS", "3"))
_NEWS_CACHE_TTL_SECONDS = 10 * 60
_news_cache: tuple[float, list[dict[str, Any]]] | None = None


def _fetch_general_news() -> list[dict[str, Any]]:
    global _news_cache
    now = time.time()
    if _news_cache is not None and now - _news_cache[0] < _NEWS_CACHE_TTL_SECONDS:
        return _news_cache[1]
    if not FINNHUB_API_KEY:
        return []
    try:
        response = SESSION.get(
            FINNHUB_NEWS_URL, params={"category": "general", "token": FINNHUB_API_KEY}, timeout=15
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return _news_cache[1] if _news_cache is not None else []
    articles = [article for article in payload if isinstance(article, dict)] if isinstance(payload, list) else []
    _news_cache = (now, articles)
    return articles


def _finnhub_news_catalyst() -> dict[str, Any] | None:
    try:
        articles = _fetch_general_news()
    except Exception:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    best: dict[str, Any] | None = None
    best_published: datetime | None = None
    for article in articles:
        headline = str(article.get("headline") or "")
        if not any(keyword in headline.lower() for keyword in FED_SPEAKER_NEWS_KEYWORDS):
            continue
        raw_timestamp = article.get("datetime")
        if not raw_timestamp:
            continue
        try:
            published = datetime.fromtimestamp(float(raw_timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        if published < cutoff:
            continue
        if best_published is None or published > best_published:
            best = {
                "title": headline[:140],
                "impact": "Medium (news-based, not a confirmed scheduled event)",
                "days_until": 0,
                "minutes_until": 0,
                "source": "Finnhub news keyword match",
            }
            best_published = published
    return best


def active_or_upcoming_catalyst(window_days: int | None = None) -> dict[str, Any] | None:
    """Checks FRED first (structured, authoritative, day-granularity), then
    falls back to the Finnhub news-keyword scan (real-time but heuristic) if
    FRED found nothing. Returns None if neither source has a hit or both are
    unconfigured/unreachable - never raises, never blocks on a broken feed."""
    window = window_days if window_days is not None else CATALYST_LOOKAHEAD_DAYS
    fred_hit = _fred_catalyst(window)
    if fred_hit is not None:
        return fred_hit
    return _finnhub_news_catalyst()
