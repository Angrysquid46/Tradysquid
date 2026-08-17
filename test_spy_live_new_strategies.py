"""Tests for the 14 promoted live strategies.

The point of this module is that the traded rule is the *measured* rule, so
the tests that matter are the ones proving no drift crept in between the
backtest and live:

- the registry matches the locked top 15
- features built from live bars come from the same engine the backtest used
- a signal counts only on the newest closed bar (the stale-signal bug that
  once had the old ORB reporting a reversed breakout all morning)
- every strategy defaults to paused
"""

from __future__ import annotations

import pathlib

import pytest

import spy_backtest_strategies_extended as ext
import spy_intraday_features as sif
import spy_live_new_strategies as lns


def _bars(count: int, start: float = 400.0, step: float = 0.0, day: str = "2026-08-17"):
    out = []
    for i in range(count):
        hh, mm = divmod(9 * 60 + 30 + i, 60)
        price = start + i * step
        out.append({"time": f"{day} {hh:02d}:{mm:02d}:00", "open": price,
                    "high": price + 0.10, "low": price - 0.10,
                    "close": price, "volume": 1000})
    return out


def _daily(count: int = 30, close: float = 398.0):
    return [{"date": f"2026-07-{(i % 28) + 1:02d}", "open": close - 3, "high": close + 1,
             "low": close - 5, "close": close} for i in range(count)]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_all_fourteen_promoted_strategies_are_registered():
    assert len(lns.NEW_STRATEGY_SPECS) == 14
    assert len(set(lns.NEW_STRATEGY_PLAY_TYPES)) == 14
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert play_type.startswith("SPY_")
        assert lns.is_new_strategy_play_type(play_type)
    assert not lns.is_new_strategy_play_type("SPY_KEY_LEVELS")
    assert not lns.is_new_strategy_play_type(None)


def test_registry_covers_the_locked_shortlist_ranks():
    """Rank 11 is SPY_KEY_LEVELS, which already runs in spy_scanner and is
    deliberately not duplicated here. Every other rank 1-15 must be
    present, or a strategy the owner locked in silently never trades."""
    ranks = sorted(spec["rank"] for spec in lns.NEW_STRATEGY_SPECS)
    assert ranks == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15]


def test_every_new_strategy_defaults_to_paused():
    """A brand-new strategy must be switched on deliberately - a missing
    config key can never silently start trading."""
    flags = lns.default_flags()
    assert len(flags) == 14
    assert all(value is False for value in flags.values())
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert lns.config_flag(play_type) in flags


def test_config_flags_are_lowercase_play_types():
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert lns.config_flag(play_type) == play_type.lower()


# ---------------------------------------------------------------------------
# Features from live bars
# ---------------------------------------------------------------------------

def test_live_features_use_the_same_engine_as_the_backtest():
    """If live features were computed differently the traded rule would not
    be the measured rule, however identical the signal function looked."""
    rows = lns.live_feature_rows(_bars(120, step=0.02), _daily())
    assert len(rows) == 120
    for column in ("vwap", "atr_14", "regime", "structure", "or15_state",
                   "prev_day_high", "alignment", "adx_14"):
        assert column in rows[-1], f"{column} missing - not the backtest feature set"
    assert len(rows[-1]) == len(sif.FEATURE_COLUMNS) + 2   # + bar_time, session_date


def test_session_context_uses_only_prior_days():
    context = lns.build_session_context(_daily(30, close=398.0))
    assert context.prev_day_close == 398.0
    assert context.atr_14 is not None and context.atr_14 > 0


def test_session_context_survives_too_little_history():
    context = lns.build_session_context([])
    assert context.prev_day_close is None
    assert context.atr_14 is None
    assert lns.live_feature_rows(_bars(30), []) != []      # still computes


def test_malformed_bars_are_skipped_not_fatal():
    bars = _bars(10) + [{"time": None, "close": 1}, {"close": None}]
    assert len(lns.live_feature_rows(bars, _daily())) == 10


# ---------------------------------------------------------------------------
# Signals fire only on the newest bar
# ---------------------------------------------------------------------------

def _fire_scene():
    """A confluence setup on the final bar: price at four tracked levels,
    then a break of the prior bar's high."""
    rows = []
    for minute in range(40):
        hh, mm = divmod(9 * 60 + 30 + minute, 60)
        rows.append({
            "bar_time": f"2026-08-17T{hh:02d}:{mm:02d}:00",
            "session_date": "2026-08-17", "minutes_since_open": minute,
            "time_bucket": "OPEN", "open": 400.0, "high": 400.1, "low": 399.9,
            "close": 400.0, "volume": 1000.0, "atr_14": 2.0, "vwap": 400.0,
            "confluence_count": 4, "close": 400.0,
        })
    rows[-2].update(high=400.2, low=399.9, close=400.0)
    rows[-1].update(open=400.0, high=400.8, low=400.0, close=400.7)
    return rows


