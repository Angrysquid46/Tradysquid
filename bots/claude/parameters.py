"""Phase 13 v2: per-hypothesis mutable parameters, plus the mutation
specs that drive bots/claude/evolution.py's deterministic tightening.

v1 had one global, fixed Parameters object. That was a fair criticism:
a trend-continuation trade and a mean-reversion trade have no principled
reason to share one delta band or one exit shape, and hand-picked
constants that never change aren't "adaptive." Every hypothesis in
HYPOTHESIS_DEFAULTS now owns its own entry thresholds AND its own
position mechanics (delta band, premium cap, profit target, stop), and
MUTATION_SPECS defines, for each tunable field, which direction is
"tighter/more selective" and where the bound is - evolution.py applies
these deterministically (never randomly) when a hypothesis's measured
fitness goes negative.

Every starting value here is a reasoned default, not a measured one -
labeled that way throughout, same basis as market_api_budget.py's
reserve fractions and rivalry.py's rate limits. bots/claude/backtest_runner.py
keeps re-measuring against real data as it accrues; evolution.py is what
actually revises these once real attributed trade outcomes exist.
"""

from __future__ import annotations

# --- shared/global - safety and data-quality mechanics, not edge params ---

MAX_SPREAD_PCT = 0.15
FORCE_CLOSE_HOUR = 14
FORCE_CLOSE_MINUTE = 45
# How many of a hypothesis's OWN attributed closed trades must exist
# before its fitness is judged and it becomes eligible for an evolution
# step. Policy default, not a measured value - gates when a hypothesis is
# old enough to judge, does not block launch.
MIN_SAMPLE_BEFORE_EVOLVE = 10

# --- per-hypothesis starting parameters ---
# Every hypothesis carries the same shared position-mechanics fields
# (delta_min/delta_max/premium_cap_usd/profit_target_pct/stop_loss_pct)
# plus its own entry-specific fields.

HYPOTHESIS_DEFAULTS: dict[str, dict[str, float]] = {
    "trend_continuation": {
        # Wilder's ADX convention already bucketed by market_memory.py's
        # own trend_strength field (0=NONE,1=EMERGING,2=STRONG,3=VERY_STRONG).
        # 2 = requires STRONG or better to start.
        "min_trend_strength_level": 2,
        # Owner directive 2026-08-26: was hardcoded to unanimous (3/3) in
        # hypotheses.py, which blocked a real VERY_STRONG/clear-DI setup
        # for a full session solely because the long-term MA disagreed
        # with short+medium. 2 = majority agreement is the new starting
        # default; evolution.py can still tighten this back toward 3 if
        # majority-agreement entries prove worse, or hold it loose if not.
        "min_ma_stack_agreement": 2,
        "relative_volume_min": 1.2,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 450.0,
        "profit_target_pct": 0.40,
        "stop_loss_pct": -0.35,
    },
    "mean_reversion_extreme": {
        "rsi_extreme_low": 30.0,
        "rsi_extreme_high": 70.0,
        # Opposite precondition of trend_continuation: only fires in a
        # genuinely choppy/non-trending regime. 1 = NONE or EMERGING only.
        "max_trend_strength_level": 1,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 450.0,
        "profit_target_pct": 0.40,
        "stop_loss_pct": -0.35,
    },
    "momentum_acceleration": {
        # market_memory.py's trend_run_length: signed consecutive-bar
        # structural run. A FRESH short run is treated as an inflection
        # in progress, distinct from trend_continuation's "already
        # established, any length" bet.
        "max_run_length": 3,
        "relative_volume_min": 1.3,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 450.0,
        "profit_target_pct": 0.40,
        "stop_loss_pct": -0.35,
    },
}

# --- mutation specs: (step, min_bound, max_bound) ---
# `step` is signed in the direction that makes the hypothesis STRICTER
# (fewer, higher-quality signals). Applying `step` and clamping to
# [min_bound, max_bound] is evolution.py's entire mutation mechanism -
# deterministic, reproducible, no randomness. Every field's loose bound
# (lower if step>0, upper if step<0) is deliberately set equal to that
# field's own HYPOTHESIS_DEFAULTS value, so evolution.py's loosening path
# (added 2026-08-26) can only ever walk a field back to its original
# documented default, never past it - delta_min previously broke this
# (loose bound 0.30 sat below its 0.35 default, an inconsistency from
# before loosening existed), fixed here to match the pattern every other
# field already followed.
_SHARED_POSITION_SPECS: dict[str, tuple[float, float, float]] = {
    "delta_min": (0.02, 0.35, 0.45),
    "delta_max": (-0.02, 0.45, 0.55),
    "premium_cap_usd": (-25.0, 150.0, 450.0),
    "profit_target_pct": (0.05, 0.40, 0.80),
    "stop_loss_pct": (0.03, -0.35, -0.15),
}

MUTATION_SPECS: dict[str, dict[str, tuple[float, float, float]]] = {
    "trend_continuation": {
        "min_trend_strength_level": (1, 2, 3),
        "min_ma_stack_agreement": (1, 2, 3),
        "relative_volume_min": (0.2, 1.2, 3.0),
        **_SHARED_POSITION_SPECS,
    },
    "mean_reversion_extreme": {
        "rsi_extreme_low": (-5.0, 10.0, 30.0),
        "rsi_extreme_high": (5.0, 70.0, 90.0),
        "max_trend_strength_level": (-1, 0, 1),
        **_SHARED_POSITION_SPECS,
    },
    "momentum_acceleration": {
        "max_run_length": (-1, 1, 3),
        "relative_volume_min": (0.2, 1.3, 3.0),
        **_SHARED_POSITION_SPECS,
    },
}
