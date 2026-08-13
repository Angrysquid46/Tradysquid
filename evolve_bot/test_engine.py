from __future__ import annotations
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import bankroll
import engine
import tradelog

CT = ZoneInfo("America/Chicago")


def _isolated_paths(temp_dir):
    return Path(temp_dir) / "bankroll.json", Path(temp_dir) / "trades.csv"


def test_run_cycle_returns_early_when_market_is_closed():
    with mock.patch.object(engine.s, "market_is_open_now", return_value=(False, datetime.now(CT))):
        result = engine.run_cycle()
    assert result == {"status": "market closed"}


def test_run_cycle_returns_early_when_spot_quote_is_unavailable():
    with tempfile.TemporaryDirectory() as temp:
        bank_path, log_path = _isolated_paths(temp)
        with (
            mock.patch.object(engine, "BANKROLL_PATH", bank_path),
            mock.patch.object(engine, "TRADELOG_PATH", log_path),
            mock.patch.object(engine.s, "market_is_open_now", return_value=(True, datetime.now(CT))),
            mock.patch.object(engine.s, "get_quote", return_value=None),
        ):
            result = engine.run_cycle()
    assert result == {"status": "spot quote unavailable"}


def test_close_open_positions_credits_bankroll_and_marks_loss_on_a_stop_out():
    row = tradelog.blank_row()
    row.update({
        "trade_id": "EVOLVE-20260812-001", "outcome": "OPEN",
        "option_symbol": "SPY260812P00770000", "entry_price": "0.50", "contracts": "2",
    })
    rows = [row]
    bank = bankroll.default_state()
    bank = bankroll.debit_entry(bank, 100.0)  # simulate the entry cost already paid
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)  # mid-session, well outside the EOD-close window

    # entry $0.50, SPY_0DTE_STOP_PCT is -50% - mark $0.20 is a -60% move,
    # clearly past the stop rather than close enough to be ambiguous.
    with (
        mock.patch.object(engine.s, "get_quotes", return_value={"SPY260812P00770000": {"bid": 0.20, "ask": 0.22}}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=True),
        mock.patch.object(engine.s, "conservative_option_exit", return_value=0.20),
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 1
    assert row["outcome"] == "LOSS"
    assert row["last_signal"] == "STOP OUT"
    assert row["exit_price"] == "0.2"
    # proceeds = 0.20 * 100 * 2 contracts = $40, credited back to the bank
    assert updated_bank["balance"] == bank["balance"] + 40.0


def test_close_open_positions_posts_a_real_discord_alert_on_close():
    row = tradelog.blank_row()
    row.update({
        "trade_id": "EVOLVE-20260812-001", "outcome": "OPEN",
        "option_symbol": "SPY260812P00770000", "entry_price": "0.50", "contracts": "2",
    })
    rows = [row]
    bank = bankroll.default_state()
    bank = bankroll.debit_entry(bank, 100.0)
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={"SPY260812P00770000": {"bid": 0.20, "ask": 0.22}}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=True),
        mock.patch.object(engine.s, "conservative_option_exit", return_value=0.20),
        mock.patch.object(engine.discord_post, "post_message") as fake_post,
    ):
        engine._close_open_positions(rows, bank, timestamp)

    fake_post.assert_called_once()
    channel_key, content = fake_post.call_args[0]
    assert channel_key == "trades"
    assert "LOSS" in content
    assert "SPY260812P00770000" in content
    assert "STOP OUT" in content


def test_close_open_positions_never_raises_when_discord_posting_fails():
    """A Discord outage must never break a real trade close - posting is
    a side effect of the trade, not a precondition for it."""
    row = tradelog.blank_row()
    row.update({
        "trade_id": "T1", "outcome": "OPEN",
        "option_symbol": "SPY260812P00770000", "entry_price": "0.50", "contracts": "1",
    })
    rows = [row]
    bank = bankroll.default_state()
    bank = bankroll.debit_entry(bank, 50.0)
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={"SPY260812P00770000": {"bid": 0.20, "ask": 0.22}}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=True),
        mock.patch.object(engine.s, "conservative_option_exit", return_value=0.20),
        mock.patch.object(engine.discord_post, "post_message", side_effect=engine.discord_post.DiscordPostError("down")),
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 1  # the real trade close still happened despite the Discord failure


