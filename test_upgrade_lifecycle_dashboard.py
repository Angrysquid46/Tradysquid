from __future__ import annotations

import unittest

import upgrade_lifecycle_dashboard as lifecycle


class UpgradeLifecycleDashboardTests(unittest.TestCase):
    def batch(self, state="READY"):
        return {
            "state": state,
            "issue_number": 44,
            "request_count": 2,
            "requests": [
                {
                    "request_number": 1,
                    "source": "OWNER REQUEST",
                    "summary": "Add a feature",
                },
                {
                    "request_number": 2,
                    "source": "AUTOMATIC DIAGNOSTIC",
                    "summary": "Repair a failure",
                },
            ],
        }

    def test_open_batch_is_pending(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch("OPEN"), [], {}, verified=False, verification_reason=""
        )
        self.assertEqual(result.state, "PENDING")
        self.assertIn("/upgrade-ready", result.next_action)

    def test_ready_batch_without_implementation_stays_upgrade_ready(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(), [], {}, verified=False, verification_reason="no receipt"
        )
        self.assertEqual(result.state, "UPGRADE READY")
        self.assertIn("Maintainer", result.next_action)

    def test_failing_ci_is_failed_validation(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [{"ci_state": "FAILURE"}],
            {},
            verified=False,
            verification_reason="",
        )
        self.assertEqual(result.state, "FAILED VALIDATION")

    def test_successful_ci_is_not_reported_as_deployed(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [{"ci_state": "SUCCESS"}],
            {},
            verified=False,
            verification_reason="",
        )
        self.assertEqual(result.state, "CI PASSED")
        self.assertNotEqual(result.state, "DEPLOYED")

    def test_remote_commit_waiting_on_laptop_is_deployment_pending(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [],
            {
                "last_remote_sha": "bbbbbbbbbbbb",
                "deployed_sha": "aaaaaaaaaaaa",
            },
            verified=False,
            verification_reason="",
        )
        self.assertEqual(result.state, "DEPLOYMENT PENDING")

    def test_deployed_without_post_deployment_receipts_is_not_verified(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [],
            {
                "last_update_status": "DEPLOYED",
                "local_sha": "aaaaaaaaaaaa",
                "deployed_sha": "aaaaaaaaaaaa",
                "last_remote_sha": "aaaaaaaaaaaa",
            },
            verified=False,
            verification_reason="self diagnostics pending",
        )
        self.assertEqual(result.state, "DEPLOYED")
        self.assertIn("Wait", result.next_action)

    def test_verified_requires_explicit_post_deployment_proof(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [],
            {
                "last_update_status": "DEPLOYED",
                "local_sha": "aaaaaaaaaaaa",
                "deployed_sha": "aaaaaaaaaaaa",
                "last_remote_sha": "aaaaaaaaaaaa",
            },
            verified=True,
            verification_reason="diagnostics and applied-upgrades receipts passed",
        )
        self.assertEqual(result.state, "VERIFIED")
        self.assertIn("receipts passed", result.reason)

    def test_rollback_overrides_all_optimistic_states(self) -> None:
        result = lifecycle.derive_lifecycle(
            self.batch(),
            [{"ci_state": "SUCCESS"}],
            {
                "last_update_status": "ROLLED_BACK",
                "last_update_detail": "test failed",
            },
            verified=True,
            verification_reason="old proof",
        )
        self.assertEqual(result.state, "ROLLED BACK")
        self.assertIn("test failed", result.reason)

    def test_render_names_source_commit_and_exact_next_action(self) -> None:
        state = {
            "local_sha": "aaaaaaaaaaaa",
            "deployed_sha": "aaaaaaaaaaaa",
            "last_remote_sha": "bbbbbbbbbbbb",
        }
        derived = lifecycle.Lifecycle(
            "DEPLOYMENT PENDING",
            "Leave the updater running.",
            "remote differs from deployed",
        )
        text = lifecycle.render(self.batch(), [], state, derived)
        self.assertIn("OWNER REQUEST", text)
        self.assertIn("AUTOMATIC DIAGNOSTIC", text)
        self.assertIn("Exact next action", text)
        self.assertIn("aaaaaaaaaaaa", text)
        self.assertIn("bbbbbbbbbbbb", text)


if __name__ == "__main__":
    unittest.main()
