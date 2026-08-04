from __future__ import annotations

import unittest
from pathlib import Path

import deployment_validation_manifest as manifest


ROOT = Path(__file__).resolve().parent


class DeploymentValidationManifestTests(unittest.TestCase):
    def test_one_click_cmd_avoids_quoted_trailing_backslash_path(self):
        launcher = Path(__file__).with_name("ONE-CLICK-TRADYSQUID.cmd").read_text(encoding="utf-8")
        self.assertIn('-RepositoryPath "%~dp0."', launcher)
        self.assertNotIn('-RepositoryPath "%~dp0"', launcher)

    def test_manifest_is_unique_and_complete(self) -> None:
        payload = manifest.validate_manifest()
        self.assertEqual(payload["compile_modules"], len(manifest.COMPILE_MODULES))
        self.assertEqual(payload["focused_tests"], len(manifest.FOCUSED_TEST_MODULES))
        self.assertEqual(len(manifest.COMPILE_MODULES), len(set(manifest.COMPILE_MODULES)))
        self.assertEqual(
            len(manifest.FOCUSED_TEST_MODULES),
            len(set(manifest.FOCUSED_TEST_MODULES)),
        )

    def test_every_manifest_path_exists(self) -> None:
        missing = [
            relative
            for relative in (*manifest.COMPILE_MODULES, *manifest.FOCUSED_TEST_MODULES)
            if not (ROOT / relative).is_file()
        ]
        self.assertEqual(missing, [])

    def test_active_runtime_and_every_diagnostic_layer_are_compiled(self) -> None:
        required = {
            "run_supervisor_simple.py",
            "simple_upgrade_runtime.py",
            "applied_upgrade_status_runtime.py",
            "diagnostic_upgrade_system.py",
            "diagnostic_runtime_integration.py",
            "diagnostic_startup_runtime.py",
            "diagnostic_nonblocking_runtime.py",
            "discord_command_diagnostics.py",
            "supervisor_diagnostic_runtime.py",
            "scheduler_diagnostic_runtime.py",
            "github_upgrade_bridge_runtime.py",
            "shared_upgrade_lifecycle.py",
            "upgrade_lifecycle_dashboard.py",
            "market_calendar_runtime.py",
        }
        self.assertEqual(required - set(manifest.COMPILE_MODULES), set())

    def test_every_new_runtime_layer_has_a_laptop_test(self) -> None:
        required = {
            "test_simple_upgrade_flow.py",
            "test_applied_upgrade_status_runtime.py",
            "test_diagnostic_upgrade_system.py",
            "test_diagnostic_startup_runtime.py",
            "test_diagnostic_nonblocking_runtime.py",
            "test_discord_command_diagnostics.py",
            "test_supervisor_diagnostic_runtime.py",
            "test_scheduler_diagnostic_runtime.py",
            "test_github_upgrade_bridge_runtime.py",
            "test_upgrade_lifecycle_dashboard.py",
            "test_market_calendar_runtime.py",
            "test_deployment_validation_manifest.py",
        }
        self.assertEqual(required - set(manifest.FOCUSED_TEST_MODULES), set())

    def test_updater_uses_manifest_instead_of_duplicate_lists(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        self.assertIn("deployment_validation_manifest as validation_manifest", text)
        self.assertIn("validation_manifest.COMPILE_MODULES", text)
        self.assertIn("validation_manifest.FOCUSED_TEST_MODULES", text)
        self.assertNotIn("compile_files = [", text)
        self.assertNotIn("tests = [", text)


if __name__ == "__main__":
    unittest.main()
