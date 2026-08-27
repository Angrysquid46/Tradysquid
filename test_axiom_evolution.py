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
    half = MIN_SAMPLE_BEFORE_EVOLVE // 2
    pnls = [10.0] * half + [-30.0] * (MIN_SAMPLE_BEFORE_EVOLVE - half)  # mean = -10.0
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


def test_evolve_does_nothing_on_exactly_zero_fitness(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    before = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [0.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert applied == []
    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert after == before


def test_evolve_on_positive_fitness_is_a_noop_when_already_at_the_loose_default(tmp_path, monkeypatch):
    """A never-tightened hypothesis starts AT its loosest bound by design
    (every MUTATION_SPECS field's loose bound equals its own
    HYPOTHESIS_DEFAULTS value) - positive fitness has nowhere looser to
    go yet, so this must be a genuine no-op, not a silent no-change bug."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    before = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert applied == []
    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert after == before


def test_evolve_loosens_one_deterministic_step_after_a_prior_tighten(tmp_path, monkeypatch):
    """Owner directive 2026-08-26 ('evolve as aggressively as it wants'):
    once a hypothesis has been tightened by a losing streak, a later
    winning streak gets it back some room - the mirror of tightening,
    exercised from the only state where loosening has anywhere to go."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    defaults = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "loss")
    tightened_applied = evolution.update_fitness_and_evolve(conn, log_path=None)
    assert tightened_applied and tightened_applied[0]["event"] == "TIGHTENED"
    tightened = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert tightened != defaults

    # hypothesis_fitness averages over ALL attributed trades ever, so the
    # win batch must clearly outweigh the prior loss batch's -50s for the
    # cumulative average to land positive, not merely offset it to zero.
    _attribute_n_trades(sb, conn, "trend_continuation", [200.0] * MIN_SAMPLE_BEFORE_EVOLVE, "win")
    applied = evolution.update_fitness_and_evolve(conn, log_path=None)

    assert len(applied) == 1
    assert applied[0]["event"] == "LOOSENED_PROFITABLE"
    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    specs = MUTATION_SPECS["trend_continuation"]
    for key, (step, lower, upper) in specs.items():
        expected = max(lower, min(upper, tightened[key] - step))
        assert after[key] == expected, key
    # One tighten step then one loosen step must land exactly back at the
    # original default - not past it in either direction.
    assert after == defaults


def test_evolve_loosening_never_exceeds_the_original_default(tmp_path, monkeypatch):
    """Repeated positive-fitness cycles after tightening must clamp at
    the default, not walk past it into something looser than
    parameters.py ever specified."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    defaults = evolution.get_hypothesis_params(conn, "trend_continuation")
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "loss")
    evolution.update_fitness_and_evolve(conn, log_path=None)

    for i in range(20):
        _attribute_n_trades(sb, conn, "trend_continuation", [50.0] * MIN_SAMPLE_BEFORE_EVOLVE, f"g{i}")
        evolution.update_fitness_and_evolve(conn, log_path=None)

    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert after == defaults


def test_evolve_skips_hypothesis_below_minimum_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * 3, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)
    assert applied == []


# --- stale stored params (a row seeded before a HYPOTHESIS_DEFAULTS field
# was added must not crash - this happened live 2026-08-27: trend_continuation's
# stored row predated min_ma_stack_agreement and crashed axiom-evolve) ------

def _drop_key_from_stored_params(conn, name, key):
    import json as _json
    row = conn.execute("SELECT params_json FROM hypothesis_state WHERE name=?", (name,)).fetchone()
    stale = _json.loads(row["params_json"])
    del stale[key]
    conn.execute(
        "UPDATE hypothesis_state SET params_json=? WHERE name=?", (_json.dumps(stale), name)
    )
    conn.commit()


def test_get_hypothesis_params_backfills_a_field_missing_from_a_stale_row(tmp_path):
    conn = _evo_conn(tmp_path)
    _drop_key_from_stored_params(conn, "trend_continuation", "min_ma_stack_agreement")

    params = evolution.get_hypothesis_params(conn, "trend_continuation")

    assert params["min_ma_stack_agreement"] == 2  # HYPOTHESIS_DEFAULTS value, backfilled
    assert params["min_trend_strength_level"] == 2  # untouched fields still present


def test_get_hypothesis_params_prefers_a_real_stored_value_over_the_default(tmp_path):
    """Backfilling a genuinely missing key must never clobber a value
    evolution.py has already tuned away from its default for a key that
    IS present."""
    conn = _evo_conn(tmp_path)
    _drop_key_from_stored_params(conn, "trend_continuation", "min_ma_stack_agreement")
    conn.execute(
        "UPDATE hypothesis_state SET params_json=json_set(params_json, '$.min_trend_strength_level', 3) "
        "WHERE name='trend_continuation'"
    )
    conn.commit()

    params = evolution.get_hypothesis_params(conn, "trend_continuation")

    assert params["min_trend_strength_level"] == 3  # real stored (evolved) value wins
    assert params["min_ma_stack_agreement"] == 2  # missing key still backfilled


def test_evolve_does_not_crash_on_a_stale_row_missing_a_newer_field(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    _drop_key_from_stored_params(conn, "trend_continuation", "min_ma_stack_agreement")
    _attribute_n_trades(sb, conn, "trend_continuation", [-50.0] * MIN_SAMPLE_BEFORE_EVOLVE, "t")

    applied = evolution.update_fitness_and_evolve(conn, log_path=None)  # must not raise

    assert len(applied) == 1
    assert applied[0]["event"] == "TIGHTENED"
    after = evolution.get_hypothesis_params(conn, "trend_continuation")
    assert "min_ma_stack_agreement" in after


def test_drought_does_not_crash_on_a_stale_row_missing_a_newer_field(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    conn = _evo_conn(tmp_path)
    _drop_key_from_stored_params(conn, "trend_continuation", "min_ma_stack_agreement")
    conn.execute(
        "UPDATE hypothesis_state SET updated_at=? WHERE name=?",
        ("2020-01-01T00:00:00-05:00", "trend_continuation"),
    )
    conn.commit()

    applied = evolution.loosen_starved_hypotheses(conn, log_path=None, drought_hours=1.0)  # must not raise

    # Already at every loose bound except the backfilled field, which is
    # ALSO already at its loose default (2) - genuinely nothing to loosen.
    assert applied == []


# --- loosen_starved_hypotheses: drought-based loosening ---------------------

def test_drought_loosens_a_never_fired_hypothesis_past_the_threshold(tmp_path, monkeypatch):
    """A hypothesis with zero attributed trades ever can never reach
    MIN_SAMPLE_BEFORE_EVOLVE, so fitness-based evolution alone could
    never touch it - the drought path is the other half of bidirectional
    evolution, independent of measured fitness."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    conn = _evo_conn(tmp_path)
    defaults = evolution.get_hypothesis_params(conn, "mean_reversion_extreme")
    # Already at the loose default, so there is nothing to loosen yet -
    # tighten it manually first so drought has somewhere real to go.
    specs = MUTATION_SPECS["mean_reversion_extreme"]
    tightened, _ = evolution._tighten(defaults, specs)
    conn.execute(
        "UPDATE hypothesis_state SET params_json=? WHERE name=?",
        (__import__("json").dumps(tightened), "mean_reversion_extreme"),
    )
    conn.commit()
    # Back-date the seed row itself so _hours_since_last_signal() sees a
    # real drought instead of "just seeded a moment ago".
    conn.execute(
        "UPDATE hypothesis_state SET updated_at=? WHERE name=?",
        ("2020-01-01T00:00:00-05:00", "mean_reversion_extreme"),
    )
    conn.commit()

    applied = evolution.loosen_starved_hypotheses(conn, log_path=None, drought_hours=1.0)

    assert len(applied) == 1
    assert applied[0]["event"] == "LOOSENED_DROUGHT"
    assert applied[0]["hypothesis"] == "mean_reversion_extreme"
    after = evolution.get_hypothesis_params(conn, "mean_reversion_extreme")
    for key, (step, lower, upper) in specs.items():
        expected = max(lower, min(upper, tightened[key] - step))
        assert after[key] == expected, key


def test_drought_does_nothing_before_the_threshold_elapses(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    conn = _evo_conn(tmp_path)
    defaults = evolution.get_hypothesis_params(conn, "momentum_acceleration")
    specs = MUTATION_SPECS["momentum_acceleration"]
    tightened, _ = evolution._tighten(defaults, specs)
    conn.execute(
        "UPDATE hypothesis_state SET params_json=? WHERE name=?",
        (__import__("json").dumps(tightened), "momentum_acceleration"),
    )
    conn.commit()
    # updated_at stays "now" (default seed time) - well under the drought
    # threshold.

    applied = evolution.loosen_starved_hypotheses(conn, log_path=None, drought_hours=3.0)

    assert applied == []
    assert evolution.get_hypothesis_params(conn, "momentum_acceleration") == tightened


def test_drought_does_nothing_when_already_at_the_loose_default(tmp_path, monkeypatch):
    """A never-tightened hypothesis is already as loose as it gets - a
    drought must not error or fabricate a change with nowhere to go."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    conn = _evo_conn(tmp_path)
    conn.execute(
        "UPDATE hypothesis_state SET updated_at=? WHERE name=?",
        ("2020-01-01T00:00:00-05:00", "trend_continuation"),
    )
    conn.commit()

    applied = evolution.loosen_starved_hypotheses(conn, log_path=None, drought_hours=1.0)

    assert applied == []


def test_drought_uses_the_most_recent_attributed_trade_not_just_seed_time(tmp_path, monkeypatch):
    """A hypothesis that fired recently must not be treated as starved
    just because it was seeded long ago."""
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    sb = scoreboard.connect_db()
    conn = _evo_conn(tmp_path)
    defaults = evolution.get_hypothesis_params(conn, "trend_continuation")
    specs = MUTATION_SPECS["trend_continuation"]
    tightened, _ = evolution._tighten(defaults, specs)
    conn.execute(
        "UPDATE hypothesis_state SET params_json=?, updated_at=? WHERE name=?",
        (__import__("json").dumps(tightened), "2020-01-01T00:00:00-05:00", "trend_continuation"),
    )
    conn.commit()
    # One real, freshly-attributed trade - the drought clock should reset
    # to that, not the stale 2020 seed timestamp.
    _open_and_close(sb, "recent-1", 10.0)
    evolution.record_trade_attribution(conn, trade_id="recent-1", hypothesis_name="trend_continuation", generation=1)

    applied = evolution.loosen_starved_hypotheses(conn, log_path=None, drought_hours=1.0)

    assert applied == []
    assert evolution.get_hypothesis_params(conn, "trend_continuation") == tightened