def test_close_open_positions_skips_a_row_with_an_unreliable_quote():
    row = tradelog.blank_row()
    row.update({"trade_id": "T1", "outcome": "OPEN", "option_symbol": "SPY260812P00770000", "entry_price": "0.50", "contracts": "1"})
    rows = [row]
    bank = bankroll.default_state()
    timestamp = datetime(2026, 8, 12, 10, 0, tzinfo=CT)

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={"SPY260812P00770000": {"bid": 0, "ask": 0}}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=False),
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 0
    assert row["outcome"] == "OPEN"
    assert updated_bank == bank


def test_try_open_new_position_skips_when_a_position_is_already_open():
    existing = tradelog.blank_row()
    existing.update({"trade_id": "T1", "outcome": "OPEN"})
    bank = bankroll.default_state()
    row, updated_bank = engine._try_open_new_position([existing], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None
    assert updated_bank == bank


def test_try_open_new_position_skips_during_the_blocked_entry_window():
    with mock.patch.object(engine.s, "entry_window_blocked", return_value="within the opening minutes"):
        row, updated_bank = engine._try_open_new_position([], bankroll.default_state(), datetime(2026, 8, 12, 8, 35, tzinfo=CT), 600.0)
    assert row is None


def test_try_open_new_position_skips_when_todays_expiration_isnt_listed():
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2099-01-01"]),
    ):
        row, updated_bank = engine._try_open_new_position([], bankroll.default_state(), datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None


def test_try_open_new_position_skips_when_the_signal_is_not_qualified():
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(engine.s, "spy_0dte_opening_range_signal", return_value={"qualified": False}),
    ):
        row, updated_bank = engine._try_open_new_position([], bankroll.default_state(), datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None


def test_try_open_new_position_opens_and_debits_the_bankroll_when_everything_qualifies():
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "CHOPPY / NORMAL VOL"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "broke below the range", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=0.85),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=15.5),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=0.12),
        mock.patch.object(engine.model_scoring, "explain_score", return_value={"score": 0.71, "contributions": []}),
    ):
        row, updated_bank = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["outcome"] == "OPEN"
    assert row["option_symbol"] == "SPY260812P00600000"
    assert row["market_condition_at_entry"] == "CHOPPY / NORMAL VOL"
    assert "BEARISH" in row["thesis"]
    assert row["vix_at_entry"] == "15.5"
    assert row["sentiment_at_entry"] == "0.12"
    assert row["put_call_ratio_at_entry"] == "0.85"
    assert row["model_score_at_entry"] == "0.71"
    # $1000 balance * 15% = $150 position size; $0.50 premium -> $50/contract -> 3 contracts
    assert row["contracts"] == "3"
    # cost = 0.50 * 100 * 3 = $150, debited from the starting $1000
    assert updated_bank["balance"] == bankroll.STARTING_BALANCE - 150.0


def test_try_open_new_position_posts_a_real_discord_alert_on_entry():
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "CHOPPY / NORMAL VOL"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "broke below the range", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=0.85),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=15.5),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=0.12),
        mock.patch.object(engine.model_scoring, "explain_score", return_value={"score": 0.71, "contributions": []}),
        mock.patch.object(engine.discord_post, "post_message") as fake_post,
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    fake_post.assert_called_once()
    channel_key, content = fake_post.call_args[0]
    assert channel_key == "trades"
    assert "PUT" in content
    assert "SPY_EVOLVE opened" in content


def test_try_open_new_position_leaves_market_features_blank_when_unavailable():
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "x", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=None),
        mock.patch.object(engine.model_scoring, "explain_score", return_value=None),
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["vix_at_entry"] == ""
    assert row["sentiment_at_entry"] == ""
    assert row["put_call_ratio_at_entry"] == ""
    assert row["model_score_at_entry"] == ""


