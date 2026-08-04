from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "auto_install_clean_rebuild.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_auto_handoff_preserves_complete_environment() -> None:
    text = _text()
    assert "Copy-RuntimeSnapshot" in text
    assert "Restore-RuntimeSnapshot" in text
    assert "Restore-FileExact" in text
    assert "complete_environment_preserved = $true" in text
    assert "full_environment_preserved = $true" in text
    assert "Test-MigrationSourceCredentials" in text
    assert "Install-CanonicalCredentialHandoff" not in text


def test_auto_handoff_is_noninteractive_and_exact_commit_bound() -> None:
    text = _text()
    assert "ExpectedCleanCommit" in text
    assert "refs/remotes/origin/$CleanBranch" in text
    assert "$ObservedClean -ne $ExpectedCleanCommit" in text
    assert "Verb = 'RunAs'" not in text
    assert "-Verb RunAs" not in text
    assert "Read-Host" not in text


def test_auto_handoff_stops_old_runtime_and_runs_real_setup() -> None:
    text = _text()
    assert "Stop-RepositoryPython" in text
    assert "Unregister-ScheduledTask" in text
    assert "scripts\\setup_entry.ps1" in text
    assert "$Process.WaitForExit()" in text
    assert "SETUP-RESULT.json" in text
    assert "Clean setup did not produce a current PASS receipt" in text


def test_auto_handoff_rolls_back_and_restarts_legacy_on_failure() -> None:
    text = _text()
    assert "git -C $Repository switch --force $OriginalBranch" in text
    assert "git -C $Repository reset --hard $OriginalCommit" in text
    assert "Restore-RuntimeSnapshot" in text
    assert "Start-LegacySupervisor" in text
    assert "supervisor-stop.flag" in text


def test_auto_handoff_receipt_contains_no_secret_values() -> None:
    text = _text()
    assert "secret_values_written = $false" in text
    assert "DISCORD_BOT_TOKEN=" not in text
    assert "TRADIER_ACCESS_TOKEN=" not in text


def test_generated_egg_info_cannot_block_clean_branch_switch() -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.egg-info/" in ignore_text.splitlines()

    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "tradysquid.egg-info"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode == 0, tracked.stderr
    assert tracked.stdout.strip() == ""
