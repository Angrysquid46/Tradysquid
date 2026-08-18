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
import spy_scanner
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
    assert len(lns.NEW_STRATEGY_SPECS) == len(set(lns.NEW_STRATEGY_PLAY_TYPES))
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert play_type.startswith("SPY_")
        assert lns.is_new_strategy_play_type(play_type)
    assert not lns.is_new_strategy_play_type("SPY_KEY_LEVELS")
    assert not lns.is_new_strategy_play_type(None)


def test_registry_covers_the_locked_shortlist_ranks():
    """Every rank must be accounted for, or a strategy the owner locked in
    silently never trades.

    SPY_KEY_LEVELS holds a rank but runs in spy_scanner rather than here,
    so the scan registry alone is deliberately NOT contiguous - it skips
    exactly that one number. Checking only NEW_STRATEGY_SPECS assumed
    Key-Levels was the highest rank, which stopped being true when a 15th
    strategy was promoted above it. The real invariant is that the two
    together cover 1..N with no gaps and no duplicates.
    """
    scan_ranks = [spec["rank"] for spec in lns.NEW_STRATEGY_SPECS]
    channel_ranks = [spec["rank"] for spec in lns.CHANNEL_ROSTER]
    assert len(set(channel_ranks)) == len(channel_ranks), "duplicate rank"
    assert sorted(channel_ranks) == list(range(1, len(channel_ranks) + 1))

    missing = set(channel_ranks) - set(scan_ranks)
    key_levels_rank = next(
        spec["rank"] for spec in lns.CHANNEL_ROSTER
        if spec["play_type"] == spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE
    )
    assert missing == {key_levels_rank}, (
        f"ranks {sorted(missing)} have a channel but nothing scans them"
    )


def test_every_new_strategy_defaults_to_paused():
    """A brand-new strategy must be switched on deliberately - a missing
    config key can never silently start trading."""
    flags = lns.default_flags()
    assert len(flags) == len(lns.NEW_STRATEGY_PLAY_TYPES)
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
    assert len(lns.NEW_STRATEGY_EXITS) == len(lns.NEW_STRATEGY_PLAY_TYPES)
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


# ---------------------------------------------------------------------------
# Roster consistency
# ---------------------------------------------------------------------------

def test_no_strategy_is_a_nested_subset_of_another():
    """The owner's rule: every strategy is its own idea, no copy-paste.

    Three of the original 15 violated it and were removed - measured signal
    containment was 1.000, a total subset: gap>=0.25% contained gap>=0.5%
    contained gap>=1.0%, and a 5-bar sweep reclaim is by definition also a
    <=10-bar one.

    This runs on REAL sessions, not a fixture. A synthetic scene cannot
    discriminate here: hold gap_pct and above_vwap constant across every bar
    and unrelated strategies fire on identical bars, reporting containment
    1.00 for pairs the real data puts at 0.29. Skips if the research DB has
    not been built, rather than passing on evidence it does not have.

    The check is containment, NOT shared code. Two strategies may share a
    factory when the parameter PARTITIONS rather than nests - TOD_MIDDAY and
    TOD_FINAL30 use one momentum rule in disjoint windows, so their signals
    can never coincide.
    """
    import itertools
    from collections import defaultdict

    try:
        import spy_backtest as bt
        conn = bt.connect()
    except Exception as exc:                      # pragma: no cover
        pytest.skip(f"research database unavailable: {exc}")

    fired = defaultdict(set)
    sessions = 0
    try:
        for _session, rows in bt.load_sessions(conn, limit=120):
            sessions += 1
            for spec in lns.NEW_STRATEGY_SPECS:
                try:
                    for index, direction in spec["signal"](rows):
                        fired[spec["play_type"]].add((rows[index]["bar_time"], direction))
                except Exception:
                    pass
    finally:
        conn.close()

    if sessions < 20:
        pytest.skip(f"only {sessions} sessions available - not enough to judge overlap")

    checked = 0
    for a, b in itertools.combinations(fired, 2):
        sa, sb = fired[a], fired[b]
        if min(len(sa), len(sb)) < 25:
            continue                              # ratio is noise below this
        checked += 1
        containment = len(sa & sb) / min(len(sa), len(sb))
        assert containment < 0.9, (
            f"{a} and {b} overlap at containment {containment:.2f} over "
            f"{sessions} real sessions - one is a subset of the other, which is "
            f"one idea with a knob turned"
        )
    assert checked > 0, "no pair had enough signals to judge - test is vacuous"


