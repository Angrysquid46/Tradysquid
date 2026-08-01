param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Tradysquids Supervisor Watchdog'
$Watchdog = Join-Path $PSScriptRoot 'ENSURE-SUPERVISOR.ps1'
$InstallLog = Join-Path $PSScriptRoot 'state\supervisor-watchdog-install.log'

function Write-InstallLog {
    param([string]$Message)

    try {
        $installLogDirectory = Split-Path -Parent $InstallLog
        New-Item -ItemType Directory -Path $installLogDirectory -Force | Out-Null
        Add-Content -Path $InstallLog -Value $Message
    }
    catch {
        Write-Warning "Could not write the initial watchdog result to $InstallLog`: $($_.Exception.Message)"
    }
}

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

# Run once now as a best-effort startup attempt. Task creation is the installer's
# success condition; the later recovery acceptance test proves the watchdog can
# restore the stack. Keep this result separate so a transient startup failure is
# visible without falsely reporting that task installation failed.
$attemptedAt = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'
try {
    & powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $Watchdog
    $initialRunExitCode = $LASTEXITCODE
    if ($initialRunExitCode -ne 0) {
        Write-InstallLog "$attemptedAt initial watchdog run failed (exit $initialRunExitCode); scheduled task installation succeeded."
        Write-Warning "The scheduled task was created, but the initial watchdog run failed (exit $initialRunExitCode). Recovery acceptance tests will verify automatic recovery. See $InstallLog."
    }
    else {
        Write-InstallLog "$attemptedAt initial watchdog run succeeded."
    }
}
catch {
    Write-InstallLog "$attemptedAt initial watchdog run could not start: $($_.Exception.Message); scheduled task installation succeeded."
    Write-Warning "The scheduled task was created, but the initial watchdog run could not start. Recovery acceptance tests will verify automatic recovery. See $InstallLog."
}

exit 0