def test_try_open_new_position_ignores_a_low_model_score_when_filter_is_disabled():
    """MODEL_FILTER_ENABLED defaults to False (Phase 7, deliberately
    dormant until shadow mode has real history) - a candidate the model
    scores very low must still open, unchanged from Phase 1-6 behavior."""
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine, "MODEL_FILTER_ENABLED", False),
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "x", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=None),
        mock.patch.object(engine.model_scoring, "explain_score", return_value={"score": 0.02, "contributions": []}),
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["outcome"] == "OPEN"
    assert row["model_score_at_entry"] == "0.02"


def test_try_open_new_position_skips_a_low_model_score_when_filter_is_enabled():
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine, "MODEL_FILTER_ENABLED", True),
        mock.patch.object(engine, "MODEL_MIN_WIN_PROBABILITY", 0.5),
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "x", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=None),
        mock.patch.object(engine.model_scoring, "explain_score", return_value={"score": 0.02, "contributions": []}),
    ):
        row, updated_bank = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is None
    assert updated_bank == bank


def test_try_open_new_position_opens_a_high_model_score_when_filter_is_enabled():
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine, "MODEL_FILTER_ENABLED", True),
        mock.patch.object(engine, "MODEL_MIN_WIN_PROBABILITY", 0.5),
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "x", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=None),
        mock.patch.object(engine.model_scoring, "explain_score", return_value={"score": 0.9, "contributions": []}),
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["outcome"] == "OPEN"


def test_try_open_new_position_never_blocks_on_a_missing_model_score_even_when_filter_is_enabled():
    """A None score (no model trained yet, or a load failure) must never
    be treated as a low score - only an actual number below threshold
    blocks the trade."""
    bank = bankroll.default_state()
    candidate = {
        "call_or_put": "put", "strike": "600", "expiration": "2026-08-12",
        "entry_price": 0.50, "delta": -0.42, "theta": -0.05, "iv": 0.35,
        "open_interest": 500, "option_volume": 200, "option_symbol": "SPY260812P00600000",
        "score": 42,
    }
    with (
        mock.patch.object(engine, "MODEL_FILTER_ENABLED", True),
        mock.patch.object(engine, "MODEL_MIN_WIN_PROBABILITY", 0.5),
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BEARISH / CONTROLLED", "reason": "x", "range_high": 601.0, "range_low": 599.0},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[{"strike": 600.0, "option_type": "put"}]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[candidate]),
        mock.patch.object(engine.market_features, "put_call_ratio_from_chain", return_value=None),
        mock.patch.object(engine.market_features, "fetch_vix_series", return_value=[]),
        mock.patch.object(engine.market_features, "vix_on_or_before", return_value=None),
        mock.patch.object(engine.market_features, "market_sentiment_for_date", return_value=None),
        mock.patch.object(engine.model_scoring, "explain_score", return_value=None),
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    assert row["outcome"] == "OPEN"
    assert row["model_score_at_entry"] == ""


def test_try_open_new_position_skips_when_no_candidates_pass_the_filters():
    with (
        mock.patch.object(engine.s, "entry_window_blocked", return_value=""),
        mock.patch.object(engine.s, "get_expirations", return_value=["2026-08-12"]),
        mock.patch.object(engine.s, "get_daily_history", return_value=[]),
        mock.patch.object(engine.s, "classify_market_condition", return_value={"label": "UNKNOWN"}),
        mock.patch.object(engine.s, "get_intraday_history", return_value=[]),
        mock.patch.object(
            engine.s, "spy_0dte_opening_range_signal",
            return_value={"qualified": True, "regime": "BULLISH / CONTROLLED", "reason": "x"},
        ),
        mock.patch.object(engine.s, "filter_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_strikes", return_value=[600.0]),
        mock.patch.object(engine.s, "get_chain", return_value=[]),
        mock.patch.object(engine.s, "scan_spy_0dte_candidates", return_value=[]),
    ):
        row, updated_bank = engine._try_open_new_position([], bankroll.default_state(), datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)
    assert row is None
