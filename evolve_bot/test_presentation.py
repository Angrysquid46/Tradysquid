from __future__ import annotations
import tempfile
from pathlib import Path
from unittest import mock

import bankroll
import presentation


_FAKE_REVIEW_DATA = {
    "live_trading": {
        "bankroll": {"balance": 822.0, "starting_balance": 1000.0, "all_time_high_balance": 1000.0, "run_number": 1, "total_resets": 0},
        "n_open": 1, "n_closed": 1, "win_rate": 0.0,
    },
    "shadow_mode": {
        "n_total_logged": 1, "n_closed": 0,
        "score_calibration": {"enough_data_to_compare": False},
    },
    "backtest_training_data": {"n_rows": 2575, "n_trading_days": 27, "n_real_priced_rows": 103},
    "retraining": {"n_retrains_recorded": 3, "most_recent": {"result": {"metrics": {"auc": 0.88}}}},
}


def _closed_row(closed_at: str, balance_before: str, balance_after: str, outcome: str) -> dict[str, str]:
    return {
        "outcome": outcome, "closed_at": closed_at, "timestamp": closed_at,
        "balance_before": balance_before, "balance_after": balance_after,
    }


def test_equity_curve_series_is_empty_with_no_closed_trades():
    rows = [{"outcome": "OPEN"}]
    assert presentation.equity_curve_series(rows) == []