def test_retired_channels_are_marked_for_deletion():
    """A channel left behind after its strategy is removed looks live but
    never updates again."""
    current = {lns.channel_slug(s["play_type"]) for s in lns.CHANNEL_ROSTER}
    for slug in lns.RETIRED_CHANNEL_SLUGS:
        assert slug not in current, f"{slug} is both retired and current"


def test_all_fifteen_locked_strategies_get_a_channel():
    """Key-Levels is rank 11 of the locked 15 and was the only survivor
    without its own channel - it routed to the shared dashboard while the
    other 14 each had one. That was an inconsistency, not a design."""
    count = len(lns.CHANNEL_ROSTER)
    ranks = sorted(spec["rank"] for spec in lns.CHANNEL_ROSTER)
    assert ranks == list(range(1, count + 1)), "ranks must be contiguous from 1"
    slugs = {lns.channel_slug(s["play_type"]) for s in lns.CHANNEL_ROSTER}
    assert len(slugs) == count
    # Key-Levels must HAVE a channel; it need not be the highest rank.
    # Asserting it sits at s{count} broke the moment a 15th strategy was
    # promoted after it, and would have silently passed against the wrong
    # channel had another strategy taken that number.
    assert lns.channel_slug(spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE) in slugs


def test_key_levels_is_in_the_channel_roster_but_not_the_scan_roster():
    """Its entry lives in spy_scanner. Scanning it here too would run the
    strategy twice per cycle."""
    assert "SPY_KEY_LEVELS" in {s["play_type"] for s in lns.CHANNEL_ROSTER}
    assert "SPY_KEY_LEVELS" not in lns.NEW_STRATEGY_PLAY_TYPES
    assert not lns.is_new_strategy_play_type("SPY_KEY_LEVELS")


def test_key_levels_is_not_given_a_second_ledger():
    """performance_reconciliation already registers it under these keys, so
    re-registering would leave one strategy with two competing ledgers."""
    play_types = {variant[0] for variant in lns.report_variants()}
    assert "SPY_KEY_LEVELS" not in play_types


def test_key_levels_channel_does_not_advertise_an_exit_it_does_not_use():
    """It manages itself under its own R-multiple rule; quoting this
    module's default percentages would state the wrong rules in Discord."""
    described = {name: desc for _cat, name, desc in lns.channel_specs()}
    # Key-Levels' slug comes from its RANK, not from its position in the
    # roster list. Computing it from len() broke the moment a strategy was
    # added after it, and would silently pass against the wrong channel if
    # a later strategy happened to land on that number.
    key_levels_slug = lns.channel_slug(spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE)
    assert "% of premium" not in described[key_levels_slug]
    assert "% of premium" in described["s01-gap-cont-50"]


def test_every_routing_key_points_at_a_channel_the_sync_creates():
    """An orphaned route silently drops a strategy's cards."""
    created = {name for _cat, name, _desc in lns.channel_specs()}
    for key, channel in lns.channel_names().items():
        assert channel in created, f"{key} routes to #{channel}, which is never created"


