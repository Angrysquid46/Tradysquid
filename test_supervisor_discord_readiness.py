from __future__ import annotations

import unittest

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
            resilient.base.deployment_sync_ready,
            resilient.deployment_sync_ready,
        )


if __name__ == "__main__":
    unittest.main()