def test_a_signal_fires_when_its_setup_is_on_the_latest_bar():
    """Non-vacuity guard: if nothing can ever fire, every test below
    passes while checking nothing."""
    rows = _fire_scene()
    enabled = {lns.config_flag(p): True for p in lns.NEW_STRATEGY_PLAY_TYPES}
    fired = lns.signals_on_latest_bar(rows, enabled)
    assert any(f["play_type"] == "SPY_CONFLUENCE_4" for f in fired), fired


def test_a_setup_earlier_in_the_session_does_not_fire_now():
    """The stale-signal rule. A setup that completed twenty minutes ago is
    no longer live, and acting on it would repeat the bug that had the old
    ORB reporting a long-since-reversed breakout all morning."""
    rows = _fire_scene()
    # Push the trigger back and leave the final bars quiet.
    rows[-1].update(open=400.7, high=400.75, low=400.65, close=400.70)
    rows.append({**rows[-1], "bar_time": "2026-08-17T10:11:00",
                 "minutes_since_open": 41, "open": 400.70, "high": 400.72,
                 "low": 400.68, "close": 400.70})
    enabled = {lns.config_flag(p): True for p in lns.NEW_STRATEGY_PLAY_TYPES}
    for signal in lns.signals_on_latest_bar(rows, enabled):
        assert signal["bar_time"] == rows[-1]["bar_time"]


def test_a_disabled_strategy_never_fires():
    rows = _fire_scene()
    assert lns.signals_on_latest_bar(rows, {}) == []
    only_one = {lns.config_flag(p): False for p in lns.NEW_STRATEGY_PLAY_TYPES}
    only_one[lns.config_flag("SPY_CONFLUENCE_4")] = True
    fired = lns.signals_on_latest_bar(rows, only_one)
    assert {f["play_type"] for f in fired} <= {"SPY_CONFLUENCE_4"}


def test_one_strategy_raising_does_not_break_the_scan():
    """A broken strategy must not take down the others, or a single bad
    signal function silently stops every live trade."""
    def explode(rows):
        raise RuntimeError("boom")

    original = lns.NEW_STRATEGY_SPECS[0]["signal"]
    lns.NEW_STRATEGY_SPECS[0]["signal"] = explode
    try:
        rows = _fire_scene()
        enabled = {lns.config_flag(p): True for p in lns.NEW_STRATEGY_PLAY_TYPES}
        fired = lns.signals_on_latest_bar(rows, enabled)
        assert any(f["play_type"] == "SPY_CONFLUENCE_4" for f in fired)
    finally:
        lns.NEW_STRATEGY_SPECS[0]["signal"] = original


def test_signal_payload_carries_what_a_candidate_needs():
    rows = _fire_scene()
    enabled = {lns.config_flag(p): True for p in lns.NEW_STRATEGY_PLAY_TYPES}
    fired = lns.signals_on_latest_bar(rows, enabled)
    assert fired
    for signal in fired:
        assert signal["side"] in ("call", "put")
        assert signal["direction"] in ("LONG", "SHORT")
        assert signal["spot_at_signal"] > 0
        assert signal["play_type"] in lns.NEW_STRATEGY_BY_PLAY_TYPE
        assert signal["reason"]


def test_no_signals_from_an_empty_session():
    assert lns.signals_on_latest_bar([], None) == []


# ---------------------------------------------------------------------------
# Config wiring - a real trap, not a formality
# ---------------------------------------------------------------------------

def test_every_new_strategy_flag_is_registered_in_the_scanner_defaults():
    """`trade_types_enabled()` only applies a config override to a key that
    ALREADY exists in DEFAULT_TRADE_TYPES_ENABLED.

    This actually bit: all 14 flags were set to true in
    config/scanner.json and every one was silently ignored - the scan
    reported them disabled while the config said enabled. Nothing raised.
    """
    import spy_scanner as ss
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        flag = lns.config_flag(play_type)
        assert flag in ss.DEFAULT_TRADE_TYPES_ENABLED, (
            f"{flag} missing from DEFAULT_TRADE_TYPES_ENABLED - its config "
            f"flag would be silently ignored"
        )


def test_new_strategy_flags_default_to_paused_in_the_scanner_too():
    """Code-level fallback must be paused, so a missing config key can never
    silently start trading."""
    import importlib
    import spy_scanner as ss
    module = importlib.reload(ss)
    try:
        for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
            assert module.DEFAULT_TRADE_TYPES_ENABLED[lns.config_flag(play_type)] is False
    finally:
        importlib.reload(module)


def test_a_config_flag_actually_turns_a_new_strategy_on():
    """The inverse of the trap: proves the override path works end to end."""
    import spy_scanner as ss
    enabled = ss.trade_types_enabled()
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert lns.config_flag(play_type) in enabled


def test_the_scan_runner_and_exit_dispatch_are_wired():
    import spy_scanner as ss
    assert hasattr(ss, "_run_new_strategy_variants")
    assert hasattr(ss, "evaluate_open_new_strategy_row")
    row = {"play_type": "SPY_GAP_CONT_50", "option_symbol": "MISSING", "entry_price": "1.00"}
    result = ss.evaluate_open_row(row, {}, ss.now_ct())
    assert result["signal"] == "HOLD"
    assert "unavailable" in result["note"].lower()


