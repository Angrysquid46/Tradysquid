"""Real tests for bots/claude/evolution.py: fitness-ranked selection
among simultaneously-firing hypotheses, fitness computed from real
attributed closed trades (via scoreboard.py, monkeypatched to an
isolated tmp DB), deterministic tightening on negative fitness, and
disabling once every tunable parameter is already at its bound."""

from __future__ import annotations

import pytest
import scoreboard

import bots.claude.evolution as evolution
from bots.claude.parameters import MIN_SAMPLE_BEFORE_EVOLVE, MUTATION_SPECS

# Features where trend_continuation AND momentum_acceleration both fire
# CALL simultaneously (mean_reversion_extreme is blocked - trend_strength
# STRONG exceeds its max_trend_strength_level=1), so selection between
# the two is a real, meaningful test of fitness-based ranking.
_BOTH_FIRE_FEATURES = {
    "trend_strength": "STRONG",
    "trend_direction_di": "BULLISH",
    "short_term_trend": "UP", "medium_term_trend": "UP", "long_term_trend": "UP",
    "macd_histogram": 0.5,
    "relative_volume": 2.0,
    "trend_run_length": 2,
}

_NOTHING_FIRES_FEATURES = {
    "trend_strength": "NONE",
    "trend_direction_di": "NEUTRAL",
    "short_term_trend": "FLAT", "medium_term_trend": "FLAT", "long_term_trend": "FLAT",
    "macd_histogram": 0.0,
    "relative_volume": 0.5,
    "trend_run_length": 0,
    "rsi_14": 50.0, "bb_upper": 110.0, "bb_lower": 95.0,
}


def _evo_conn(tmp_path):
    return evolution.connect_db(tmp_path / "axiom-evolution-test.db")


def _open_and_close(sb, trade_id, pnl_usd, generation=1):
    scoreboard.record_trade_open(
        sb, trade_id=trade_id, bot="AXIOM", generation=generation,
        opened_at="2026-08-25T09:30:00", side="CALL",
        contract_symbol=f"SPY-{trade_id}", entry_price=4.0, contracts=1,
        entry_bankroll=scoreboard.current_bankroll(sb, "AXIOM"),
    )
    scoreboard.record_trade_close(
        sb, trade_id=trade_id, closed_at="2026-08-25T10:00:00",
        exit_price=4.0 + pnl_usd / 100, pnl_usd=pnl_usd,
    )


def _attribute_n_trades(sb, evo_conn, hypothesis_name, pnls, prefix):
    for i, pnl in enumerate(pnls):
        trade_id = f"{prefix}-{i}"
        _open_and_close(sb, trade_id, pnl)
        evolution.record_trade_attribution(
            evo_conn, trade_id=trade_id, hypothesis_name=hypothesis_name, generation=1
        )


# --- select_hypothesis: fitness-ranked selection ---

def test_select_hypothesis_picks_the_higher_measured_fitness(tmp_path):
    conn = _evo_conn(tmp_path)

    def fake_fitness(_connection, name):
        return {"trend_continuation": (5.0, 20), "momentum_acceleration": (-3.0, 20)}.get(name, (0.0, 0))

    selected = evolution.select_hypothesis(conn, 100.0, _BOTH_FIRE_FEATURES, fitness_fn=fake_fitness)
    assert selected is not None
    assert selected.name == "trend_continuation"


def test_select_hypothesis_flips_with_fitness(tmp_path):
    conn = _evo_conn(tmp_path)

    def fake_fitness(_connection, name):
        return {"trend_continuation": (-3.0, 20), "momentum_acceleration": (5.0, 20)}.get(name, (0.0, 0))

    selected = evolution.select_hypothesis(conn, 100.0, _BOTH_FIRE_FEATURES, fitness_fn=fake_fitness)
    assert selected is not None
    assert selected.name == "momentum_acceleration"


def test_unmeasured_hypothesis_is_neutral_not_penalized(tmp_path):
    conn = _evo_conn(tmp_path)

    def fake_fitness(_connection, name):
        return {"trend_continuation": (-5.0, 20), "momentum_acceleration": (None, 2)}.get(name, (0.0, 0))

    selected = evolution.select_hypothesis(conn, 100.0, _BOTH_FIRE_FEATURES, fitness_fn=fake_fitness)
    assert selected is not None
    assert selected.name == "momentum_acceleration"  # neutral 0.0 beats -5.0


def test_select_hypothesis_returns_none_when_nothing_fires(tmp_path):
    conn = _evo_conn(tmp_path)
    assert evolution.select_hypothesis(conn, 100.0, _NOTHING_FIRES_FEATURES) is None


def test_select_hypothesis_returns_none_when_all_disabled(tmp_path):
    conn = _evo_conn(tmp_path)
    conn.execute("UPDATE hypothesis_state SET enabled=0")
    conn.commit()
    assert evolution.select_hypothesis(conn, 100.0, _BOTH_FIRE_FEATURES) is None


# --- hypothesis_fitness: reads real scoreboard closed trades ---

def test_hypothesis_fitness_none_below_minimum_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    _attribute_n_trades(sb, conn, "trend_continuation", [10.0] * (MIN_SAMPLE_BEFORE_EVOLVE - 1), "t")

    fitness, sample_size = evolution.hypothesis_fitness(conn, "trend_continuation")
    assert fitness is None
    assert sample_size == MIN_SAMPLE_BEFORE_EVOLVE - 1


def test_hypothesis_fitness_computed_at_minimum_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    pnls = [10.0] * 5 + [-30.0] * 5  # mean = -10.0
    _attribute_n_trades(sb, conn, "trend_continuation", pnls, "t")

    fitness, sample_size = evolution.hypothesis_fitness(conn, "trend_continuation")
    assert sample_size == MIN_SAMPLE_BEFORE_EVOLVE
    # scoreboard.py now computes pnl_usd itself from entry/exit/contracts
    # rather than storing the test's exact pre-rounded value, so a tiny
    # float round-trip difference is expected, not a bug.
    assert fitness == pytest.approx(-10.0)


# --- update_fitness_and_evolve: deterministic tightening / disabling ---

def test_evolve_tightens_every_tunable_param_on_negative_fitness(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    before = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert len(applied) == 1
    event = applied[0]
    assert event["hypothesis"] == "trend_continuation"
    assert event["event"] == "TIGHTENED"

    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    specs = MUTATION_SPECS["trend_continuation"]
    for key, (step, lower, upper) in specs.items():
        expected = max(lower, min(upper, before[key] + step))
        assert after[key] == expected, key

    state = evolution.get_hypothesis_state(conn, "trend_continuation")
    assert state["generation"] == 1
    assert state["enabled"] == 1


def test_evolve_disables_hypothesis_already_at_every_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)

    import json
    specs = MUTATION_SPECS["trend_continuation"]
    at_bound = {key: (upper if step > 0 else lower) for key, (step, lower, upper) in specs.items()}
    conn.execute(
        "UPDATE hypothesis_state SET params_json=? WHERE name=?",
        (json.dumps(at_bound), "trend_continuation"),
    )
    conn.commit()
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert len(applied) == 1
    assert applied[0]["event"] == "DISABLED"
    state = evolution.get_hypothesis_state(conn, "trend_continuation")
    assert state["enabled"] == 0


def test_evolve_does_nothing_on_positive_fitness(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    before = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert applied == []
    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert after == before


def test_evolve_skips_hypothesis_below_minimum_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * 3, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)
    assert applied == []
