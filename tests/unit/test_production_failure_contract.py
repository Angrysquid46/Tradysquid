from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts" / "setup.ps1"
INSTALLER = ROOT / "scripts" / "install_clean_rebuild.ps1"
INSTALLER_BODY = ROOT / "scripts" / "install_clean_rebuild_body.ps1"
AUTO_INSTALLER = ROOT / "scripts" / "auto_install_clean_rebuild.ps1"
STRUCTURE = ROOT / "tradysquid" / "discord" / "structure.py"
LAYOUT = ROOT / "tradysquid" / "discord" / "layout.py"
SCHEMA = ROOT / "config" / "discord-schema.json"
BOT = ROOT / "tradysquid" / "discord" / "bot.py"


def test_setup_does_not_serialize_generic_list_directly() -> None:
    source = SETUP.read_text(encoding="utf-8")
    assert "stages = @($stageRecords)" not in source
    assert "Convert-StageRecordsToPlainArray" in source
    assert "stages = $StageArray" in source
    assert "receipt_error" in source


def test_installer_uses_safe_optional_receipt_properties() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    assert "function Get-OptionalProperty" in source
    assert "$SetupReceipt.log" not in source
    assert "Setup log: not available" in source
    for property_name in ("failed_stage", "error", "status", "log"):
        assert f"Get-OptionalProperty $SetupReceipt '{property_name}'" in source


def test_structure_reconciler_restores_original_layout_without_overflow() -> None:
    structure = STRUCTURE.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    assert "MAX_CHANNELS_PER_CATEGORY = 50" in structure
    assert "_all_channels" in structure
    assert "channel-restored-to-original-category" in structure
    assert "discord.channel." in structure
    assert "_overflow_category" not in structure
    assert "create_category" not in structure

    assert '"SCANNING"' in layout
    assert '"PAPER TRADING"' in layout
    assert '"LEARNING CENTER 2"' in layout
    assert '"STRATEGY CONTROL"' in layout
    assert "INVENTED_CATEGORIES" in layout
    assert "STRATEGY CONTROL" not in {
        "SCANNING",
        "PAPER TRADING",
        "LEARNING CENTER 2",
    }

    assert '"allow_create_missing": false' in schema
    assert '"allow_move_existing": false' in schema
    assert '"STRATEGY CONTROL"' in schema
    assert '"LEARNING CENTER 2"' not in schema


def test_guild_slash_commands_are_copied_synced_and_verified() -> None:
    bot = BOT.read_text(encoding="utf-8")
    assert "self.tree.copy_global_to(guild=guild_object)" in bot
    assert "self.tree.sync(guild=guild_object)" in bot
    assert "self.tree.fetch_commands(guild=guild_object)" in bot
    assert "synchronization returned zero commands" in bot


def test_optional_extended_cleanup_cannot_downgrade_core_readiness() -> None:
    bot = BOT.read_text(encoding="utf-8")
    assert '"extended_status": extended_status' in bot
    assert '"status": current.get("status", "PASS")' in bot


def test_branch_switch_archives_then_removes_only_untracked_nonignored_conflicts() -> None:
    installer = INSTALLER_BODY.read_text(encoding="utf-8")
    assert "New-ExternalBackup -Root $Repository" in installer
    assert "ls-files --others --exclude-standard" in installer
    assert "untracked-paths-before-clean.txt" in installer
    assert "git -C $Repository clean -fd" in installer
    assert "git -C $Repository clean -fdx" not in installer
    assert installer.index("New-ExternalBackup -Root $Repository") < installer.index(
        "git -C $Repository clean -fd"
    )


def test_outer_handoff_cleans_conflicts_before_its_branch_switch() -> None:
    installer = AUTO_INSTALLER.read_text(encoding="utf-8")
    clean = "git -C $Repository clean -fd"
    switch = "$FailedStage = 'clean-branch-switch'"
    assert "ls-files --others --exclude-standard" in installer
    assert "pre-switch-installation" in installer
    assert "untracked-paths-before-clean.txt" in installer
    assert clean in installer
    assert "git -C $Repository clean -fdx" not in installer
    assert installer.index(clean) < installer.index(switch)


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows PowerShell only")
def test_powershell_plain_stage_array_serializes_zero_one_and_many(tmp_path: Path) -> None:
    script = tmp_path / "receipt-regression.ps1"
    script.write_text(
        r'''
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Convert-Plain([object[]]$InputRecords) {
    $OutputRecords = @()
    foreach ($Record in $InputRecords) {
        $OutputRecords += [pscustomobject]@{
            name = [string]$Record.name
            status = [string]$Record.status
            started_at = [string]$Record.started_at
            finished_at = [string]$Record.finished_at
            duration_seconds = [double]$Record.duration_seconds
            exit_code = [int]$Record.exit_code
            error = if ($null -eq $Record.error) { $null } else { [string]$Record.error }
        }
    }
    return $OutputRecords
}
foreach ($Count in @(0, 1, 3)) {
    $Records = New-Object System.Collections.Generic.List[object]
    for ($Index = 0; $Index -lt $Count; $Index++) {
        $Records.Add([pscustomobject]@{
            name = "stage-$Index"
            status = 'PASS'
            started_at = 'start'
            finished_at = 'finish'
            duration_seconds = 1.0
            exit_code = 0
            error = $null
        })
    }
    $Plain = @(Convert-Plain -InputRecords $Records)
    $Json = [ordered]@{ stages = $Plain } | ConvertTo-Json -Depth 5
    $Parsed = $Json | ConvertFrom-Json
    if (@($Parsed.stages).Count -ne $Count) {
        throw "Expected $Count records but received $(@($Parsed.stages).Count)"
    }
}
Write-Host 'PASS'
''',
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows PowerShell only")
def test_optional_property_reader_handles_missing_log_under_strict_mode(
    tmp_path: Path,
) -> None:
    script = tmp_path / "optional-property-regression.ps1"
    script.write_text(
        r'''
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Get-OptionalProperty {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $Default }
    if ($null -eq $Property.Value) { return $Default }
    return $Property.Value
}
$ReceiptWithoutLog = [pscustomobject]@{ status = 'FAILED'; error = 'original error' }
$ReceiptWithNullLog = [pscustomobject]@{ status = 'FAILED'; error = 'original error'; log = $null }
if ((Get-OptionalProperty $ReceiptWithoutLog 'log' 'not available') -ne 'not available') { throw 'missing failed' }
if ((Get-OptionalProperty $ReceiptWithNullLog 'log' 'not available') -ne 'not available') { throw 'null failed' }
if ((Get-OptionalProperty $ReceiptWithoutLog 'error' 'none') -ne 'original error') { throw 'error changed' }
Write-Host 'PASS'
''',
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout
