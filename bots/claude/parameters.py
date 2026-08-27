"""Per-hypothesis mutable parameters, plus the mutation specs that drive
bots/claude/evolution.py's deterministic tightening/loosening.

v1 had one global, fixed Parameters object. That was a fair criticism:
a trend-continuation trade and a mean-reversion trade have no principled
reason to share one delta band or one exit shape, and hand-picked
constants that never change aren't "adaptive." Every hypothesis in
HYPOTHESIS_DEFAULTS owns its own entry thresholds AND its own position
mechanics (delta band, premium cap, profit target, stop), and
MUTATION_SPECS defines, for each tunable field, which direction is
"tighter/more selective" and where the bound is - evolution.py applies
these deterministically (never randomly) when a hypothesis's measured
fitness moves, or when it's gone too long without firing at all.

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
# step. Owner directive 2026-08-26 ("evolve as aggressively as it
# wants"/"self learning path"): lowered from 10 to 6 - a faster feedback
# loop trades some statistical smoothing for AXIOM actually reacting to
# what's happening this generation instead of next one. Still a real
# half-dozen closed trades, not a hair-trigger on 1-2.
MIN_SAMPLE_BEFORE_EVOLVE = 6

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
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
    },
    "mean_reversion_extreme": {
        "rsi_extreme_low": 30.0,
        "rsi_extreme_high": 70.0,
        # Opposite precondition of trend_continuation: only fires in a
        # genuinely choppy/non-trending regime. 1 = NONE or EMERGING only.
        "max_trend_strength_level": 1,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
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
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
    },
    # --- Added 2026-08-26 (owner directive: "build anything with its own
    # signals and aggression") - three more genuinely distinct mechanisms,
    # not variations on the original three. ---
    "vwap_momentum": {
        # SPY around $550-600: 0.05% is roughly $0.28-0.30, a real
        # intraday move off the session's volume-weighted price, not
        # tick noise.
        "min_vwap_distance_pct": 0.05,
        "relative_volume_min": 1.2,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
    },
    "volatility_breakout": {
        # bb_width_pct this tight is a genuine compression regime, not
        # every ordinary quiet bar - most sessions never qualify.
        "max_squeeze_bb_width_pct": 1.5,
        # Breakout confirmation should be volume-heavy - a squeeze that
        # "breaks" on thin volume is usually just noise at the band edge.
        "relative_volume_min": 1.4,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
    },
    "gap_and_go": {
        # 0.15% on SPY is roughly $0.80-0.90 - a gap worth trading, not
        # the routine half-tick most sessions open with.
        "min_gap_pct": 0.15,
        "relative_volume_min": 1.3,
        "delta_min": 0.35,
        "delta_max": 0.55,
        "premium_cap_usd": 500.0,
        "profit_target_pct": 1.00,
        "stop_loss_pct": -0.20,
    },
}

# --- mutation specs: (step, min_bound, max_bound) ---
# `step` is signed in the direction that makes the hypothesis STRICTER
# (fewer, higher-quality signals). Applying `step` and clamping to
# [min_bound, max_bound] is evolution.py's entire mutation mechanism -
# deterministic, reproducible, no randomness. Every field's loose bound
# (lower if step>0, upper if step<0) is deliberately set equal to that
# field's own HYPOTHESIS_DEFAULTS value, so evolution.py's loosening path
# can only ever walk a field back to its original documented default,
# never past it.
_SHARED_POSITION_SPECS: dict[str, tuple[float, float, float]] = {
    "delta_min": (0.02, 0.35, 0.45),
    "delta_max": (-0.02, 0.45, 0.55),
    "premium_cap_usd": (-25.0, 150.0, 500.0),
    # Owner directive 2026-08-27 ("you chose to pick the hottest pile of
    # shit imaginable"): default changed from a near-symmetric 40%/-35%
    # (needed ~47% win rate to break even, measured win rate was 22-31%)
    # to a genuinely asymmetric cut-losses-fast/let-winners-run shape.
    # Tested directly against the real backtest with the exact same
    # entries, only the exit math changed: 40/-35 lost -$1,646; 100/-20
    # made +$748. Bounds widened to match - tighten still walks toward a
    # bigger required win (2.00) or a tighter stop (-0.10), loosen still
    # bottoms out at this new, verified default, never past it.
    "profit_target_pct": (0.10, 1.00, 2.00),
    "stop_loss_pct": (0.02, -0.20, -0.10),
}

# Exported so evolution.py's extreme-drought loosening (owner directive
# 2026-08-27: a hypothesis that can only ever walk back to its ORIGINAL
# default has no answer for a structurally quiet session where even the
# default is too strict - "you win contests with 0 work" was a fair call
# on that gap) knows which fields are position MECHANICS (what happens
# once a trade fires) versus entry GATES (whether one ever can) - only
# the latter get pushed past their normal floor under sustained drought.
SHARED_POSITION_KEYS = frozenset(_SHARED_POSITION_SPECS.keys())

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
    "vwap_momentum": {
        # Default (loose bound) 0.05 - tighten walks the required
        # distance-off-vwap UP toward 0.20 (stricter: only the biggest
        # moves qualify).
        "min_vwap_distance_pct": (0.02, 0.05, 0.20),
        "relative_volume_min": (0.2, 1.2, 3.0),
        **_SHARED_POSITION_SPECS,
    },
    "volatility_breakout": {
        # Default (loose bound) 1.5 is the upper bound here - tighten
        # walks the max allowed width DOWN toward 0.5 (stricter: demands
        # a tighter coil before it'll trade the break).
        "max_squeeze_bb_width_pct": (-0.25, 0.5, 1.5),
        "relative_volume_min": (0.2, 1.4, 3.0),
        **_SHARED_POSITION_SPECS,
    },
    "gap_and_go": {
        "min_gap_pct": (0.05, 0.15, 0.50),
        "relative_volume_min": (0.2, 1.3, 3.0),
        **_SHARED_POSITION_SPECS,
    },
}
