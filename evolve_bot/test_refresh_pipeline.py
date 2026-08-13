from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import refresh_pipeline


def test_run_refresh_skips_when_cached_days_are_unchanged():
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        state_path.write_text(
            json.dumps({"last_seen_days": ["2026-08-10", "2026-08-11"]}), encoding="utf-8"
        )
        with (
            mock.patch.object(refresh_pipeline, "REFRESH_STATE_PATH", state_path),
            mock.patch.object(refresh_pipeline.robinhood_cache, "cached_equity_days", return_value=["2026-08-10", "2026-08-11"]),
            mock.patch.object(refresh_pipeline.backtest, "run_backtest") as fake_backtest,
            mock.patch.object(refresh_pipeline.retrain_loop, "run_retrain_cycle") as fake_retrain,
            mock.patch.object(refresh_pipeline.logic_proposals, "run_proposal_cycle") as fake_proposals,
        ):
            result = refresh_pipeline.run_refresh()

        assert result["status"] == "no new cached days since last refresh"
        fake_backtest.assert_not_called()
        fake_retrain.assert_not_called()
        fake_proposals.assert_not_called()


def test_run_refresh_runs_the_full_chain_when_a_new_day_appears():
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        state_path.write_text(json.dumps({"last_seen_days": ["2026-08-10"]}), encoding="utf-8")

        with (
            mock.patch.object(refresh_pipeline, "REFRESH_STATE_PATH", state_path),
            mock.patch.object(
                refresh_pipeline.robinhood_cache, "cached_equity_days", return_value=["2026-08-10", "2026-08-12"]
            ),
            mock.patch.object(refresh_pipeline.backtest, "run_backtest", return_value={"rows_written_this_run": 25}) as fake_backtest,
            mock.patch.object(refresh_pipeline.retrain_loop, "run_retrain_cycle", return_value={"status": "retrained"}) as fake_retrain,
            mock.patch.object(refresh_pipeline.logic_proposals, "run_proposal_cycle", return_value={"status": "proposed"}) as fake_proposals,
        ):
            result = refresh_pipeline.run_refresh()

        assert result["status"] == "refreshed"
        assert result["n_cached_days"] == 2
        assert result["retrain"] == "retrained"
        assert result["proposals"] == "proposed"
        fake_backtest.assert_called_once()
        fake_retrain.assert_called_once()
        fake_proposals.assert_called_once()

        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["last_seen_days"] == ["2026-08-10", "2026-08-12"]


def test_run_refresh_runs_the_full_chain_the_first_time_with_no_prior_state():
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "does_not_exist.json"

        with (
            mock.patch.object(refresh_pipeline, "REFRESH_STATE_PATH", state_path),
            mock.patch.object(refresh_pipeline.robinhood_cache, "cached_equity_days", return_value=["2026-08-10"]),
            mock.patch.object(refresh_pipeline.backtest, "run_backtest", return_value={}) as fake_backtest,
            mock.patch.object(refresh_pipeline.retrain_loop, "run_retrain_cycle", return_value={"status": "retrained"}),
            mock.patch.object(refresh_pipeline.logic_proposals, "run_proposal_cycle", return_value={"status": "proposed"}),
        ):
            result = refresh_pipeline.run_refresh()

        assert result["status"] == "refreshed"
        fake_backtest.assert_called_once()


def test_run_refresh_force_bypasses_the_unchanged_gate():
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "state.json"
        state_path.write_text(json.dumps({"last_seen_days": ["2026-08-10"]}), encoding="utf-8")

        with (
            mock.patch.object(refresh_pipeline, "REFRESH_STATE_PATH", state_path),
            mock.patch.object(refresh_pipeline.robinhood_cache, "cached_equity_days", return_value=["2026-08-10"]),
            mock.patch.object(refresh_pipeline.backtest, "run_backtest", return_value={}) as fake_backtest,
            mock.patch.object(refresh_pipeline.retrain_loop, "run_retrain_cycle", return_value={"status": "skipped - no new data"}),
            mock.patch.object(refresh_pipeline.logic_proposals, "run_proposal_cycle", return_value={"status": "not enough real trading-day coverage yet"}),
        ):
            result = refresh_pipeline.run_refresh(force=True)

        assert result["status"] == "refreshed"
        fake_backtest.assert_called_once()
