from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts" / "setup.ps1"
INSTALLER = ROOT / "scripts" / "install_clean_rebuild.ps1"
STRUCTURE = ROOT / "tradysquid" / "discord" / "structure.py"


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


def test_structure_reconciler_checks_capacity_and_whole_guild() -> None:
    source = STRUCTURE.read_text(encoding="utf-8")
    assert "MAX_CHANNELS_PER_CATEGORY = 50" in source
    assert "_all_text_channels" in source
    assert "_overflow_category" in source
    assert "channel-reused-other-category" in source
    assert "discord.channel." in source


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