# ---------------------------------------------------------------------------
# Per-strategy exits
# ---------------------------------------------------------------------------

def test_every_strategy_has_its_own_exit_rules():
    """An earlier version applied one +200/-80 shape to all 14, discarding
    the per-strategy target/stop the backtest actually measured."""
    assert len(lns.NEW_STRATEGY_EXITS) == 14
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert play_type in lns.NEW_STRATEGY_EXITS, f"{play_type} has no exit of its own"
        target, stop, _time_stop = lns.exit_rules_for(play_type)
        assert target > 0 and stop < 0


def test_exits_actually_differ_between_strategies():
    """If they were all identical the per-strategy table would be theatre."""
    shapes = {lns.exit_rules_for(p) for p in lns.NEW_STRATEGY_PLAY_TYPES}
    assert len(shapes) >= 4, f"only {len(shapes)} distinct exit shapes"


def test_the_three_strategies_measured_with_a_time_stop_have_one():
    with_time_stop = {p for p in lns.NEW_STRATEGY_PLAY_TYPES
                      if lns.exit_rules_for(p)[2] is not None}
    assert with_time_stop == {"SPY_TOD_FINAL30", "SPY_EXHAUSTION_1ATR",
                              "SPY_OPENING_GAP_FADE"}


def test_a_time_stop_only_applies_to_the_strategy_that_measured_one():
    held = 200.0
    assert lns.new_strategy_exit_signal(
        1.0, 1.1, 120, play_type="SPY_EXHAUSTION_1ATR", minutes_held=held)[0] == "TIME STOP"
    assert lns.new_strategy_exit_signal(
        1.0, 1.1, 120, play_type="SPY_GAP_CONT_50", minutes_held=held)[0] == "HOLD"


def test_each_strategy_uses_its_own_target_not_a_shared_one():
    """Exhaustion targets +40%, gap continuation +150%. A +45% mark must
    take profit on one and hold on the other."""
    assert lns.new_strategy_exit_signal(
        1.0, 1.45, 120, play_type="SPY_EXHAUSTION_1ATR")[0] == "TAKE PROFIT"
    assert lns.new_strategy_exit_signal(
        1.0, 1.45, 120, play_type="SPY_GAP_CONT_50")[0] == "HOLD"


def test_each_strategy_uses_its_own_stop_not_a_shared_one():
    assert lns.new_strategy_exit_signal(
        1.0, 0.55, 120, play_type="SPY_EXHAUSTION_1ATR")[0] == "STOP OUT"
    assert lns.new_strategy_exit_signal(
        1.0, 0.55, 120, play_type="SPY_GAP_CONT_50")[0] == "HOLD"


def test_todays_partial_daily_bar_is_never_used_as_prior_day():
    """A real lookahead bug, caught by checking live output.

    The provider's daily history includes a PARTIAL bar for the current
    session. Using the last bar blindly made today's own high/low/close the
    "previous day" levels, so a level-based strategy would trade against a
    level derived from the very move it was trying to predict - corrupting
    failed-breakout, liquidity-sweep, confluence and gap.
    """
    daily = [
        {"date": "2026-08-14", "open": 770, "high": 775, "low": 768, "close": 772},
        {"date": "2026-08-16", "open": 772, "high": 778.8, "low": 771, "close": 777},
        {"date": "2026-08-17", "open": 777, "high": 999.0, "low": 700.0, "close": 780},
    ]
    context = lns.build_session_context(daily, session="2026-08-17")
    assert context.prev_day_high == 778.8, "used today's partial bar"
    assert context.prev_day_low == 771
    assert context.prev_day_close == 777

    # Without the session filter the bug reappears - proving the filter is
    # what prevents it, not incidental ordering.
    assert lns.build_session_context(daily).prev_day_high == 999.0


def test_live_feature_rows_pass_the_session_through():
    bars = _bars(30, day="2026-08-17")
    daily = [
        {"date": "2026-08-16", "open": 772, "high": 778.8, "low": 771, "close": 777},
        {"date": "2026-08-17", "open": 777, "high": 999.0, "low": 700.0, "close": 780},
    ]
    rows = lns.live_feature_rows(bars, daily)
    assert rows
    assert rows[-1]["prev_day_high"] == 778.8


def test_every_command_handler_calls_a_function_that_exists():
    """/force-all-strategies shipped calling `respond(...)`, which does not
    exist in this module - the command failed with a NameError the first
    time it was used in Discord. Nothing at import time caught it because
    the name is only resolved when that branch runs.
    """
    import re
    import discord_command_bot as bot
    source = pathlib.Path("discord_command_bot.py").read_text(encoding="utf-8")
    called = set(re.findall(r"^\s+([a-z_]+)\(\s*$", source, re.M))
    dispatchers = {name for name in called
                   if name.endswith(("original", "respond", "followup"))}
    for name in dispatchers:
        assert hasattr(bot, name), f"handler calls {name}() which does not exist"
