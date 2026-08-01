param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$StateDir = Join-Path $Root 'state'
$LogPath = Join-Path $StateDir 'supervisor-watchdog.log'
$SupervisorScript = Join-Path $Root 'run_supervisor.py'
$Launcher = Join-Path $Root 'start_supervisor_hidden.vbs'

if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogPath -Value "$stamp | $Message" -Encoding UTF8
}

function Get-TradysquidsSupervisorProcess {
    $escapedScript = [regex]::Escape($SupervisorScript)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match $escapedScript -and
            $_.Name -match '^python(w)?\.exe$'
        } |
        Select-Object -First 1
}

$running = Get-TradysquidsSupervisorProcess
if ($running) {
    if (-not $CheckOnly) {
        Write-WatchdogLog "Supervisor healthy enough for watchdog detection; PID $($running.ProcessId)."
    }
    exit 0
}

if ($CheckOnly) {
    exit 1
}

$stopFlag = Join-Path $StateDir 'supervisor-stop.flag'
if (Test-Path $stopFlag) {
    Write-WatchdogLog 'Stop flag is present; watchdog did not relaunch the supervisor.'
    exit 0
}

if (-not (Test-Path $Launcher)) {
    Write-WatchdogLog "Launcher missing: $Launcher"
    exit 2
}

Write-WatchdogLog 'Supervisor process was absent; launching it now.'
Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"') -WindowStyle Hidden
Start-Sleep -Seconds 10

$running = Get-TradysquidsSupervisorProcess
if ($running) {
    Write-WatchdogLog "Supervisor relaunched successfully; PID $($running.ProcessId)."
    exit 0
}

Write-WatchdogLog 'Supervisor relaunch was attempted but no matching process appeared.'
exit 3
