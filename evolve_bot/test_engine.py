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


def test_refresh_dashboard_calls_post_dashboard():
    """engine.run_cycle wires this in so the #evolve-dashboard cards
    track real activity every ~3 minutes instead of once a day - owner,
    after a day with 6 real trades closing while the dashboard still
    showed the morning's stale numbers: "these don't look right."."""
    import presentation

    with mock.patch.object(presentation, "post_dashboard") as fake_post:
        engine._refresh_dashboard()

    fake_post.assert_called_once()


def test_refresh_dashboard_never_raises_when_discord_posting_fails():
    import presentation

    with mock.patch.object(
        presentation, "post_dashboard", side_effect=engine.discord_post.DiscordPostError("down")
    ):
        engine._refresh_dashboard()  # must not raise


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
        mock.patch.object(engine.discord_post, "upsert_message") as fake_upsert,
    ):
        engine._close_open_positions(rows, bank, timestamp)

    fake_upsert.assert_called_once()
    channel_key, card_key, content = fake_upsert.call_args[0]
    assert channel_key == "trades"
    assert card_key == "trade:EVOLVE-20260812-001"
    assert "LOSS" in content
    assert "SPY260812P00770000" in content
    assert "STOP OUT" in content


def test_close_open_positions_upserts_a_live_held_position_card_when_not_closing():
    """Owner: "why can I track its live pl like all the other stuff?" -
    a position that's evaluated but doesn't close yet should get its
    live P/L card refreshed (upserted, not a new message each cycle),
    under the SAME card key the entry card used - one card per trade,
    not a second 'held' card next to it (owner: "why's it showing 2
    cards for every trade?")."""
    row = tradelog.blank_row()
    row.update({
        "trade_id": "EVOLVE-20260813-001", "outcome": "OPEN",
        "option_symbol": "SPY260813C00777000", "entry_price": "0.76", "contracts": "2",
    })
    rows = [row]
    bank = bankroll.default_state()
    timestamp = datetime(2026, 8, 13, 13, 0, tzinfo=CT)

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={"SPY260813C00777000": {"bid": 0.80, "ask": 0.82}}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=True),
        mock.patch.object(engine.s, "conservative_option_exit", return_value=0.81),
        mock.patch.object(engine.logic_state, "current_exit_signal", return_value=("HOLD", "no exit condition met")),
        mock.patch.object(engine.discord_post, "upsert_message") as fake_upsert,
        mock.patch.object(engine.discord_post, "delete_card") as fake_delete,
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 0
    assert row["outcome"] == "OPEN"
    fake_delete.assert_not_called()
    fake_upsert.assert_called_once()
    channel_key, card_key, content = fake_upsert.call_args[0]
    assert channel_key == "trades"
    assert card_key == "trade:EVOLVE-20260813-001"
    assert "SPY260813C00777000" in content
    assert "0.81" in content or "+7%" in content  # real live mark/P&L, not a placeholder


def test_close_open_positions_updates_the_same_trade_card_on_close_instead_of_deleting_it():
    """Owner: "why's it showing 2 cards for every trade?" - closing a
    position must update the SAME trade:<id> card the entry/held
    updates already used (one persistent card for the trade's whole
    lifecycle), not delete a separate 'held' card and post yet another
    standalone close message."""
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
        mock.patch.object(engine.discord_post, "upsert_message") as fake_upsert,
        mock.patch.object(engine.discord_post, "delete_card") as fake_delete,
    ):
        engine._close_open_positions(rows, bank, timestamp)

    fake_delete.assert_not_called()
    fake_upsert.assert_called_once()
    channel_key, card_key, content = fake_upsert.call_args[0]
    assert channel_key == "trades"
    assert card_key == "trade:EVOLVE-20260812-001"


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
        mock.patch.object(engine.discord_post, "upsert_message", side_effect=engine.discord_post.DiscordPostError("down")),
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


def test_close_open_positions_force_closes_a_position_past_its_own_expiration_with_no_quote():
    """Regression guard for a real bug found live 2026-08-13:
    EVOLVE-20260812-002 (expiration 2026-08-12) sat OPEN a full day into
    2026-08-13 because its option symbol expired and Tradier stopped
    serving quotes for it - with no quote, evaluate_exit_for_row always
    returned None, so the position could never be re-evaluated or
    closed, silently blocking every new entry (single-position-at-a-time
    gate) indefinitely."""
    row = tradelog.blank_row()
    row.update({
        "trade_id": "EVOLVE-20260812-002", "outcome": "OPEN",
        "option_symbol": "SPY260812P00773000", "entry_price": "0.33", "contracts": "1",
        "expiration": "2026-08-12",
    })
    rows = [row]
    bank = bankroll.default_state()
    bank = bankroll.debit_entry(bank, 33.0)
    timestamp = datetime(2026, 8, 13, 10, 0, tzinfo=CT)  # a full day after expiration

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=False),
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 1
    assert row["outcome"] == "LOSS"
    assert row["last_signal"] == "EXPIRATION CLOSE"
    assert row["exit_price"] == "0.0"
    assert row["closed_at"]
    assert updated_bank["balance"] == bank["balance"]  # mark=0 proceeds - nothing credited back


def test_close_open_positions_does_not_force_close_same_day_expiration_with_no_quote():
    """A position expiring TODAY (not yet past its own expiration) with a
    temporarily bad quote should still just wait for the next cycle, not
    get force-closed as if it were an orphan."""
    row = tradelog.blank_row()
    row.update({
        "trade_id": "T1", "outcome": "OPEN",
        "option_symbol": "SPY260813C00780000", "entry_price": "0.50", "contracts": "1",
        "expiration": "2026-08-13",
    })
    rows = [row]
    bank = bankroll.default_state()
    timestamp = datetime(2026, 8, 13, 10, 0, tzinfo=CT)

    with (
        mock.patch.object(engine.s, "get_quotes", return_value={}),
        mock.patch.object(engine.s, "quote_is_reliable_for_exit", return_value=False),
    ):
        updated_bank, closed = engine._close_open_positions(rows, bank, timestamp)

    assert closed == 0
    assert row["outcome"] == "OPEN"


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
    # Derived from the real bankroll.POSITION_SIZE_PCT constant rather than
    # a hardcoded percentage, so this test doesn't silently drift out of
    # sync (and start asserting the WRONG number instead of failing) if
    # that constant is ever tuned.
    expected_size_dollars = bankroll.STARTING_BALANCE * bankroll.POSITION_SIZE_PCT
    expected_contracts = int(expected_size_dollars // 50.0)  # $0.50 premium -> $50/contract
    expected_cost = 0.50 * 100 * expected_contracts
    assert row["contracts"] == str(expected_contracts)
    assert updated_bank["balance"] == bankroll.STARTING_BALANCE - expected_cost


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
        mock.patch.object(engine.discord_post, "upsert_message") as fake_upsert,
    ):
        row, _ = engine._try_open_new_position([], bank, datetime(2026, 8, 12, 10, 0, tzinfo=CT), 600.0)

    assert row is not None
    fake_upsert.assert_called_once()
    channel_key, card_key, content = fake_upsert.call_args[0]
    assert channel_key == "trades"
    assert card_key == f"trade:{row['trade_id']}"
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
