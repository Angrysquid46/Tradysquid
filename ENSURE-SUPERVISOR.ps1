param(
    [switch]$CheckOnly,
    [int]$MaxHeartbeatAgeSeconds = 180
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$StateDir = Join-Path $Root 'state'
$StatePath = Join-Path $StateDir 'supervisor-state.json'
$LogPath = Join-Path $StateDir 'supervisor-watchdog.log'
$Launcher = Join-Path $Root 'start_supervisor_hidden.vbs'
$LauncherCommand = Join-Path $Root 'START-SUPERVISOR.cmd'
$SupervisorEntrypoint = 'run_supervisor_simple.py'
$SupervisorCommandPattern = '(?i)(^|[\\/"\s])' + [regex]::Escape($SupervisorEntrypoint) + '(["\s]|$)'
$HealthPort = 8876

if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogPath -Value "$stamp | $Message" -Encoding UTF8
}

function Get-AllProcesses {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Get-TradysquidsSupervisorProcesses {
    param($AllProcesses = $null)
    $items = if ($null -eq $AllProcesses) { Get-AllProcesses } else { $AllProcesses }
    @(
        $items | Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -and
            $_.CommandLine -match $SupervisorCommandPattern
        }
    )
}

function Get-TradysquidsLauncherProcesses {
    param($AllProcesses = $null)
    $items = if ($null -eq $AllProcesses) { Get-AllProcesses } else { $AllProcesses }
    $escaped = [regex]::Escape($LauncherCommand)
    @(
        $items | Where-Object {
            $_.Name -eq 'cmd.exe' -and
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

function Get-AncestorIds {
    param([int]$ProcessId, $AllProcesses)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    $current = $ProcessId
    while ($current -gt 0 -and $ids.Add([int]$current)) {
        $item = $AllProcesses |
            Where-Object { $_.ProcessId -eq $current } |
            Select-Object -First 1
        if (-not $item) { break }
        $current = [int]$item.ParentProcessId
    }
    return ,$ids
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
    $all = Get-AllProcesses
    $processes = @(Get-TradysquidsSupervisorProcesses -AllProcesses $all)
    $ids = @($processes | ForEach-Object { [int]$_.ProcessId })
    $portOwner = Get-HealthPortOwner
    $ownerTree = [System.Collections.Generic.HashSet[int]]::new()
    if ($portOwner -gt 0 -and $ids -contains $portOwner) {
        $ownerTree = Get-AncestorIds -ProcessId $portOwner -AllProcesses $all
    }
    $foreign = @($ids | Where-Object { -not $ownerTree.Contains([int]$_) })
    return [pscustomobject]@{
        AllProcesses = $all
        Processes = $processes
        ProcessIds = $ids
        PortOwner = $portOwner
        OwnerTreeIds = @($ownerTree)
        ForeignSupervisorIds = $foreign
        Healthy = ($portOwner -gt 0 -and $ids -contains $portOwner -and $foreign.Count -eq 0)
    }
}

function Stop-ExtraOwnership {
    param($Ownership)
    if ($Ownership.PortOwner -le 0 -or -not ($Ownership.ProcessIds -contains $Ownership.PortOwner)) {
        return 0
    }
    $stopped = 0
    foreach ($process in $Ownership.Processes) {
        if ($Ownership.OwnerTreeIds -contains [int]$process.ProcessId) { continue }
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped += 1
    }
    foreach ($launcherProcess in @(Get-TradysquidsLauncherProcesses -AllProcesses $Ownership.AllProcesses)) {
        if ($Ownership.OwnerTreeIds -contains [int]$launcherProcess.ProcessId) { continue }
        Stop-Process -Id $launcherProcess.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped += 1
    }
    if ($stopped -gt 0) { Start-Sleep -Seconds 2 }
    return $stopped
}

function Stop-StaleSupervisor {
    param($Ownership)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($id in $Ownership.ProcessIds) { [void]$ids.Add([int]$id) }
    if ($Ownership.PortOwner -gt 0) { [void]$ids.Add([int]$Ownership.PortOwner) }
    foreach ($id in $ids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    foreach ($launcherProcess in @(Get-TradysquidsLauncherProcesses -AllProcesses $Ownership.AllProcesses)) {
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

if ($ownership.ForeignSupervisorIds.Count -gt 0) {
    if ($CheckOnly) { exit 1 }
    Write-WatchdogLog (
        "Removing foreign supervisor ownership while preserving owner tree $($ownership.OwnerTreeIds -join ','); " +
        "foreign PIDs=$($ownership.ForeignSupervisorIds -join ',')."
    )
    $removed = Stop-ExtraOwnership -Ownership $ownership
    $ownership = Get-OwnershipStatus
    $heartbeat = Get-HeartbeatStatus
    if ($ownership.Healthy -and $heartbeat.Fresh) {
        Write-WatchdogLog "Removed $removed foreign owner/launcher process(es); owner tree $($ownership.OwnerTreeIds -join ',') remained online; $($heartbeat.Detail)."
        exit 0
    }
}

if ($ownership.Healthy -and $heartbeat.Fresh) {
    if (-not $CheckOnly) {
        Write-WatchdogLog "Supervisor verified; owner tree=$($ownership.OwnerTreeIds -join ','); port $HealthPort owner=$($ownership.PortOwner); $($heartbeat.Detail)."
    }
    exit 0
}

if ($CheckOnly) { exit 1 }

Write-WatchdogLog (
    "Supervisor ownership unhealthy; matched=$($ownership.ProcessIds -join ','); " +
    "ownerTree=$($ownership.OwnerTreeIds -join ','); foreign=$($ownership.ForeignSupervisorIds -join ','); " +
    "portOwner=$($ownership.PortOwner); $($heartbeat.Detail). Rebuilding one hidden owner tree."
)
Stop-StaleSupervisor -Ownership $ownership

if (-not (Test-Path $Launcher)) {
    Write-WatchdogLog "Launcher missing: $Launcher"
    exit 2
}

Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"') -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $ownership = Get-OwnershipStatus
    $heartbeat = Get-HeartbeatStatus
    if ($ownership.ForeignSupervisorIds.Count -gt 0) {
        [void](Stop-ExtraOwnership -Ownership $ownership)
        $ownership = Get-OwnershipStatus
        $heartbeat = Get-HeartbeatStatus
    }
    if ($ownership.Healthy -and $heartbeat.Fresh) {
        Write-WatchdogLog "Supervisor recovery verified; owner tree=$($ownership.OwnerTreeIds -join ','); port $HealthPort owner=$($ownership.PortOwner); $($heartbeat.Detail)."
        exit 0
    }
}

$ownership = Get-OwnershipStatus
Write-WatchdogLog (
    "Supervisor recovery failed; matched=$($ownership.ProcessIds -join ','); " +
    "ownerTree=$($ownership.OwnerTreeIds -join ','); foreign=$($ownership.ForeignSupervisorIds -join ','); " +
    "portOwner=$($ownership.PortOwner)."
)
exit 3
