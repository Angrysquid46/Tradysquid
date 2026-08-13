from __future__ import annotations
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import engine
import shadow

CT = ZoneInfo("America/Chicago")


def test_next_shadow_id_increments_within_the_same_day():
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)
    rows = [{"shadow_id": "SHADOW-20260812-001"}]
    assert shadow.next_shadow_id(rows, timestamp) == "SHADOW-20260812-002"


def test_open_rows_filters_to_outcome_open():
    rows = [{"outcome": "OPEN"}, {"outcome": "WIN"}, {"outcome": "OPEN"}]
    assert len(shadow.open_rows(rows)) == 2


def test_try_open_shadow_position_skips_when_a_shadow_position_is_already_open():
    existing = shadow.blank_row()
    existing.update({"outcome": "OPEN"})
    row = shadow._try_open_shadow_position([existing], datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None


def test_try_open_shadow_position_skips_when_no_candidate_qualifies():
    with mock.patch.object(engine, "find_candidate", return_value={"qualified": False, "reason": "x"}):
        row = shadow._try_open_shadow_position([], datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None


def test_try_open_shadow_position_logs_a_row_with_a_model_score_and_no_bankroll_fields():
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "iv": 0.35, "option_symbol": "SPY260812P00600000",
    }
    found = {
        "qualified": True, "candidate": candidate,
        "context": {"regime": "BEARISH / CONTROLLED", "reason": "broke below the range"},
        "market_condition": "CHOPPY / NORMAL VOL", "chain": [], "today_str": "2026-08-12",
    }
    with (
        mock.patch.object(engine, "find_candidate", return_value=found),
        mock.patch.object(shadow.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(shadow.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(shadow.market_features, "vix_on_or_before", return_value=15.5),
        mock.patch.object(shadow.market_features, "market_sentiment_for_date", return_value=0.1),
        mock.patch.object(
            shadow.model_scoring, "explain_score",
            return_value={"score": 0.63, "contributions": [{"feature": "vix_at_entry", "shap_value": 0.2, "display_value": "15.5"}]},
        ),
    ):
        row = shadow._try_open_shadow_position([], datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["outcome"] == "OPEN"
    assert row["option_symbol"] == "SPY260812P00600000"
    assert row["model_score"] == "0.63"
    assert "63.0%" in row["model_narrative"]
    assert row["vix_at_entry"] == "15.5"
    assert "contracts" not in shadow.HEADER
    assert "balance_before" not in shadow.HEADER


def test_close_open_shadow_rows_closes_on_a_real_exit_signal():
    row = shadow.blank_row()
    row.update({"shadow_id": "SHADOW-1", "outcome": "OPEN", "option_symbol": "SPY260812P00600000", "entry_price": "0.50"})
    rows = [row]
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)
    with (
        mock.patch.object(shadow.s, "get_quotes", return_value={"SPY260812P00600000": {"bid": 0.20, "ask": 0.22}}),
        mock.patch.object(shadow.s, "quote_is_reliable_for_exit", return_value=True),
        mock.patch.object(shadow.s, "conservative_option_exit", return_value=0.20),
    ):
        closed = shadow._close_open_shadow_rows(rows, timestamp)
    assert closed == 1
    assert row["outcome"] == "LOSS"
    assert row["last_signal"] == "STOP OUT"


def test_run_shadow_cycle_returns_early_when_market_is_closed():
    with mock.patch.object(shadow.s, "market_is_open_now", return_value=(False, datetime.now(CT))):
        result = shadow.run_shadow_cycle()
    assert result == {"status": "market closed"}


def test_run_shadow_cycle_end_to_end_with_a_qualified_candidate():
    candidate = {
        "call_or_put": "call", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": 0.45, "iv": 0.2, "option_symbol": "SPY260812C00600000",
    }
    found = {
        "qualified": True, "candidate": candidate,
        "context": {"regime": "BULLISH / CONTROLLED", "reason": "broke above the range"},
        "market_condition": "TRENDING_UP / NORMAL VOL", "chain": [], "today_str": "2026-08-12",
    }
    with tempfile.TemporaryDirectory() as temp:
        log_path = Path(temp) / "shadow_trades.csv"
        with (
            mock.patch.object(shadow, "SHADOW_LOG_PATH", log_path),
            mock.patch.object(shadow.s, "market_is_open_now", return_value=(True, datetime(2026, 8, 12, 10, 0, tzinfo=CT))),
            mock.patch.object(shadow.s, "get_quote", return_value={"last": "600.5"}),
            mock.patch.object(engine, "find_candidate", return_value=found),
            mock.patch.object(shadow.market_features, "put_call_ratio_from_chain", return_value=None),
            mock.patch.object(shadow.market_features, "fetch_vix_series", return_value=[]),
            mock.patch.object(shadow.market_features, "vix_on_or_before", return_value=None),
            mock.patch.object(shadow.market_features, "market_sentiment_for_date", return_value=None),
            mock.patch.object(
                shadow.model_scoring, "explain_score",
                return_value={"score": 0.55, "contributions": []},
            ),
        ):
            result = shadow.run_shadow_cycle()

        assert result["status"] == "ok"
        assert result["opened"] is True
        assert result["model_score"] == "0.55"
        assert log_path.exists()
        saved_rows = shadow.read_log(log_path)
        assert len(saved_rows) == 1
        assert saved_rows[0]["outcome"] == "OPEN"
        assert "55.0%" in saved_rows[0]["model_narrative"]
