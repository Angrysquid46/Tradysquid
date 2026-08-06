"""Behavioral tests confirming tonight's new settings are actually reachable
from Discord, not just sitting in a config file nobody can touch remotely.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import discord_command_bot as bot
import dynamic_universe
import ford_scan


def _interaction(user_id: str, **options: object) -> dict:
    return {
        "member": {"user": {"id": user_id}},
        "data": {"options": [{"name": name, "value": value} for name, value in options.items()]},
    }


def _with_temp_scanner_config(initial: dict):
    class _Swap:
        def __enter__(self):
            self.original_dynamic = dynamic_universe.SCANNER_CONFIG_PATH
            self.original_ford = ford_scan.SCANNER_CONFIG_PATH
            self.tmp = tempfile.TemporaryDirectory()
            path = Path(self.tmp.name) / "scanner.json"
            path.write_text(json.dumps(initial), encoding="utf-8")
            dynamic_universe.SCANNER_CONFIG_PATH = path
            ford_scan.SCANNER_CONFIG_PATH = path
            return path

        def __exit__(self, *exc):
            dynamic_universe.SCANNER_CONFIG_PATH = self.original_dynamic
            ford_scan.SCANNER_CONFIG_PATH = self.original_ford
            self.tmp.cleanup()

    return _Swap()


BASE_CONFIG = {
    "max_contract_ask": 1.0,
    "max_position_risk_dollars": 100.0,
    "single_leg_profit_target_pct": 0.2,
    "single_leg_stop_pct": 0.15,
    "single_leg_breakeven_trigger_pct": 10.0,
    "single_leg_trail_giveback_pct": 8.0,
    "spread_profit_target_pct": 0.5,
    "spread_stop_multiple": 2.0,
    "trade_types_enabled": {name: True for name in bot.TRADER_NAMES},
}


def test_a_new_tonight_setting_is_now_reachable_through_filter_set():
    original = ford_scan.BREAKEVEN_TRIGGER_PCT
    try:
        with _with_temp_scanner_config(BASE_CONFIG):
            bot.ALLOWED_USER_ID = "owner-1"
            interaction = _interaction(
                "owner-1", filter="single_leg_breakeven_trigger_pct", value=15.0
            )
            reply = bot.filter_set_reply(interaction)
            assert "changed locally from **10.0** to **15.0**" in reply
            saved = json.loads(ford_scan.SCANNER_CONFIG_PATH.read_text())
            assert saved["single_leg_breakeven_trigger_pct"] == 15.0
            assert ford_scan.BREAKEVEN_TRIGGER_PCT == 15.0
    finally:
        # filter_set_reply intentionally mutates the live module constant -
        # that's the feature - so tests must put it back, or every other
        # test that reads BREAKEVEN_TRIGGER_PCT inherits this test's value.
        ford_scan.BREAKEVEN_TRIGGER_PCT = original


def test_filter_set_still_rejects_a_value_outside_its_bounds():
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = _interaction("owner-1", filter="single_leg_delta_erosion_ratio", value=5.0)
        try:
            bot.filter_set_reply(interaction)
            assert False, "should have raised"
        except ValueError as exc:
            assert "must be between" in str(exc)


def test_filter_set_rejects_a_non_owner_even_for_a_valid_setting():
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = _interaction("someone-else", filter="iv_rv_min_ratio", value=1.2)
        try:
            bot.filter_set_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass


def test_trader_toggle_turns_one_trader_off_without_touching_the_others():
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = _interaction("owner-1", trader="bull_put_spreads", enabled=False)
        reply = bot.trader_toggle_reply(interaction)
        assert "bull_put_spreads** disabled" in reply
        saved = json.loads(ford_scan.SCANNER_CONFIG_PATH.read_text())
        assert saved["trade_types_enabled"]["bull_put_spreads"] is False
        assert saved["trade_types_enabled"]["swing_calls"] is True


def test_trader_toggle_rejects_an_unrecognized_trader_name():
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = _interaction("owner-1", trader="iron_condor", enabled=False)
        try:
            bot.trader_toggle_reply(interaction)
            assert False, "should have raised"
        except ValueError as exc:
            assert "not recognized" in str(exc)


def test_toggling_off_via_discord_is_immediately_visible_to_the_scanner():
    # The whole point: what Discord writes, the scanner's own toggle check
    # reads back, with no restart in between.
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        bot.trader_toggle_reply(_interaction("owner-1", trader="swing_puts", enabled=False))
        enabled = ford_scan.trade_types_enabled()
        assert enabled["swing_puts"] is False
        assert enabled["swing_calls"] is True


def test_filters_reply_is_organized_by_play_style_and_does_not_crash():
    with _with_temp_scanner_config(BASE_CONFIG):
        reply = bot.filters_reply()
        assert "Regular calls** (on)" in reply
        assert "Swing calls** (on)" in reply
        assert "Bull put spreads** (on)" in reply
        assert "Shared exit/risk" in reply
        assert "Breakeven trigger" in reply


def test_regular_set_changes_a_regular_only_setting():
    original = ford_scan.REGULAR_SCORE_THRESHOLD
    try:
        with _with_temp_scanner_config(BASE_CONFIG):
            bot.ALLOWED_USER_ID = "owner-1"
            interaction = _interaction("owner-1", filter="regular_score_threshold", value=4.0)
            reply = bot.regular_set_reply(interaction)
            assert "regular_score_threshold" in reply
            assert ford_scan.REGULAR_SCORE_THRESHOLD == 4.0
    finally:
        ford_scan.REGULAR_SCORE_THRESHOLD = original


def test_regular_set_refuses_a_swing_only_setting():
    with _with_temp_scanner_config(BASE_CONFIG):
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = _interaction("owner-1", filter="swing_score_threshold", value=3.0)
        try:
            bot.regular_set_reply(interaction)
            assert False, "should have raised"
        except ValueError as exc:
            assert "not editable from this command" in str(exc)


def test_swing_set_changes_a_swing_only_setting():
    original = ford_scan.SWING_VOLUME_RATIO_MIN
    try:
        with _with_temp_scanner_config(BASE_CONFIG):
            bot.ALLOWED_USER_ID = "owner-1"
            interaction = _interaction("owner-1", filter="swing_volume_ratio_min", value=1.3)
            reply = bot.swing_set_reply(interaction)
            assert "swing_volume_ratio_min" in reply
            assert ford_scan.SWING_VOLUME_RATIO_MIN == 1.3
    finally:
        ford_scan.SWING_VOLUME_RATIO_MIN = original


def test_spread_set_changes_a_spread_only_setting():
    original = ford_scan.SPREAD_EXTREME_BUFFER_PCT
    try:
        with _with_temp_scanner_config(BASE_CONFIG):
            bot.ALLOWED_USER_ID = "owner-1"
            interaction = _interaction("owner-1", filter="spread_extreme_buffer_pct", value=2.0)
            reply = bot.spread_set_reply(interaction)
            assert "spread_extreme_buffer_pct" in reply
            assert ford_scan.SPREAD_EXTREME_BUFFER_PCT == 2.0
    finally:
        ford_scan.SPREAD_EXTREME_BUFFER_PCT = original


def test_every_editable_filter_has_a_matching_runtime_attribute_on_ford_scan():
    # If a setting is Discord-editable, changing it has to actually be able
    # to reach a real constant - this catches a typo in either dict before
    # it ships as a command that silently does nothing.
    for key in bot.EDITABLE_FILTERS:
        attribute_name = bot.RUNTIME_FILTER_ATTRIBUTES.get(key)
        assert attribute_name is not None, f"{key} has no runtime attribute mapping"
        assert hasattr(ford_scan, attribute_name), f"ford_scan has no attribute {attribute_name}"


def test_the_four_setting_groups_do_not_overlap():
    groups = [
        bot.CORE_EDITABLE_FILTERS,
        bot.REGULAR_EDITABLE_FILTERS,
        bot.SWING_EDITABLE_FILTERS,
        bot.SPREAD_EDITABLE_FILTERS,
    ]
    seen: set[str] = set()
    for group in groups:
        overlap = seen & group.keys()
        assert not overlap, f"setting(s) {overlap} appear in more than one command group"
        seen |= group.keys()
