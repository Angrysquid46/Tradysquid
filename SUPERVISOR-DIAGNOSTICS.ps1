$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path $PSScriptRoot).Path
$StatePath = Join-Path $Root 'state\supervisor-state.json'
$DiagnosticDb = Join-Path $Root 'state\diagnostics.db'
$TaskName = 'Tradysquids Supervisor Watchdog'
$SupervisorCommandPattern = '(?i)(^|[\\/"\s])run_supervisor_simple\.py(["\s]|$)'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "==== $Title ===="
}

function Get-GitValue([string[]]$Arguments) {
    $output = & git -C $Root @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { return "ERROR: $($output -join ' ')" }
    return ($output -join "`n").Trim()
}

Write-Section 'Git and updater'
Write-Host 'active entrypoint expected: run_supervisor_simple.py'
Write-Host 'update interval expected: 120 seconds'
Write-Host "branch: $(Get-GitValue @('rev-parse', '--abbrev-ref', 'HEAD'))"
Write-Host "local:  $(Get-GitValue @('rev-parse', '--short=12', 'HEAD'))"
Write-Host "cached origin/main: $(Get-GitValue @('rev-parse', '--short=12', 'origin/main'))"
$tracked = Get-GitValue @('status', '--porcelain', '--untracked-files=no')
Write-Host "tracked tree: $(if ([string]::IsNullOrWhiteSpace($tracked)) { 'clean' } else { $tracked })"
Write-Host 'No fetch, merge, reset, restart, repair, or Discord write was performed.'

Write-Section 'Single supervisor ownership'
$supervisors = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -and
            $_.CommandLine -match $SupervisorCommandPattern
        } |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine
)
$listener = Get-NetTCPConnection -State Listen -LocalPort 8876 -ErrorAction SilentlyContinue |
    Select-Object -First 1
Write-Host "simple supervisor count: $($supervisors.Count)"
Write-Host "port 8876 owner: $(if ($listener) { $listener.OwningProcess } else { 'none' })"
if ($supervisors.Count -gt 0) {
    $supervisors | Format-List | Out-String -Width 260 | Write-Host
}

Write-Section 'Managed services and ports'
$servicePattern = 'discord_command_bot(_public)?\.py|local_information_engine(_public|_bootstrap)?\.py|run_ngrok\.py|ngrok(\.exe)?\s+http\s+8080'
$services = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $servicePattern } |
        Select-Object ProcessId, Name, CommandLine
)
if ($services.Count -eq 0) { Write-Host 'No managed service process found.' }
else { $services | Format-Table -AutoSize | Out-String -Width 260 | Write-Host }
$ports = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8080, 8765, 8876, 4040 } |
        Sort-Object LocalPort |
        Select-Object LocalAddress, LocalPort, OwningProcess
)
if ($ports.Count -eq 0) { Write-Host 'None of the expected ports are listening.' }
else { $ports | Format-Table -AutoSize | Out-String | Write-Host }

Write-Section 'Watchdog task'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) { Write-Host 'Watchdog task is missing.' }
else {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "state: $($task.State)"
    Write-Host "last run: $($info.LastRunTime)"
    Write-Host "last result: $($info.LastTaskResult)"
    Write-Host "next run: $($info.NextRunTime)"
    Write-Host "action: $($task.Actions.Execute) $($task.Actions.Arguments)"
}

Write-Section 'Supervisor state'
if (-not (Test-Path $StatePath)) { Write-Host 'state\supervisor-state.json is missing.' }
else {
    try {
        $state = Get-Content -Raw -Path $StatePath | ConvertFrom-Json
        $state |
            Select-Object supervisor, supervisor_mode, supervisor_heartbeat_at,
                update_interval_seconds, auto_update_enabled,
                local_sha, deployed_sha, last_remote_sha, last_known_working_sha,
                last_fetch_status, last_fetch_mode, last_fetch_attempt_at, last_fetch_detail,
                last_update_status, last_update_detail, last_deployment_attempt_at,
                last_deployment_finished_at, rollback_ref, rollback_result,
                service_health, service_process_ids, service_restart_counts,
                service_last_started_at, expected_ports, updated_at |
            Format-List | Out-String -Width 260 | Write-Host
    }
    catch { Write-Host "State file could not be parsed: $($_.Exception.Message)" }
}

Write-Section 'Actionable diagnostics'
if (-not (Test-Path $DiagnosticDb)) {
    Write-Host 'state\diagnostics.db is missing; no diagnostic receipt exists yet.'
}
else {
    $python = @'
import json
import diagnostic_review_runtime as review
summary = review.diagnostics_summary()
print(json.dumps({
  "last_cycle": summary.get("last_cycle"),
  "actionable_count": len(summary.get("actionable") or []),
  "transient_count": len(summary.get("transient") or []),
  "actionable": [
    {
      "diagnostic_id": row.get("diagnostic_id"),
      "status": row.get("status"),
      "component": row.get("component"),
      "operation": row.get("operation"),
      "failures": row.get("consecutive_failures"),
      "github_batch": row.get("github_issue_number"),
      "github_request": row.get("github_request_number"),
    }
    for row in (summary.get("actionable") or [])[:20]
  ]
}, indent=2))
'@
    Push-Location $Root
    try { $python | python - }
    finally { Pop-Location }
}

foreach ($item in @(
    @{ Name = 'Supervisor log'; Path = (Join-Path $Root 'state\supervisor-logs\supervisor.log'); Lines = 40 },
    @{ Name = 'Command-bot log'; Path = (Join-Path $Root 'state\supervisor-logs\command-bot.log'); Lines = 30 },
    @{ Name = 'Information-engine log'; Path = (Join-Path $Root 'state\supervisor-logs\information-engine.log'); Lines = 40 },
    @{ Name = 'Startup log'; Path = (Join-Path $Root 'state\supervisor-startup.log'); Lines = 30 },
    @{ Name = 'Watchdog log'; Path = (Join-Path $Root 'state\supervisor-watchdog.log'); Lines = 30 }
)) {
    Write-Section $item.Name
    if (Test-Path $item.Path) { Get-Content -Path $item.Path -Tail $item.Lines }
    else { Write-Host "Missing: $($item.Path)" }
}
