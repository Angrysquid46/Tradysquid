from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import strategy_control_cards
import strategy_profiles


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "strategy_profiles.json"


class StrategyProfileFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = strategy_profiles.load_document(CONFIG_PATH)

    def test_required_profiles_are_independent_and_valid(self) -> None:
        self.assertEqual(
            set(self.document["profiles"]),
            set(strategy_profiles.PROFILE_IDENTITIES),
        )
        hashes = {
            name: strategy_profiles.configuration_hash(profile)
            for name, profile in self.document["profiles"].items()
        }
        self.assertEqual(len(hashes), 6)
        self.assertTrue(all(len(value) == 16 for value in hashes.values()))

    def test_current_long_option_defaults_match_live_behavior(self) -> None:
        for name in ("regular-call", "regular-put", "swing-call", "swing-put"):
            profile = self.document["profiles"][name]
            self.assertEqual(profile["exit"]["profit_target"]["value"], 0.20)
            self.assertEqual(profile["exit"]["hard_stop"]["value"], 0.15)
            self.assertFalse(
                profile["management"]["dynamic_profit_protection_enabled"]
            )
            self.assertFalse(profile["management"]["technical_exit_enabled"])

    def test_current_spread_defaults_match_live_behavior(self) -> None:
        for name in ("bull-put-spread", "bear-call-spread"):
            profile = self.document["profiles"][name]
            self.assertEqual(profile["exit"]["profit_target"]["value"], 0.50)
            self.assertEqual(profile["exit"]["hard_stop"]["value"], 2.0)
            self.assertEqual(profile["exit"]["expiration"]["dte"], 5)

    def test_profile_mapping_is_explicit(self) -> None:
        self.assertEqual(
            strategy_profiles.profile_for_trade("REGULAR", "call"),
            "regular-call",
        )
        self.assertEqual(
            strategy_profiles.profile_for_trade("SWING", "put"),
            "swing-put",
        )
        self.assertEqual(
            strategy_profiles.profile_for_trade("SPREAD", "call"),
            "bear-call-spread",
        )
        with self.assertRaises(strategy_profiles.StrategyProfileError):
            strategy_profiles.profile_for_trade("UNKNOWN", "call")

    def test_invalid_cross_field_values_are_rejected(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["profiles"]["regular-call"]["contract_filters"]["dte_min"] = 30
        broken["profiles"]["regular-call"]["contract_filters"]["dte_max"] = 10
        with self.assertRaises(strategy_profiles.StrategyProfileError):
            strategy_profiles.validate_document(broken)

    def test_learning_cannot_apply_changes_automatically(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["profiles"]["regular-call"]["learning"][
            "automatic_application_allowed"
        ] = True
        with self.assertRaises(strategy_profiles.StrategyProfileError):
            strategy_profiles.validate_document(broken)

    def test_runtime_status_requires_both_matching_acknowledgements(self) -> None:
        profile = self.document["profiles"]["regular-call"]
        digest = strategy_profiles.configuration_hash(profile)
        runtime = {
            "profiles": {
                "regular-call": {
                    "scanner": {
                        "version": profile["version"],
                        "configuration_hash": digest,
                        "acknowledged_at": "2026-08-02T16:30:00-05:00",
                    }
                }
            }
        }
        pending = strategy_profiles.registry_snapshot(
            self.document, runtime
        )["profiles"][0]
        self.assertEqual(pending["runtime_status"], "FOUNDATION ONLY")
        runtime["profiles"]["regular-call"]["position_manager"] = {
            "version": profile["version"],
            "configuration_hash": digest,
            "acknowledged_at": "2026-08-02T16:30:01-05:00",
        }
        active = strategy_profiles.registry_snapshot(
            self.document, runtime
        )["profiles"][0]
        self.assertEqual(active["runtime_status"], "ACTIVE")
        self.assertTrue(active["runtime_match"])

    def test_cards_never_claim_active_without_runtime_proof(self) -> None:
        cards = strategy_control_cards.all_profile_cards(
            self.document, {"profiles": {}}
        )
        self.assertEqual(len(cards), 6)
        combined = json.dumps(cards)
        self.assertIn("FOUNDATION ONLY", combined)
        self.assertNotIn('"value": "ACTIVE"', combined)
        self.assertTrue(
            all("STRATEGY-CARD::" in card["description"] for card in cards)
        )

    def test_card_pages_render_exact_settings(self) -> None:
        snapshot = strategy_profiles.registry_snapshot(
            self.document, {"profiles": {}}
        )["profiles"][0]
        contract_card = strategy_control_cards.profile_card(
            snapshot, "contract-filters"
        )
        entry_card = strategy_control_cards.profile_card(snapshot, "entry-rules")
        exit_card = strategy_control_cards.profile_card(snapshot, "exit-rules")
        self.assertIn("max_contract_ask", json.dumps(contract_card))
        self.assertIn("market-regime", json.dumps(entry_card))
        self.assertIn("Profit target", json.dumps(exit_card))

    def test_config_loader_rejects_non_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(strategy_profiles.StrategyProfileError):
                strategy_profiles.load_document(path)


if __name__ == "__main__":
    unittest.main()