def test_equity_curve_series_starts_with_the_pre_trade_balance():
    rows = [_closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS")]
    series = presentation.equity_curve_series(rows)
    assert series[0]["balance"] == 1000.0
    assert series[0]["outcome"] == "START"
    assert series[1]["balance"] == 850.0
    assert series[1]["outcome"] == "LOSS"


def test_equity_curve_series_is_chronologically_sorted_regardless_of_row_order():
    rows = [
        _closed_row("2026-08-02T10:00:00", "850.0", "900.0", "WIN"),
        _closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS"),
    ]
    series = presentation.equity_curve_series(rows)
    balances = [point["balance"] for point in series]
    assert balances == [1000.0, 850.0, 900.0]


def test_equity_curve_series_ignores_open_rows():
    rows = [
        _closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS"),
        {"outcome": "OPEN", "closed_at": ""},
    ]
    series = presentation.equity_curve_series(rows)
    assert len(series) == 2  # start + the one closed trade, not the open one


def test_compute_milestones_reflects_real_empty_state():
    bank_state = bankroll.default_state()
    milestones = presentation.compute_milestones([], bank_state)
    by_label = {m["label"]: m for m in milestones}
    assert by_label["First real trade closed"]["achieved"] is False
    assert by_label["First real win"]["achieved"] is False
    assert by_label["Survived a bankroll reset"]["achieved"] is False


def test_compute_milestones_reflects_real_progress():
    rows = [
        _closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS"),
        _closed_row("2026-08-02T10:00:00", "850.0", "1200.0", "WIN"),
    ]
    bank_state = bankroll.default_state()
    bank_state["all_time_high_balance"] = 1200.0
    milestones = presentation.compute_milestones(rows, bank_state)
    by_label = {m["label"]: m for m in milestones}
    assert by_label["First real trade closed"]["achieved"] is True
    assert by_label["First real win"]["achieved"] is True
    assert by_label["10 real closed trades"]["achieved"] is False
    assert by_label["10 real closed trades"]["detail"] == "2/10"


def test_render_equity_curve_returns_none_with_fewer_than_two_points():
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "curve.png"
        result = presentation.render_equity_curve([], output_path)
    assert result is None
    assert not output_path.exists()


def test_render_equity_curve_writes_a_real_png_with_real_data():
    rows = [
        _closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS"),
        _closed_row("2026-08-02T10:00:00", "850.0", "1200.0", "WIN"),
    ]
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "curve.png"
        result = presentation.render_equity_curve(rows, output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_render_milestones_always_writes_a_real_png():
    rows = [_closed_row("2026-08-01T10:00:00", "1000.0", "850.0", "LOSS")]
    bank_state = bankroll.default_state()
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "milestones.png"
        result = presentation.render_milestones(rows, bank_state, output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_render_milestones_writes_a_real_png_with_no_data_yet():
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "milestones.png"
        result = presentation.render_milestones([], bankroll.default_state(), output_path)
        assert result == output_path
        assert output_path.exists()


def test_render_self_tuning_log_returns_none_when_log_is_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as temp:
        missing_path = Path(temp) / "does_not_exist.jsonl"
        monkeypatch.setattr(presentation, "SELF_TUNING_LOG_PATH", missing_path)
        output_path = Path(temp) / "tuning.png"
        result = presentation.render_self_tuning_log(output_path)
    assert result is None
    assert not output_path.exists()


def test_render_self_tuning_log_writes_a_real_png_when_events_exist(monkeypatch):
    with tempfile.TemporaryDirectory() as temp:
        log_path = Path(temp) / "self_tuning_log.jsonl"
        log_path.write_text(
            '{"timestamp": "2026-08-12T10:00:00", "change": "stop_pct 0.50 -> 0.45", "reasoning": "backtest showed fewer stop-outs"}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(presentation, "SELF_TUNING_LOG_PATH", log_path)
        output_path = Path(temp) / "tuning.png"
        result = presentation.render_self_tuning_log(output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_render_stats_card_always_writes_a_real_png():
    data = {
        "live_trading": {
            "bankroll": {"balance": 822.0, "starting_balance": 1000.0, "all_time_high_balance": 1000.0, "run_number": 1, "total_resets": 0},
            "n_open": 1, "n_closed": 1, "win_rate": 0.0,
        },
        "shadow_mode": {
            "n_total_logged": 1, "n_closed": 0,
            "score_calibration": {"enough_data_to_compare": False},
        },
        "backtest_training_data": {"n_rows": 2575, "n_trading_days": 27, "n_real_priced_rows": 20},
        "retraining": {"n_retrains_recorded": 3, "most_recent": {"result": {"metrics": {"auc": 0.88}}}},
    }
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "card.png"
        result = presentation.render_stats_card(data, output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_post_dashboard_returns_early_when_discord_is_not_configured():
    with mock.patch.object(presentation.discord_post, "enabled", return_value=False):
        result = presentation.post_dashboard()
    assert result["status"] == "discord not configured"


def test_post_dashboard_posts_and_saves_state_when_enabled():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        bank_path = temp_path / "bankroll.json"
        log_path = temp_path / "trades.csv"
        state_path = temp_path / "dashboard_post_state.json"
        posted = []

        with (
            mock.patch.object(presentation.discord_post, "enabled", return_value=True),
            mock.patch.object(presentation.discord_post, "post_file", side_effect=lambda *a, **k: posted.append(a[0])),
            mock.patch.object(presentation, "DASHBOARD_POST_STATE_PATH", state_path),
            mock.patch.object(presentation, "PRESENTATION_DIR", temp_path),
            mock.patch.object(presentation.engine, "TRADELOG_PATH", log_path),
            mock.patch.object(presentation.engine, "BANKROLL_PATH", bank_path),
            mock.patch.object(presentation.weekly_review, "gather_review_data", return_value=_FAKE_REVIEW_DATA),
        ):
            result = presentation.post_dashboard()

        assert result["status"] == "posted"
        assert "stats_card" in result["posted"]
        assert "milestones" in result["posted"]
        assert state_path.exists()


def test_post_dashboard_does_not_post_twice_in_the_same_day():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        state_path = temp_path / "dashboard_post_state.json"
        import time as time_module

        state_path.write_text(
            '{"last_posted_date": "' + time_module.strftime("%Y-%m-%d") + '"}', encoding="utf-8"
        )

        with (
            mock.patch.object(presentation.discord_post, "enabled", return_value=True),
            mock.patch.object(presentation, "DASHBOARD_POST_STATE_PATH", state_path),
        ):
            result = presentation.post_dashboard()

        assert result["status"] == "already posted today"
