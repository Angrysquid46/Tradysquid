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
        self.assertIn("eb1b04b2d6deeee42df8d939acb328e26d693f7f", text)
        self.assertIn("ba75aae5f34f3889404bfe0c7c0b96663a92a657", text)
        self.assertIn("auto_install_clean_rebuild.ps1", text)
        self.assertIn("Start-Process -FilePath 'powershell.exe'", text)
        self.assertIn("-NoNewWindow", text)
        self.assertIn("-Wait", text)
        self.assertIn("-PassThru", text)
        self.assertIn("TRADYSQUID INSTALLATION PASSED", text)
        self.assertIn("TRADYSQUID INSTALLATION DID NOT PASS", text)
        self.assertIn("Read-Host", text)
        self.assertNotIn("DETACHED_PROCESS", text)
        self.assertNotIn("CREATE_NO_WINDOW", text)
        self.assertNotIn("clean_rebuild_auto_handoff.launch_if_needed", text)

    def test_stale_worktree_path_cannot_abort_foreground_installer(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("$UniqueSuffix = [guid]::NewGuid()", text)
        self.assertIn("$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'", text)
        self.assertIn("Remove-TemporaryWorktreeBestEffort", text)
        self.assertIn("Cleanup must never replace the real installation result", text)
        self.assertIn("$ErrorActionPreference = 'Continue'", text)
        self.assertNotIn(
            "& git -C $Repository worktree remove --force $Worktree 2>$null",
            text,
        )
        self.assertNotIn(
            "'Tradysquid-clean-handoff-' + $ExpectedCleanCommit.Substring(0, 12)",
            text,
        )

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
