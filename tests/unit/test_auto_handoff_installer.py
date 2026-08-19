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
    assert "Invoke-RobocopyMirror" in text
    assert "Process timed out after $TimeoutSeconds seconds" in text


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
    assert "$Process.WaitForExit(5000)" in text
    assert "SETUP-RESULT.json" in text
    assert "Clean setup did not produce a current PASS receipt" in text
    assert "Setup stage:" in text
    assert "application-start-and-readiness' = 15 * 60" in text
    assert "Stop-ProcessTree -ProcessId $Process.Id" in text


def test_auto_handoff_rolls_back_and_restarts_legacy_on_failure() -> None:
    text = _text()
    assert "@('switch', '--force', $OriginalBranch)" in text
    assert "@('reset', '--hard', $OriginalCommit)" in text
    assert "Restore-RuntimeSnapshot" in text
    assert "Restore-TradysquidScheduledTasks" in text
    assert "Start-LegacySupervisor" in text
    assert "supervisor-stop.flag" in text


def test_failure_is_visible_before_rollback_work_begins() -> None:
    text = _text()
    failure_banner = text.index("SETUP FAILED AT:")
    preliminary_receipt = text.index("Write-AutoResult -CurrentStatus $Status", failure_banner)
    rollback_start = text.index("Starting bounded rollback", preliminary_receipt)
    branch_restore = text.index("Returning checkout to", rollback_start)
    assert failure_banner < preliminary_receipt < rollback_start < branch_restore
    assert "ROLLBACK IN PROGRESS" in text
    assert "Failure receipt written" in text


def test_rollback_steps_are_bounded_and_visible() -> None:
    text = _text()
    assert "Invoke-BoundedProcess" in text
    assert "WaitForExit($TimeoutSeconds * 1000)" in text
    assert "Restoring runtime directory:" in text
    assert "Restoring scheduled task:" in text
    assert "Stopping the partial clean runtime before rollback" in text
    assert "Final installer status:" in text
    assert "Restarting legacy supervisor after final receipt" in text
    assert "Stop-RepositoryPython -Root $Root" in text


def test_snapshot_happens_after_runtime_stop_and_omits_sqlite_sidecars() -> None:
    text = _text()
    stop = text.index("Stopping legacy runtime and scheduled tasks before snapshot")
    snapshot = text.index("Creating external backup:", stop)
    assert stop < snapshot
    assert "'*.db-shm', '*.db-wal', '*.db-journal'" in text


def test_final_receipt_precedes_optional_legacy_restart() -> None:
    text = _text()
    rollback_status = text.index("$Status = if ($RollbackFailures.Count -eq 0)")
    final_receipt = text.index("Write-AutoResult -CurrentStatus $Status", rollback_status)
    legacy_restart = text.index("Start-LegacySupervisor -Root $Repository", final_receipt)
    assert rollback_status < final_receipt < legacy_restart


def test_auto_handoff_receipt_contains_no_secret_values() -> None:
    text = _text()
    assert "secret_values_written = $false" in text
    assert "DISCORD_BOT_TOKEN=" not in text
    assert "TRADIER_ACCESS_TOKEN=" not in text


def test_generated_egg_info_cannot_block_clean_branch_switch() -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.egg-info/" in ignore_text.splitlines()

    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.egg-info"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode == 0, tracked.stderr
    assert tracked.stdout.strip() == ""
