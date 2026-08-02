from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import single_owner_runtime


ROOT = Path(__file__).resolve().parent


class SingleOwnerRuntimeTests(unittest.TestCase):
    def test_startup_cleanup_preserves_current_process_and_ancestors(self) -> None:
        script = single_owner_runtime._powershell_script(123)
        self.assertIn("$current = 123", script)
        self.assertIn("ParentProcessId", script)
        self.assertIn("$keep.Contains", script)

    def test_startup_cleanup_removes_stale_supervisors_launchers_and_services(self) -> None:
        result = single_owner_runtime.validate()
        self.assertTrue(result["stale_supervisors_removed"])
        self.assertTrue(result["stale_launchers_removed"])
        self.assertTrue(result["managed_services_reowned"])

    def test_install_replaces_only_supervisor_ownership_function(self) -> None:
        target = SimpleNamespace(take_process_ownership=lambda: None)
        original = single_owner_runtime._INSTALLED
        try:
            single_owner_runtime._INSTALLED = False
            single_owner_runtime.install(target)
            self.assertIs(target.take_process_ownership, single_owner_runtime.take_single_owner)
        finally:
            single_owner_runtime._INSTALLED = original

    def test_watchdog_preserves_entire_port_owner_tree_and_removes_only_foreign_trees(self) -> None:
        text = (ROOT / "ENSURE-SUPERVISOR.ps1").read_text(encoding="utf-8")
        self.assertIn("function Stop-ExtraOwnership", text)
        self.assertIn("OwnerTreeIds", text)
        self.assertIn("ForeignSupervisorIds", text)
        self.assertIn("Get-AncestorIds", text)
        self.assertIn("owner tree", text)
        self.assertIn("AddSeconds(120)", text)
        self.assertNotIn("ProcessId -eq $Ownership.PortOwner", text)

    def test_loader_installs_guard_only_for_simple_supervisor(self) -> None:
        text = (ROOT / "run_with_env.py").read_text(encoding="utf-8")
        self.assertIn("include_supervisor_guard", text)
        self.assertIn('target.name.casefold() == "run_supervisor_simple.py"', text)
        self.assertIn("single_owner_runtime.install()", text)


if __name__ == "__main__":
    unittest.main()
