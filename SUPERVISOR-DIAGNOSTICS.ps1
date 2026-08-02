param(
    [switch]$FetchRemote
)

$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path $PSScriptRoot).Path
$StatePath = Join-Path $Root 'state\supervisor-state.json'
$EngineAcceptancePath = Join-Path $Root 'state\market-intelligence-startup.json'
$SupervisorLog = Join-Path $Root 'state\supervisor-logs\supervisor.log'
$StartupLog = Join-Path $Root 'state\supervisor-startup.log'
$WatchdogLog = Join-Path $Root 'state\supervisor-watchdog.log'
$TaskName = 'Tradysquids Supervisor Watchdog'
$SupervisorScripts = @(
    (Join-Path $Root 'run_supervisor_resilient.py'),
    (Join-Path $Root 'run_supervisor.py')
)

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "==== $Title ===="
}

function Get-GitValue([string[]]$Arguments) {
    $output = & git -C $Root @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        return "ERROR: $($output -join ' ')"
    }
    return ($output -join "`n").Trim()
}

Write-Section 'Git and updater'
if ($FetchRemote) {
    $fetchOutput = & git -C $Root fetch origin main 2>&1
    Write-Host "fetch origin/main exit: $LASTEXITCODE"
    if ($fetchOutput) { Write-Host ($fetchOutput -join "`n") }
}
$branch = Get-GitValue @('rev-parse', '--abbrev-ref', 'HEAD')
$local = Get-GitValue @('rev-parse', '--short=12', 'HEAD')
$remote = Get-GitValue @('rev-parse', '--short=12', 'origin/main')
$status = Get-GitValue @('status', '--short')
$treeState = if ([string]::IsNullOrWhiteSpace($status)) { 'clean' } else { $status }
Write-Host "branch: $branch"
Write-Host "local:  $local"
Write-Host "remote: $remote"
Write-Host "working tree: $treeState"

Write-Section 'Supervisor processes'
$escapedScripts = @($SupervisorScripts | ForEach-Object { [regex]::Escape($_) })
$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $command = [string]$_.CommandLine
        $command -and
        $_.Name -match '^python(w)?\.exe$' -and
        ($escapedScripts | Where-Object { $command -match $_ }).Count -gt 0
    } |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine)
if ($processes.Count -eq 0) {
    Write-Host 'No supervisor Python process found.'
}
else {
    $processes | Format-List | Out-String | Write-Host
}

Write-Section 'Managed service processes'
$servicePattern = 'discord_command_bot(_public)?\.py|local_information_engine(_public|_bootstrap)?\.py|run_ngrok\.py|ngrok(\.exe)?\s+http\s+8080'
$services = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match $servicePattern } |
    Select-Object ProcessId, Name, CommandLine)
if ($services.Count -eq 0) {
    Write-Host 'No managed service process found.'
}
else {
    $services | Format-Table -AutoSize | Out-String -Width 240 | Write-Host
}

Write-Section 'Listening ports'
$ports = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8080, 8765, 8876, 4040 } |
    Sort-Object LocalPort |
    Select-Object LocalAddress, LocalPort, OwningProcess)
if ($ports.Count -eq 0) {
    Write-Host 'None of the expected ports are listening.'
}
else {
    $ports | Format-Table -AutoSize | Out-String | Write-Host
}

Write-Section 'Watchdog task'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host 'Watchdog task is missing.'
}
else {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "state: $($task.State)"
    Write-Host "last run: $($info.LastRunTime)"
    Write-Host "last result: $($info.LastTaskResult)"
    Write-Host "next run: $($info.NextRunTime)"
    Write-Host "action: $($task.Actions.Execute) $($task.Actions.Arguments)"
}

Write-Section 'Supervisor state'
if (-not (Test-Path $StatePath)) {
    Write-Host 'state\supervisor-state.json is missing.'
}
else {
    try {
        $state = Get-Content -Raw -Path $StatePath | ConvertFrom-Json
        $state |
            Select-Object supervisor, supervisor_heartbeat_at, local_sha, deployed_sha,
                last_remote_sha, last_fetch_status, last_fetch_attempt_at,
                last_update_status, last_update_detail,
                last_discord_sync_status, last_command_registration_status,
                last_discord_sync_attempt_at, deployment_sync_ready,
                information_engine_acceptance_status,
                information_engine_acceptance_detail,
                information_engine_acceptance_checked_at,
                scheduler_heartbeat_healthy, service_health, updated_at |
            Format-List | Out-String -Width 240 | Write-Host
    }
    catch {
        Write-Host "State file could not be parsed: $($_.Exception.Message)"
    }
}

Write-Section 'Information engine startup acceptance'
if (-not (Test-Path $EngineAcceptancePath)) {
    Write-Host 'state\market-intelligence-startup.json is missing.'
}
else {
    try {
        Get-Content -Raw -Path $EngineAcceptancePath |
            ConvertFrom-Json |
            Select-Object status, verified_at, attempt, next_retry_seconds, error,
                required_jobs, performance_reconciliation, journal_contract, contract |
            Format-List | Out-String -Width 240 | Write-Host
    }
    catch {
        Write-Host "Acceptance file could not be parsed: $($_.Exception.Message)"
    }
}

foreach ($item in @(
    @{ Name = 'Supervisor log'; Path = $SupervisorLog; Lines = 50 },
    @{ Name = 'Startup log'; Path = $StartupLog; Lines = 30 },
    @{ Name = 'Watchdog log'; Path = $WatchdogLog; Lines = 30 }
)) {
    Write-Section $item.Name
    if (Test-Path $item.Path) {
        Get-Content -Path $item.Path -Tail $item.Lines
    }
    else {
        Write-Host "Missing: $($item.Path)"
    }
}
