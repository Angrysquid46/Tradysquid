from __future__ import annotations

import csv as csv_module
import json
import tempfile
from pathlib import Path
from unittest import mock

import logic_proposals


def _row(variant_label: str, trading_day: str, outcome: str, pl_pct: float) -> dict[str, str]:
    return {
        "variant_label": variant_label,
        "trading_day": trading_day,
        "outcome": outcome,
        "pl_pct": str(pl_pct),
    }


def _baseline_label() -> str:
    return logic_proposals.live_baseline_variant_label()


def _days(n: int) -> list[str]:
    return [f"2026-07-{i:02d}" for i in range(1, n + 1)]


def _mixed_rows(label: str, days: list[str], win_pct: float, loss_pct: float, n_wins: int) -> list[dict[str, str]]:
    """n_wins WIN rows at win_pct, remaining days LOSS rows at loss_pct -
    always a mix (never all-WIN) so profit_factor is always computable,
    since a real proposal comparison is meaningless without a real
    baseline profit factor to compare against."""
    rows = [_row(label, d, "WIN", win_pct) for d in days[:n_wins]]
    rows += [_row(label, d, "LOSS", loss_pct) for d in days[n_wins:]]
    return rows


def test_live_baseline_variant_label_matches_real_live_constants():
    label = logic_proposals.live_baseline_variant_label()
    assert label == "stop_50_target_50"


def test_aggregate_variant_performance_computes_real_stats_per_variant():
    rows = [
        _row("stop_50_target_50", "2026-07-01", "WIN", 50.0),
        _row("stop_50_target_50", "2026-07-01", "LOSS", -20.0),
        _row("stop_50_target_50", "2026-07-02", "WIN", 50.0),
    ]
    stats = logic_proposals.aggregate_variant_performance(rows)
    assert stats["stop_50_target_50"]["n_rows"] == 3
    assert stats["stop_50_target_50"]["n_trading_days"] == 2
    assert stats["stop_50_target_50"]["win_rate"] == round(2 / 3, 4)
    assert stats["stop_50_target_50"]["profit_factor"] == 5.0  # (50+50) / 20


def test_profit_factor_is_none_with_zero_losses():
    """A variant with no real losses at all in a sample this small isn't
    a genuinely riskless strategy - it's a sign of too little data, and
    treating it as an infinite profit factor would make it look like an
    obviously great proposal candidate for the wrong reason."""
    assert logic_proposals._profit_factor([10.0, 20.0], []) is None


def test_evaluate_returns_no_baseline_evidence_when_baseline_variant_missing():
    rows = _mixed_rows("stop_20_target_150", _days(25), 40.0, -20.0, 20)
    result = logic_proposals.evaluate_exit_parameter_proposal(rows)
    assert result["status"] == "no baseline evidence yet"


def test_evaluate_refuses_below_minimum_trading_day_coverage():
    baseline = _baseline_label()
    rows = _mixed_rows(baseline, _days(5), 10.0, -10.0, 4)
    result = logic_proposals.evaluate_exit_parameter_proposal(rows)
    assert result["status"] == "not enough real trading-day coverage yet"
    assert result["n_trading_days_covered"] == 5


def test_evaluate_refuses_when_no_candidate_has_enough_rows():
    baseline = _baseline_label()
    days = _days(25)
    rows = _mixed_rows(baseline, days, 10.0, -10.0, 20)
    rows += [_row("stop_20_target_150", days[0], "WIN", 200.0)]  # only 1 row - below MIN_ROWS_PER_VARIANT
    result = logic_proposals.evaluate_exit_parameter_proposal(rows)
    assert result["status"] == "no candidate variant has enough rows to compare"


def test_evaluate_refuses_when_no_variant_meaningfully_beats_baseline():
    baseline = _baseline_label()
    days = _days(30)
    # Baseline: 24 wins of 30%, 6 losses of -20% -> profit factor 6.0
    rows = _mixed_rows(baseline, days, 30.0, -20.0, 24)
    # Candidate: only marginally better (31% wins) - should NOT clear the 1.25x margin.
    rows += _mixed_rows("stop_20_target_150", days, 31.0, -20.0, 24)
    result = logic_proposals.evaluate_exit_parameter_proposal(rows)
    assert result["status"] == "no variant meaningfully beats the live baseline"


def test_evaluate_finds_a_real_candidate_when_it_meaningfully_beats_baseline():
    baseline = _baseline_label()
    days = _days(30)
    # Baseline: 24 wins of 20%, 6 losses of -20% -> profit factor 4.0
    rows = _mixed_rows(baseline, days, 20.0, -20.0, 24)
    # Candidate: 29 wins of 50%, 1 loss of -20% -> profit factor 72.5, clears the 1.25x margin easily
    rows += _mixed_rows("stop_20_target_150", days, 50.0, -20.0, 29)
    result = logic_proposals.evaluate_exit_parameter_proposal(rows)
    assert result["status"] == "candidate found"
    assert result["proposed_variant"] == "stop_20_target_150"
    assert result["baseline_variant"] == baseline


