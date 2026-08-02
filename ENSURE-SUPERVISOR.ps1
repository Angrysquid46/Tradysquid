param(
    [switch]$CheckOnly,
    [int]$MaxHeartbeatAgeSeconds = 180
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$StateDir = Join-Path $Root 'state'
$StatePath = Join-Path $StateDir 'supervisor-state.json'
$LogPath = Join-Path $StateDir 'supervisor-watchdog.log'
$SimpleScript = Join-Path $Root 'run_supervisor_simple.py'
$Launcher = Join-Path $Root 'start_supervisor_hidden.vbs'
$LauncherCommand = Join-Path $Root 'START-SUPERVISOR.cmd'
$HealthPort = 8876

if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogPath -Value "$stamp | $Message" -Encoding UTF8
}

function Get-SimpleSupervisorProcesses {
    $escaped = [regex]::Escape($SimpleScript)
    @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match '^python(w)?\.exe$' -and
                $_.CommandLine -and
                $_.CommandLine -match $escaped
            }
    )
}

function Get-HealthPortOwner {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $HealthPort -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return 0
}

function Get-LauncherProcesses {
    $escaped = [regex]::Escape($LauncherCommand)
    @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -eq 'cmd.exe' -and
                $_.CommandLine -and
                $_.CommandLine -match $escaped
            }
    )
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

function Get-OwnershipStatus {
    $processes = @(Get-SimpleSupervisorProcesses)
    $owner = Get-HealthPortOwner
    $ids = @($processes | ForEach-Object { [int]$_.ProcessId })
    $singleOwner = ($ids.Count -eq 1 -and $owner -eq $ids[0])
    return [pscustomobject]@{
        Processes = $processes
        ProcessIds = $ids
        PortOwner = $owner
        SingleOwner = $singleOwner
    }
}

function Stop-BrokenOwnership {
    param($Ownership)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($id in $Ownership.ProcessIds) { [void]$ids.Add([int]$id) }
    if ($Ownership.PortOwner -gt 0) { [void]$ids.Add([int]$Ownership.PortOwner) }
    foreach ($id in $ids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    foreach ($launcherProcess in @(Get-LauncherProcesses)) {
        Stop-Process -Id $launcherProcess.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($ids.Count -gt 0) { Start-Sleep -Seconds 2 }
}

$stopFlag = Join-Path $StateDir 'supervisor-stop.flag'
if (Test-Path $stopFlag) {
    if (-not $CheckOnly) {
        Write-WatchdogLog 'Stop flag is present; watchdog did not relaunch the supervisor.'
    }
    exit 0
}

$ownership = Get-OwnershipStatus
$heartbeat = Get-HeartbeatStatus
if ($ownership.SingleOwner -and $heartbeat.Fresh) {
    if (-not $CheckOnly) {
        Write-WatchdogLog "Supervisor verified; PID $($ownership.ProcessIds[0]); port $HealthPort owner matches; $($heartbeat.Detail)."
    }
    exit 0
}

if ($CheckOnly) { exit 1 }

Write-WatchdogLog (
    "Supervisor ownership unhealthy; processes=$($ownership.ProcessIds -join ','); " +
    "portOwner=$($ownership.PortOwner); $($heartbeat.Detail). Rebuilding one hidden owner."
)
Stop-BrokenOwnership -Ownership $ownership

if (-not (Test-Path $Launcher)) {
    Write-WatchdogLog "Launcher missing: $Launcher"
    exit 2
}

Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"') -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $ownership = Get-OwnershipStatus
    $heartbeat = Get-HeartbeatStatus
    if ($ownership.SingleOwner -and $heartbeat.Fresh) {
        Write-WatchdogLog "Supervisor recovery verified; PID $($ownership.ProcessIds[0]); port $HealthPort owner matches; $($heartbeat.Detail)."
        exit 0
    }
}

$ownership = Get-OwnershipStatus
Write-WatchdogLog (
    "Supervisor recovery failed; processes=$($ownership.ProcessIds -join ','); " +
    "portOwner=$($ownership.PortOwner)."
)
exit 3
