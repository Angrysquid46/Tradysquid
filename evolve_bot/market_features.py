"""Phase 3 feature sources for the evolve bot - VIX, market sentiment, and
put/call ratio, wired into the same feature set for both live entries
(engine.py) and historical backtest rows (backtest.py) so the model trains
on the same shape of data it will see live.

Follows economic_calendar.py's established pattern for this codebase: fail
open, never closed - a missing API key or a request/parse error returns
None (or an empty series), never raises, so a broken free-tier feed can
never block or crash a scan cycle or a backtest run.

Sources:
- VIX: FRED's VIXCLS series (CBOE Volatility Index daily close), gated
  behind FRED_API_KEY (already configured, confirmed live 2026-08-12).
  Confirmed this covers the entire real-data backtest window
  (2026-07-06 to 2026-08-11) with real daily values, not synthetic.
- Sentiment: Finnhub's /company-news endpoint for symbol=SPY, gated behind
  FINNHUB_API_KEY. Unlike the /news general-category endpoint
  economic_calendar.py uses (which only returns recent headlines),
  company-news accepts a real from/to date range and returns real
  historical headlines even on a free key - confirmed live 2026-08-12
  (62 real SPY-relevant headlines for 2026-07-06 alone). Scored locally
  with VADER (vaderSentiment package, bundled lexicon, no network call at
  scoring time, no per-trade LLM cost) - mean compound score across that
  day's headlines, range -1 (bearish) to +1 (bullish).
- Put/call ratio: NOT a new data source - computed directly from a chain
  already fetched by the caller (engine.py already calls get_chain for
  candidate selection). Live-only: there is no historical chain data for
  an expired SPY expiration (confirmed repeatedly this session), so
  backtest rows leave this field blank rather than fabricating a number -
  a documented gap, not an oversight.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"
SESSION = requests.Session()
_ANALYZER = SentimentIntensityAnalyzer()

_VIX_CACHE_TTL_SECONDS = 60 * 60
_vix_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}

_SENTIMENT_CACHE_TTL_SECONDS = 10 * 60
_sentiment_headline_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def fetch_vix_series(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Real FRED VIXCLS observations between start_date and end_date
    (inclusive, YYYY-MM-DD). Cached per (start_date, end_date) pair, not
    as one shared value - the backtest calls this once per trading_day
    with a DIFFERENT range each time, and an unkeyed cache silently
    returned the first day's series for every subsequent day (caught by
    inspecting real backtest output: every row showed the identical VIX
    value regardless of trading_day)."""
    global _vix_cache
    cache_key = (start_date, end_date)
    now = time.time()
    cached = _vix_cache.get(cache_key)
    if cached is not None and now - cached[0] < _VIX_CACHE_TTL_SECONDS:
        return cached[1]
    if not FRED_API_KEY:
        return []
    try:
        response = SESSION.get(
            FRED_OBSERVATIONS_URL,
            params={
                "series_id": "VIXCLS",
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return cached[1] if cached is not None else []
    observations = payload.get("observations", []) if isinstance(payload, dict) else []
    values = [obs for obs in observations if isinstance(obs, dict)]
    _vix_cache[cache_key] = (now, values)
    return values


def vix_on_or_before(as_of_date: str, series: list[dict[str, Any]]) -> float | None:
    """Most recent VIX close at or before as_of_date (YYYY-MM-DD). VIX
    doesn't publish on weekends/holidays and FRED sometimes lags a
    session, so this walks backward through the series rather than
    requiring an exact date match. Returns None if nothing qualifies or
    the series has no parseable value (FRED uses the literal string "."
    for a missing observation, not an absence of the row)."""
    best_date: str | None = None
    best_value: float | None = None
    for obs in series:
        obs_date = str(obs.get("date") or "")
        if not obs_date or obs_date > as_of_date:
            continue
        raw_value = obs.get("value")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if best_date is None or obs_date > best_date:
            best_date, best_value = obs_date, value
    return best_value


def _fetch_company_news(as_of_date: str) -> list[dict[str, Any]]:
    cache_key = as_of_date
    cached = _sentiment_headline_cache.get(cache_key)
    now = time.time()
    if cached is not None and now - cached[0] < _SENTIMENT_CACHE_TTL_SECONDS:
        return cached[1]
    if not FINNHUB_API_KEY:
        return []
    try:
        response = SESSION.get(
            FINNHUB_COMPANY_NEWS_URL,
            params={"symbol": "SPY", "from": as_of_date, "to": as_of_date, "token": FINNHUB_API_KEY},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return cached[1] if cached is not None else []
    articles = [article for article in payload if isinstance(article, dict)] if isinstance(payload, list) else []
    _sentiment_headline_cache[cache_key] = (now, articles)
    return articles


def market_sentiment_for_date(as_of_date: str) -> float | None:
    """Mean VADER compound sentiment (-1 to +1) across that date's real
    SPY-related headlines from Finnhub. None if there's no key, no
    headlines, or the request/parse fails - a missing sentiment reading is
    not the same as a neutral (0.0) one, so this never guesses a number in
    place of "unknown"."""
    try:
        articles = _fetch_company_news(as_of_date)
    except Exception:
        return None
    scores = []
    for article in articles:
        headline = str(article.get("headline") or "").strip()
        if not headline:
            continue
        scores.append(_ANALYZER.polarity_scores(headline)["compound"])
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def market_sentiment_now() -> float | None:
    """Today's sentiment reading, as of the current moment - the live
    entry-time equivalent of market_sentiment_for_date."""
    today = datetime.now(timezone.utc).date().isoformat()
    return market_sentiment_for_date(today)


def put_call_ratio_from_chain(chain: list[dict[str, Any]]) -> float | None:
    """Total put volume / total call volume from an ALREADY-FETCHED chain
    - no network call here, matching the roadmap's "from chain data
    already fetched" design. Falls back to an open-interest-based ratio
    when volume is all zero (illiquid/off-hours chain snapshot), and
    returns None (not 0 or 1) when neither side has any real data to
    compute a ratio from - a missing reading, not a fabricated neutral
    one."""
    call_volume = put_volume = 0
    call_oi = put_oi = 0
    for option in chain:
        kind = option.get("option_type")
        volume = int(option.get("volume") or 0)
        open_interest = int(option.get("open_interest") or 0)
        if kind == "call":
            call_volume += volume
            call_oi += open_interest
        elif kind == "put":
            put_volume += volume
            put_oi += open_interest
    if call_volume > 0:
        return round(put_volume / call_volume, 4)
    if call_oi > 0:
        return round(put_oi / call_oi, 4)
    return None
