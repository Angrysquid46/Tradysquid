from __future__ import annotations
from unittest import mock

import market_features as mf


def test_vix_on_or_before_finds_the_most_recent_prior_value():
    series = [
        {"date": "2026-07-01", "value": "16.59"},
        {"date": "2026-07-02", "value": "16.15"},
        {"date": "2026-07-06", "value": "15.90"},
    ]
    assert mf.vix_on_or_before("2026-07-06", series) == 15.90


def test_vix_on_or_before_skips_weekend_gap_and_uses_last_prior_trading_day():
    series = [
        {"date": "2026-07-01", "value": "16.59"},
        {"date": "2026-07-02", "value": "16.15"},
    ]
    # 2026-07-04 is a weekend/no-publish day - should fall back to 07-02.
    assert mf.vix_on_or_before("2026-07-04", series) == 16.15


def test_vix_on_or_before_returns_none_when_nothing_qualifies():
    series = [{"date": "2026-08-01", "value": "15.0"}]
    assert mf.vix_on_or_before("2026-07-01", series) is None


def test_vix_on_or_before_skips_fred_missing_value_marker():
    series = [
        {"date": "2026-07-01", "value": "."},
        {"date": "2026-06-30", "value": "17.0"},
    ]
    assert mf.vix_on_or_before("2026-07-01", series) == 17.0


def test_fetch_vix_series_returns_empty_without_an_api_key():
    with mock.patch.object(mf, "FRED_API_KEY", ""), mock.patch.object(mf, "_vix_cache", {}):
        assert mf.fetch_vix_series("2026-07-01", "2026-07-10") == []


def test_fetch_vix_series_fails_open_on_request_error():
    with (
        mock.patch.object(mf, "FRED_API_KEY", "fake-key"),
        mock.patch.object(mf, "_vix_cache", {}),
        mock.patch.object(mf.SESSION, "get", side_effect=mf.requests.RequestException("boom")),
    ):
        assert mf.fetch_vix_series("2026-07-01", "2026-07-10") == []


def test_fetch_vix_series_caches_separately_per_date_range():
    """Regression guard for the caching bug found in real backtest output:
    two different (start, end) ranges must not collapse onto the same
    cached series."""
    call_count = 0

    def fake_get(url, params, timeout):
        nonlocal call_count
        call_count += 1
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "observations": [{"date": params["observation_end"], "value": str(10.0 + call_count)}]
        }
        return response

    with (
        mock.patch.object(mf, "FRED_API_KEY", "fake-key"),
        mock.patch.object(mf, "_vix_cache", {}),
        mock.patch.object(mf.SESSION, "get", side_effect=fake_get),
    ):
        first = mf.fetch_vix_series("2026-07-01", "2026-07-06")
        second = mf.fetch_vix_series("2026-07-07", "2026-07-13")

    assert first != second
    assert call_count == 2


def test_put_call_ratio_from_chain_computes_volume_based_ratio():
    chain = [
        {"option_type": "call", "volume": 100, "open_interest": 500},
        {"option_type": "put", "volume": 50, "open_interest": 200},
    ]
    assert mf.put_call_ratio_from_chain(chain) == 0.5


def test_put_call_ratio_from_chain_falls_back_to_open_interest_when_volume_is_zero():
    chain = [
        {"option_type": "call", "volume": 0, "open_interest": 400},
        {"option_type": "put", "volume": 0, "open_interest": 100},
    ]
    assert mf.put_call_ratio_from_chain(chain) == 0.25


def test_put_call_ratio_from_chain_returns_none_when_nothing_is_computable():
    chain = [{"option_type": "call", "volume": 0, "open_interest": 0}]
    assert mf.put_call_ratio_from_chain(chain) is None


def test_put_call_ratio_from_chain_handles_an_empty_chain():
    assert mf.put_call_ratio_from_chain([]) is None


def test_market_sentiment_for_date_returns_none_without_an_api_key():
    with mock.patch.object(mf, "FINNHUB_API_KEY", ""), mock.patch.object(mf, "_sentiment_headline_cache", {}):
        assert mf.market_sentiment_for_date("2026-07-06") is None


def test_market_sentiment_for_date_averages_vader_compound_scores():
    articles = [
        {"headline": "Stocks surge to record highs on strong earnings"},
        {"headline": "Markets tumble amid recession fears"},
    ]
    with (
        mock.patch.object(mf, "FINNHUB_API_KEY", "fake-key"),
        mock.patch.object(mf, "_sentiment_headline_cache", {}),
        mock.patch.object(mf, "_fetch_company_news", return_value=articles),
    ):
        score = mf.market_sentiment_for_date("2026-07-06")
    assert score is not None
    assert -1.0 <= score <= 1.0


def test_market_sentiment_for_date_returns_none_when_no_headlines():
    with (
        mock.patch.object(mf, "FINNHUB_API_KEY", "fake-key"),
        mock.patch.object(mf, "_sentiment_headline_cache", {}),
        mock.patch.object(mf, "_fetch_company_news", return_value=[]),
    ):
        assert mf.market_sentiment_for_date("2026-07-06") is None
