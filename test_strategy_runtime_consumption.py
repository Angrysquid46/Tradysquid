from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import strategy_profiles
import strategy_runtime_consumption as runtime


class StrategyRuntimeConsumptionTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime._CACHED_DOCUMENT = None
        runtime._LAST_LOAD_META = {}

    def paths(self, directory: str):
        root = Path(directory)
        return patch.multiple(
            runtime,
            ACTIVE_CONFIG_PATH=root / "strategy-active.json",
            LAST_VALID_CONFIG_PATH=root / "strategy-last-valid.json",
            RUNTIME_STATE_PATH=root / "strategy-runtime.json",
            TRADE_PLAN_DIR=root / "strategy-trade-plans",
        )

    def fake_module(self):
        observed: dict[str, object] = {}
        module = SimpleNamespace(
            LOG_HEADER=["trade_id", "play_type", "call_or_put"],
            REGULAR_MIN_DTE=7,
            REGULAR_MAX_DTE=20,
            MIN_DTE=21,
            MAX_DTE=45,
            STRIKE_BAND_PCT=0.12,
            REENTRY_COOLDOWN_MINUTES=1440,
            MIN_OPEN_INTEREST=100,
            MIN_OPTION_VOLUME=1,
            MAX_BID_ASK_PCT=0.25,
            MAX_RISK_PER_TRADE=100.0,
            SINGLE_LEG_DELTA_MIN=0.2,
            SINGLE_LEG_DELTA_MAX=0.8,
            MAX_CONTRACT_ASK=1.0,
            SPREAD_SHORT_DELTA_MIN=0.1,
            SPREAD_SHORT_DELTA_MAX=0.25,
            MIN_SPREAD_CREDIT=0.05,
            SINGLE_STOP_PCT=0.15,
            SINGLE_TAKE_PROFIT_PCT=0.20,
            SPREAD_STOP_MULTIPLE=2.0,
            SPREAD_TAKE_PROFIT_PCT=0.50,
            SPREAD_EXIT_DTE=5,
        )

        def pick_expirations(expirations, today):
            observed["dte"] = (
                module.REGULAR_MIN_DTE,
                module.REGULAR_MAX_DTE,
                module.MIN_DTE,
                module.MAX_DTE,
            )
            return ["regular"], ["swing"]

        def filter_strikes(strikes, spot):
            observed["strike_band"] = module.STRIKE_BAND_PCT
            return list(strikes)

        def recently_tracked(rows, candidate, timestamp):
            observed["cooldown"] = module.REENTRY_COOLDOWN_MINUTES
            return False

        def scan_single_legs(chain, kind, expiration, play_type, market_context=None):
            observed["single"] = {
                "oi": module.MIN_OPEN_INTEREST,
                "volume": module.MIN_OPTION_VOLUME,
                "spread": module.MAX_BID_ASK_PCT,
                "risk": module.MAX_RISK_PER_TRADE,
                "delta": (module.SINGLE_LEG_DELTA_MIN, module.SINGLE_LEG_DELTA_MAX),
                "ask": module.MAX_CONTRACT_ASK,
            }
            return [
                {
                    "play_type": play_type,
                    "call_or_put": kind,
                    "expiration": expiration,
                }
            ]

        def scan_credit_spreads(chain, kind, expiration, market_context=None):
            observed["spread"] = {
                "delta": (
                    module.SPREAD_SHORT_DELTA_MIN,
                    module.SPREAD_SHORT_DELTA_MAX,
                ),
                "credit": module.MIN_SPREAD_CREDIT,
                "risk": module.MAX_RISK_PER_TRADE,
            }
            return [
                {
                    "play_type": "SPREAD",
                    "call_or_put": kind,
                    "expiration": expiration,
                }
            ]

        def candidate_to_row(candidate, rows, timestamp):
            return {
                "trade_id": "TEST-TRADE-001",
                "play_type": candidate["play_type"],
                "call_or_put": candidate["call_or_put"],
            }

        def evaluate_open_row(row, quotes, timestamp):
            observed["manager"] = {
                "single_stop": module.SINGLE_STOP_PCT,
                "single_target": module.SINGLE_TAKE_PROFIT_PCT,
                "spread_stop": module.SPREAD_STOP_MULTIPLE,
                "spread_target": module.SPREAD_TAKE_PROFIT_PCT,
                "spread_exit_dte": module.SPREAD_EXIT_DTE,
            }
            return {"signal": "HOLD", "mark": 1.0, "pl_pct": 0}

        module.pick_expirations = pick_expirations
        module.filter_strikes = filter_strikes
        module.recently_tracked = recently_tracked
        module.scan_single_legs = scan_single_legs
        module.scan_credit_spreads = scan_credit_spreads
        module.candidate_to_row = candidate_to_row
        module.evaluate_open_row = evaluate_open_row
        return module, observed

    def test_default_profiles_are_supported_by_current_adapter(self) -> None:
        document = runtime.validate_adapter_document(strategy_profiles.load_document())
        self.assertEqual(set(document["profiles"]), set(strategy_profiles.PROFILE_IDENTITIES))
        self.assertEqual(
            document["profiles"]["regular-call"]["exit"]["profit_target"]["value"],
            0.20,
        )
        self.assertEqual(
            document["profiles"]["regular-call"]["exit"]["hard_stop"]["value"],
            0.15,
        )
        self.assertEqual(
            document["profiles"]["bull-put-spread"]["exit"]["hard_stop"]["value"],
            2.0,
        )

    def test_install_acknowledges_all_profiles_for_both_consumers(self) -> None:
        module, _ = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            health = runtime.install(module)
            state = json.loads(runtime.RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(state["profiles"]), set(strategy_profiles.PROFILE_IDENTITIES))
        for profile in state["profiles"].values():
            self.assertIn("scanner", profile)
            self.assertIn("position_manager", profile)
            self.assertEqual(
                profile["scanner"]["configuration_hash"],
                profile["position_manager"]["configuration_hash"],
            )
        self.assertTrue(health["paper_trading_only"])
        self.assertFalse(health["updater_involved"])
        for field in runtime.STRATEGY_ROW_FIELDS:
            self.assertIn(field, module.LOG_HEADER)

    def test_scanner_uses_matching_profile_values_and_tags_candidates(self) -> None:
        module, observed = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            runtime.install(module)
            candidates = module.scan_single_legs([], "call", "2026-08-21", "REGULAR")
        self.assertEqual(observed["single"]["delta"], (0.2, 0.8))
        self.assertEqual(observed["single"]["ask"], 1.0)
        self.assertEqual(observed["single"]["risk"], 100.0)
        self.assertEqual(candidates[0]["strategy_profile"], "regular-call")
        self.assertEqual(candidates[0]["strategy_version"], "1.0.0")
        self.assertEqual(len(candidates[0]["strategy_configuration_hash"]), 16)

    def test_spread_scanner_uses_spread_profile_values(self) -> None:
        module, observed = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            runtime.install(module)
            candidates = module.scan_credit_spreads([], "put", "2026-09-18")
        self.assertEqual(observed["spread"]["delta"], (0.1, 0.25))
        self.assertEqual(observed["spread"]["credit"], 0.05)
        self.assertEqual(candidates[0]["strategy_profile"], "bull-put-spread")

    def test_entry_creates_immutable_trade_plan_and_pins_old_exit_values(self) -> None:
        module, observed = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            runtime.install(module)
            row = module.candidate_to_row(
                {"play_type": "REGULAR", "call_or_put": "call"},
                [],
                object(),
            )
            plan_path = runtime._snapshot_path("TEST-TRADE-001")
            self.assertTrue(plan_path.exists())
            self.assertEqual(row["strategy_snapshot_status"], "ENTRY-PINNED")
            original_hash = row["strategy_configuration_hash"]

            changed = runtime.load_active_document()
            changed["profiles"]["regular-call"]["version"] = "1.0.1"
            changed["profiles"]["regular-call"]["exit"]["profit_target"]["value"] = 0.10
            runtime._atomic_json(runtime.ACTIVE_CONFIG_PATH, changed)
            runtime._CACHED_DOCUMENT = None

            evaluation = module.evaluate_open_row(row, {}, object())
        self.assertEqual(observed["manager"]["single_target"], 0.20)
        self.assertEqual(evaluation["strategy_version"], "1.0.0")
        self.assertEqual(evaluation["strategy_configuration_hash"], original_hash)

    def test_legacy_open_trade_is_labeled_without_inventing_entry_history(self) -> None:
        module, _ = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            runtime.install(module)
            row = {
                "trade_id": "LEGACY-001",
                "play_type": "SWING",
                "call_or_put": "put",
            }
            module.evaluate_open_row(row, {}, object())
            payload = json.loads(
                runtime._snapshot_path("LEGACY-001").read_text(encoding="utf-8")
            )
        self.assertEqual(row["strategy_profile"], "swing-put")
        self.assertEqual(row["strategy_snapshot_status"], "LEGACY-RUNTIME-ASSIGNED")
        self.assertEqual(payload["snapshot_status"], "LEGACY-RUNTIME-ASSIGNED")

    def test_invalid_active_edit_falls_back_to_last_valid_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            valid = runtime.load_active_document()
            invalid = copy.deepcopy(valid)
            invalid["profiles"]["regular-call"]["entry"]["rules"][0]["parameters"][
                "daily_sma_fast_period"
            ] = 12
            runtime._atomic_json(runtime.ACTIVE_CONFIG_PATH, invalid)
            runtime._CACHED_DOCUMENT = None
            loaded = runtime.load_active_document()
            metadata = runtime.last_load_metadata()
        self.assertEqual(
            loaded["profiles"]["regular-call"]["entry"]["rules"][0]["parameters"][
                "daily_sma_fast_period"
            ],
            20,
        )
        self.assertTrue(metadata["fallback_used"])
        self.assertIn("later rule engine", metadata["error"])

    def test_dte_strike_and_cooldown_wrappers_use_profile_document(self) -> None:
        module, observed = self.fake_module()
        with tempfile.TemporaryDirectory() as directory, self.paths(directory):
            runtime.install(module)
            module.pick_expirations([], object())
            module.filter_strikes([10.0], 10.0)
            module.recently_tracked(
                [], {"play_type": "REGULAR", "call_or_put": "call"}, object()
            )
        self.assertEqual(observed["dte"], (7, 20, 21, 45))
        self.assertEqual(observed["strike_band"], 0.12)
        self.assertEqual(observed["cooldown"], 1440)


if __name__ == "__main__":
    unittest.main()
