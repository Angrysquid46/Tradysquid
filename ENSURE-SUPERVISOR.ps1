param(
    [switch]$CheckOnly,
    [int]$MaxHeartbeatAgeSeconds = 180
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$StateDir = Join-Path $Root 'state'
$StatePath = Join-Path $StateDir 'supervisor-state.json'
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

function Get-TradysquidsSupervisorProcesses {
    $escapedScript = [regex]::Escape($SupervisorScript)
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match $escapedScript -and
            $_.Name -match '^python(w)?\.exe$'
        })
}

function Get-HeartbeatStatus {
    if (-not (Test-Path $StatePath)) {
        return [pscustomobject]@{ Fresh = $false; AgeSeconds = $null; Detail = 'state file missing' }
    }
    try {
        $state = Get-Content -Raw -Path $StatePath | ConvertFrom-Json
        $value = [string]$state.supervisor_heartbeat_at
        if ([string]::IsNullOrWhiteSpace($value)) {
            return [pscustomobject]@{ Fresh = $false; AgeSeconds = $null; Detail = 'heartbeat missing' }
        }
        $heartbeat = [DateTimeOffset]::Parse($value)
        $age = [math]::Max(0, ([DateTimeOffset]::Now - $heartbeat).TotalSeconds)
        return [pscustomobject]@{
            Fresh = ($age -le $MaxHeartbeatAgeSeconds)
            AgeSeconds = [int]$age
            Detail = "heartbeat age $([int]$age)s"
        }
    }
    catch {
        return [pscustomobject]@{ Fresh = $false; AgeSeconds = $null; Detail = "state read failed: $($_.Exception.Message)" }
    }
}

function Stop-StaleSupervisor {
    param([array]$Processes)
    foreach ($process in $Processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

$stopFlag = Join-Path $StateDir 'supervisor-stop.flag'
if (Test-Path $stopFlag) {
    if (-not $CheckOnly) {
        Write-WatchdogLog 'Stop flag is present; watchdog did not relaunch the supervisor.'
    }
    exit 0
}

$running = Get-TradysquidsSupervisorProcesses
$heartbeat = Get-HeartbeatStatus
if ($running.Count -gt 0 -and $heartbeat.Fresh) {
    if (-not $CheckOnly) {
        $ids = ($running | ForEach-Object { $_.ProcessId }) -join ','
        Write-WatchdogLog "Supervisor verified; PID(s) $ids; $($heartbeat.Detail)."
    }
    exit 0
}

if ($CheckOnly) {
    exit 1
}

if ($running.Count -gt 0) {
    $ids = ($running | ForEach-Object { $_.ProcessId }) -join ','
    Write-WatchdogLog "Supervisor process existed but was stale ($($heartbeat.Detail)); restarting PID(s) $ids."
    Stop-StaleSupervisor -Processes $running
}
else {
    Write-WatchdogLog "Supervisor process absent ($($heartbeat.Detail)); relaunching."
}

if (-not (Test-Path $Launcher)) {
    Write-WatchdogLog "Launcher missing: $Launcher"
    exit 2
}

Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"') -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $running = Get-TradysquidsSupervisorProcesses
    $heartbeat = Get-HeartbeatStatus
    if ($running.Count -gt 0 -and $heartbeat.Fresh) {
        $ids = ($running | ForEach-Object { $_.ProcessId }) -join ','
        Write-WatchdogLog "Supervisor recovery verified; PID(s) $ids; $($heartbeat.Detail)."
        exit 0
    }
}

$running = Get-TradysquidsSupervisorProcesses
if ($running.Count -gt 0) {
    Write-WatchdogLog "Supervisor relaunched but heartbeat never became fresh within 45 seconds."
    exit 4
}

Write-WatchdogLog 'Supervisor relaunch was attempted but no matching process appeared.'
exit 3