def _write_backtest_csv(path: Path, rows: list[dict[str, str]]) -> None:
    header = ["variant_label", "trading_day", "outcome", "pl_pct"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv_module.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_run_proposal_cycle_writes_a_real_proposal_to_the_queue():
    baseline = _baseline_label()
    days = _days(30)
    rows = _mixed_rows(baseline, days, 20.0, -20.0, 24)
    rows += _mixed_rows("stop_20_target_150", days, 50.0, -20.0, 29)

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        backtest_csv = temp_path / "backtest_trades.csv"
        _write_backtest_csv(backtest_csv, rows)

        proposals_path = temp_path / "logic_proposals.jsonl"
        state_path = temp_path / "logic_proposal_state.json"
        with (
            mock.patch.object(logic_proposals.backtest, "BACKTEST_TRADES_PATH", backtest_csv),
            mock.patch.object(logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_proposals, "PROPOSAL_STATE_PATH", state_path),
        ):
            result = logic_proposals.run_proposal_cycle()

        assert result["status"] == "proposed"
        assert proposals_path.exists()
        lines = proposals_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        proposal = json.loads(lines[0])
        assert proposal["status"] == "pending_owner_review"
        assert proposal["category"] == "exit_parameter_change"
        assert proposal["proposed"]["variant"] == "stop_20_target_150"
        assert len(proposal["caveats"]) == 3


def test_run_proposal_cycle_posts_a_new_proposal_to_discord_when_enabled():
    baseline = _baseline_label()
    days = _days(30)
    rows = _mixed_rows(baseline, days, 20.0, -20.0, 24)
    rows += _mixed_rows("stop_20_target_150", days, 50.0, -20.0, 29)

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        backtest_csv = temp_path / "backtest_trades.csv"
        _write_backtest_csv(backtest_csv, rows)

        with (
            mock.patch.object(logic_proposals.backtest, "BACKTEST_TRADES_PATH", backtest_csv),
            mock.patch.object(logic_proposals, "LOGIC_PROPOSALS_PATH", temp_path / "logic_proposals.jsonl"),
            mock.patch.object(logic_proposals, "PROPOSAL_STATE_PATH", temp_path / "logic_proposal_state.json"),
            mock.patch.object(logic_proposals.discord_post, "upsert_message") as fake_upsert,
        ):
            logic_proposals.run_proposal_cycle()

        # Upserted under one stable key, not posted fresh - owner: "it
        # keeps spamming the same thing over and over, we just need 1."
        fake_upsert.assert_called_once()
        channel_key, card_key, content = fake_upsert.call_args[0]
        assert channel_key == "reviews"
        assert card_key == "pending-proposal"
        assert "stop_20_target_150" in content
        assert "Pending owner review" in content
        embed = fake_upsert.call_args[1]["embed"]
        assert "New Phase 12 Proposal" in embed["title"]


def test_run_proposal_cycle_still_writes_the_proposal_when_discord_posting_fails():
    """A Discord outage must never prevent a real, evidence-backed
    proposal from landing in the review queue - the queue file is the
    actual source of truth, posting is just a notification."""
    baseline = _baseline_label()
    days = _days(30)
    rows = _mixed_rows(baseline, days, 20.0, -20.0, 24)
    rows += _mixed_rows("stop_20_target_150", days, 50.0, -20.0, 29)

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        backtest_csv = temp_path / "backtest_trades.csv"
        _write_backtest_csv(backtest_csv, rows)
        proposals_path = temp_path / "logic_proposals.jsonl"

        with (
            mock.patch.object(logic_proposals.backtest, "BACKTEST_TRADES_PATH", backtest_csv),
            mock.patch.object(logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_proposals, "PROPOSAL_STATE_PATH", temp_path / "logic_proposal_state.json"),
            mock.patch.object(
                logic_proposals.discord_post, "upsert_message",
                side_effect=logic_proposals.discord_post.DiscordPostError("down"),
            ),
        ):
            result = logic_proposals.run_proposal_cycle()

        assert result["status"] == "proposed"
        assert proposals_path.exists()


def test_run_proposal_cycle_does_not_duplicate_a_still_pending_proposal():
    baseline = _baseline_label()
    days = _days(30)
    rows = _mixed_rows(baseline, days, 20.0, -20.0, 24)
    rows += _mixed_rows("stop_20_target_150", days, 50.0, -20.0, 29)

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        backtest_csv = temp_path / "backtest_trades.csv"
        _write_backtest_csv(backtest_csv, rows)

        proposals_path = temp_path / "logic_proposals.jsonl"
        state_path = temp_path / "logic_proposal_state.json"
        with (
            mock.patch.object(logic_proposals.backtest, "BACKTEST_TRADES_PATH", backtest_csv),
            mock.patch.object(logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_proposals, "PROPOSAL_STATE_PATH", state_path),
        ):
            first = logic_proposals.run_proposal_cycle()
            second = logic_proposals.run_proposal_cycle()

        assert first["status"] == "proposed"
        assert second["status"] == "already proposed, awaiting owner review"
        lines = proposals_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1


def test_run_proposal_cycle_writes_nothing_when_there_is_no_real_candidate():
    baseline = _baseline_label()
    days = _days(5)
    rows = _mixed_rows(baseline, days, 10.0, -10.0, 4)

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        backtest_csv = temp_path / "backtest_trades.csv"
        _write_backtest_csv(backtest_csv, rows)

        proposals_path = temp_path / "logic_proposals.jsonl"
        state_path = temp_path / "logic_proposal_state.json"
        with (
            mock.patch.object(logic_proposals.backtest, "BACKTEST_TRADES_PATH", backtest_csv),
            mock.patch.object(logic_proposals, "LOGIC_PROPOSALS_PATH", proposals_path),
            mock.patch.object(logic_proposals, "PROPOSAL_STATE_PATH", state_path),
        ):
            result = logic_proposals.run_proposal_cycle()

        assert result["status"] == "not enough real trading-day coverage yet"
        assert not proposals_path.exists()
