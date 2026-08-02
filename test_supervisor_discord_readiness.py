from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_supervisor_resilient as resilient


class SupervisorDiscordReadinessTests(unittest.TestCase):
    def test_command_timeout_is_retryable_but_nonblocking(self) -> None:
        results = [
            "command registration failed: requests.exceptions.ConnectTimeout",
            "Strictly ordered Learning Center and permissions synchronized",
        ]
        self.assertTrue(resilient.command_registration_failed(results))
        self.assertFalse(resilient.blocking_discord_results_failed(results))

    def test_structure_timeout_remains_blocking(self) -> None:
        results = [
            "Discord slash commands synchronized",
            "comprehensive Discord structure sync failed: ConnectTimeout",
        ]
        self.assertFalse(resilient.command_registration_failed(results))
        self.assertTrue(resilient.blocking_discord_results_failed(results))

    def test_command_only_retry_preserves_structure_receipt(self) -> None:
        results = [
            "command registration failed: ConnectTimeout",
            "Strictly ordered Learning Center, lesson cards, guides, and permissions synchronized",
        ]
        preserved = resilient.structure_results(results)
        self.assertEqual(
            preserved,
            [
                "Strictly ordered Learning Center, lesson cards, guides, and permissions synchronized"
            ],
        )

    def test_successful_command_entry_is_not_preserved_as_structure(self) -> None:
        self.assertEqual(
            resilient.structure_results(
                [
                    "Discord slash commands synchronized",
                    "Discord channels, guides, and permissions synchronized",
                ]
            ),
            ["Discord channels, guides, and permissions synchronized"],
        )

    def test_engine_acceptance_reads_retrying_and_passed_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acceptance.json"
            with patch.object(resilient, "ENGINE_ACCEPTANCE_PATH", path):
                self.assertEqual(resilient.engine_acceptance()[0], "STARTING")
                path.write_text(
                    json.dumps({"status": "RETRYING", "error": "Discord timeout"}),
                    encoding="utf-8",
                )
                status, detail = resilient.engine_acceptance()
                self.assertEqual(status, "RETRYING")
                self.assertIn("Discord timeout", detail)
                path.write_text(
                    json.dumps({"status": "PASSED", "contract": "verified"}),
                    encoding="utf-8",
                )
                self.assertEqual(resilient.engine_acceptance()[0], "PASSED")

    def test_services_ready_requires_engine_acceptance_pass(self) -> None:
        state = {
            "last_update_status": "DEPLOYED",
            "last_discord_sync_status": "OK",
            "deployed_sha": "abc123def456",
        }
        write = Mock()
        with (
            patch.object(resilient.base.supervisor, "state_payload", return_value=state),
            patch.object(resilient.base.supervisor, "write_state", write),
            patch.object(
                resilient,
                "engine_acceptance",
                return_value=("RETRYING", "Discord timeout"),
            ),
        ):
            self.assertFalse(resilient.deployment_sync_ready("abc123def456"))
        self.assertEqual(
            write.call_args.kwargs["information_engine_acceptance_status"],
            "RETRYING",
        )

        with (
            patch.object(resilient.base.supervisor, "state_payload", return_value=state),
            patch.object(resilient.base.supervisor, "write_state"),
            patch.object(
                resilient,
                "engine_acceptance",
                return_value=("PASSED", "verified"),
            ),
        ):
            self.assertTrue(resilient.deployment_sync_ready("abc123def456"))

    def test_online_engine_posts_retrying_state_instead_of_unhealthy(self) -> None:
        post = Mock()
        original_readiness = resilient.base.deployment_sync_ready
        with (
            patch.object(resilient.base, "ensure_services_with_readiness"),
            patch.object(
                resilient.base.supervisor,
                "LAST_HEALTH",
                {"information-engine": True},
            ),
            patch.object(resilient.base.supervisor, "write_state"),
            patch.object(resilient.base.supervisor, "discord_post", post),
            patch.object(
                resilient,
                "engine_acceptance",
                return_value=("RETRYING", "required card timed out"),
            ),
            patch.object(resilient, "_LAST_ENGINE_ACCEPTANCE_STATUS", ""),
        ):
            resilient.ensure_services_with_acceptance()
        post.assert_called_once()
        self.assertIn("services running", post.call_args.args[0])
        self.assertIn("RETRYING", post.call_args.args[0])
        self.assertIs(resilient.base.deployment_sync_ready, original_readiness)

    def test_patch_is_installed_into_supervisor_module(self) -> None:
        self.assertIs(
            resilient.base.discord_results_failed,
            resilient.blocking_discord_results_failed,
        )
        self.assertIs(
            resilient.base.retry_pending_discord_configuration,
            resilient.retry_pending_discord_configuration,
        )
        self.assertIs(
            resilient.base.supervisor.ensure_services,
            resilient.ensure_services_with_acceptance,
        )


if __name__ == "__main__":
    unittest.main()
