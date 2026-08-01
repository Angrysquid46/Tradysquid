param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Tradysquids Supervisor Watchdog'
$Watchdog = Join-Path $PSScriptRoot 'ENSURE-SUPERVISOR.ps1'

if ($Remove) {
    & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
    exit 0
}

if (-not (Test-Path $Watchdog)) {
    throw "Watchdog script not found: $Watchdog"
}

$taskCommand = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Watchdog + '"'
& schtasks.exe /Create /TN $TaskName /TR $taskCommand /SC MINUTE /MO 5 /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not create scheduled task '$TaskName' (exit $LASTEXITCODE)."
}

# Run once now. The scheduled task remains the independent recovery layer.
& powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $Watchdog
exit $LASTEXITCODE
