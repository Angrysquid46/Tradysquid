from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics
import discord_command_diagnostics as command_diagnostics


class FakeResponse:
    def __init__(self, payload, *, ok=True):
        self._payload = payload
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("HTTP failure")

    def json(self):
        return self._payload


class DiscordCommandDiagnosticsTests(unittest.TestCase):
    def test_expected_registry_contains_owner_upgrade_commands_once(self) -> None:
        names = command_diagnostics.expected_command_names()
        for name in ("upgrade-add", "upgrade-list", "upgrade-ready", "upgrade-cancel"):
            self.assertEqual(names.count(name), 1)

    def test_registered_command_read_is_get_only(self) -> None:
        response = FakeResponse([{"name": "upgrade-add"}])
        with (
            patch.dict(
                command_diagnostics.os.environ,
                {
                    "DISCORD_APPLICATION_ID": "app",
                    "DISCORD_GUILD_ID": "guild",
                    "DISCORD_BOT_TOKEN": "token",
                },
                clear=False,
            ),
            patch.object(
                command_diagnostics.requests,
                "get",
                return_value=response,
            ) as get,
            patch.object(command_diagnostics.requests, "put") as put,
            patch.object(command_diagnostics.requests, "post") as post,
            patch.object(command_diagnostics.requests, "delete") as delete,
        ):
            names = command_diagnostics.registered_command_names()
        self.assertEqual(names, ["upgrade-add"])
        get.assert_called_once()
        put.assert_not_called()
        post.assert_not_called()
        delete.assert_not_called()

    def test_exact_unique_registry_passes(self) -> None:
        expected = ["a", "b", "upgrade-add"]
        with (
            patch.object(
                command_diagnostics,
                "expected_command_names",
                return_value=expected,
            ),
            patch.object(
                command_diagnostics,
                "registered_command_names",
                return_value=list(expected),
            ),
        ):
            check = command_diagnostics.command_registration_check()
        self.assertTrue(check.passed)
        self.assertIn("missing=none", check.detail)
        self.assertIn("extra=none", check.detail)
        self.assertIn("duplicates=none", check.detail)

    def test_missing_extra_and_duplicate_commands_fail_with_exact_names(self) -> None:
        with (
            patch.object(
                command_diagnostics,
                "expected_command_names",
                return_value=["a", "b", "upgrade-add"],
            ),
            patch.object(
                command_diagnostics,
                "registered_command_names",
                return_value=["a", "a", "extra"],
            ),
        ):
            check = command_diagnostics.command_registration_check()
        self.assertFalse(check.passed)
        self.assertIn("b", check.detail)
        self.assertIn("upgrade-add", check.detail)
        self.assertIn("extra", check.detail)
        self.assertIn("duplicates=['a']", check.detail)
        self.assertFalse(check.force_upgrade)

    def test_connectivity_failure_is_warning_and_does_not_modify_commands(self) -> None:
        with patch.object(
            command_diagnostics,
            "registered_command_names",
            side_effect=RuntimeError("Discord timeout"),
        ):
            check = command_diagnostics.command_registration_check()
        self.assertFalse(check.passed)
        self.assertEqual(check.severity, "WARNING")
        self.assertIn("Discord timeout", check.detail)
        self.assertIn("read-only", check.operation)

    def test_collect_appends_one_live_command_check(self) -> None:
        base_check = diagnostics.HealthCheck(
            "base",
            True,
            "base",
            "base",
            "ok",
        )
        command_check = diagnostics.HealthCheck(
            "command",
            True,
            "commands",
            "registry",
            "ok",
        )
        with (
            patch.object(
                command_diagnostics,
                "_ORIGINAL_COLLECT",
                return_value=([base_check], {"upgrade-review": {"id": "1"}}),
            ),
            patch.object(
                command_diagnostics,
                "command_registration_check",
                return_value=command_check,
            ),
        ):
            checks, channels = command_diagnostics.collect_health_checks(object())
        self.assertEqual(checks, [base_check, command_check])
        self.assertIn("upgrade-review", channels)

    def test_install_patches_both_collect_paths_without_scheduling_writes(self) -> None:
        original_startup = startup.collect_health_checks
        original_diagnostics = diagnostics.collect_health_checks
        try:
            command_diagnostics._INSTALLED = False
            command_diagnostics.install()
            self.assertIs(
                startup.collect_health_checks,
                command_diagnostics.collect_health_checks,
            )
            self.assertIs(
                diagnostics.collect_health_checks,
                command_diagnostics.collect_health_checks,
            )
        finally:
            startup.collect_health_checks = original_startup
            diagnostics.collect_health_checks = original_diagnostics
            command_diagnostics._INSTALLED = False

    def test_source_contains_no_command_registration_mutation(self) -> None:
        source = Path(command_diagnostics.__file__).read_text(encoding="utf-8")
        self.assertNotIn("requests.put", source)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("requests.delete", source)
        self.assertNotIn("register_discord_commands.py", source)


if __name__ == "__main__":
    unittest.main()
