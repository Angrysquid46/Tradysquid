<#
Installs the Windows Scheduled Task that keeps ENSURE-COMPETITION.ps1
running every 5 minutes, parallel to INSTALL-SUPERVISOR-WATCHDOG.ps1 but for
the AXIOM/BLACKTIDE competition processes.
#>
param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Tradysquids Competition Watchdog'
$Watchdog = Join-Path $PSScriptRoot 'ENSURE-COMPETITION.ps1'
$InstallLog = Join-Path $PSScriptRoot 'state\competition-watchdog-install.log'

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

$attemptedAt = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'
try {
    & powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $Watchdog
    $initialRunExitCode = $LASTEXITCODE
    Write-InstallLog "$attemptedAt initial watchdog run exit $initialRunExitCode; scheduled task installation succeeded."
}
catch {
    Write-InstallLog "$attemptedAt initial watchdog run could not start: $($_.Exception.Message); scheduled task installation succeeded."
}

exit 0