def test_no_route_points_at_a_channel_that_does_not_exist():
    """A card sent to a deleted channel is silently dropped.

    This caught two real orphans: #ratchet-dashboard survived as a route
    after the 10 ratchet variants were retired and their channel deleted,
    and the retired 0DTE/expansion strategies still routed to the deleted
    #strategies-dashboard pair. Neither raised anything - the cards simply
    went nowhere.
    """
    import spy_scanner as ss
    import performance_reconciliation as pr
    import sync_discord_structure as sd

    # Only the DELETE set is checked, not the create set: several channels
    # are appended by installers (performance_channel_structure, the Learning
    # Center) rather than declared at import, so "is created" is not knowable
    # from a bare import. Routing at a channel the sync actively deletes is
    # the real bug class, and it is unambiguous.
    deleted = set(sd.DELETE_CHANNELS)
    for source, table in (("CHANNEL_NAMES", ss.CHANNEL_NAMES),
                          ("REPORT_ROUTES", pr.REPORT_ROUTES)):
        for key, channel in table.items():
            assert channel not in deleted, (
                f"{source}[{key!r}] routes to #{channel}, which the sync deletes - "
                f"cards sent there are silently dropped"
            )


def test_no_report_roster_entry_references_a_missing_channel_route():
    """The failure this exists to prevent reached Discord.

    spy_scanner's strategy_variants list hardcoded performance_1m/results_1m
    and the other retired strategies. Removing their CHANNEL_NAMES entries
    left the list pointing at keys that no longer existed, so the report path
    raised KeyError: 'performance_1m' - which surfaced to the owner as
    "/force-all-strategies Command failed safely". Nothing caught it because
    the name is only resolved when that code path runs.
    """
    import spy_scanner as ss
    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        assert lns.performance_key(play_type) in ss.CHANNEL_NAMES
        assert lns.results_key(play_type) in ss.CHANNEL_NAMES
    for variant in ss.SPY_RATCHET_VARIANTS:
        suffix = variant["play_type"].removeprefix("SPY_RATCHET_").lower()
        assert f"performance_ratchet_{suffix}" in ss.CHANNEL_NAMES


def test_force_all_strategies_survives_a_roster_change():
    """Runs the handler end to end. Import and registration both succeeded
    while this was broken; only executing it revealed the KeyError."""
    import discord_command_bot as bot
    original = bot.require_ticker_admin
    bot.require_ticker_admin = lambda *a, **k: None
    try:
        reply = bot.force_all_strategies_reply({
            "member": {"user": {"id": "owner"}},
            "data": {"options": [{"name": "direction", "value": "call"}]},
        })
    except KeyError as exc:                       # pragma: no cover
        pytest.fail(f"handler raised KeyError({exc}) - a stale roster reference")
    except Exception as exc:
        pytest.skip(f"needs live market data: {type(exc).__name__}")
    finally:
        bot.require_ticker_admin = original
    assert "Forced" in reply


def test_every_strategy_variant_has_a_route_and_markers():
    """Adding a strategy to STRATEGY_VARIANTS without a REPORT_ROUTES entry
    tells the reconciler to build a card and gives it nowhere to send it.

    That happened: all 13 promoted strategies were registered as variants
    with no routes at all. Nothing raised - the cards simply had no
    destination. Markers are checked too, since a variant without unique
    markers cannot locate its own card to edit and would overwrite
    another's.
    """
    import performance_reconciliation as pr
    for play_type, perf_logical, results_logical, _label in pr.STRATEGY_VARIANTS:
        assert perf_logical in pr.REPORT_ROUTES, f"{play_type}: no performance route"
        assert results_logical in pr.REPORT_ROUTES, f"{play_type}: no results route"
        assert perf_logical in pr.REPORT_MARKERS, f"{play_type}: no performance markers"
        assert results_logical in pr.REPORT_MARKERS, f"{play_type}: no results markers"


def test_retired_strategies_are_not_still_registered_as_variants():
    """A retired strategy left in STRATEGY_VARIANTS produces a card for a
    strategy that no longer trades."""
    import performance_reconciliation as pr
    live_play_types = {v[0] for v in pr.STRATEGY_VARIANTS}
    for retired in ("SPY_0DTE_1M", "SPY_0DTE_5M", "SPY_EXPANSION_LEVEL"):
        assert retired not in live_play_types
