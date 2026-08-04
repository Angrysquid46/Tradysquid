from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "RUN-AUDITED-TRADYSQUID-INSTALL.ps1"


class VisibleManualInstallerTests(unittest.TestCase):
    def test_foreground_installer_targets_exact_audited_build(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("f2ae73954ff2b93d4a2827abf48aa286e9e9d43a", text)
        self.assertIn("ba75aae5f34f3889404bfe0c7c0b96663a92a657", text)
        self.assertIn("auto_install_clean_rebuild.ps1", text)
        self.assertIn("& powershell.exe @InstallerArguments", text)
        self.assertIn("TRADYSQUID INSTALLATION PASSED", text)
        self.assertIn("TRADYSQUID INSTALLATION DID NOT PASS", text)
        self.assertIn("Read-Host", text)
        self.assertNotIn("DETACHED_PROCESS", text)
        self.assertNotIn("CREATE_NO_WINDOW", text)
        self.assertNotIn("clean_rebuild_auto_handoff.launch_if_needed", text)

    @unittest.skipUnless(os.name == "nt", "PowerShell parse gate requires Windows")
    def test_foreground_installer_parses_in_windows_powershell(self) -> None:
        escaped = str(INSTALLER).replace("'", "''")
        command = (
            "$tokens=$null; $errors=$null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{escaped}', "
            "[ref]$tokens, [ref]$errors); "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
