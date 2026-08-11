param(
    [int]$KeepProcessId = 0
)

$patterns = @(
    'discord_command_bot(_public)?\.py',
    'local_information_engine(_public|_bootstrap)?\.py',
    'run_ngrok\.py',
    'run_with_env\.py.*run_supervisor_simple\.py',
    'run_supervisor_simple\.py',
    'ngrok(\.exe)?\s+http\s+8080'
)

$logPath = Join-Path $PSScriptRoot 'state\port-kill-evidence.log'

function Write-KillEvidence {
    param($Process, $AllProcesses, [bool]$WasPortOwner)

    try {
        $logDir = Split-Path -Parent $logPath
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        $parent = $AllProcesses | Where-Object { $_.ProcessId -eq $Process.ParentProcessId } | Select-Object -First 1
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        $lines = @(
            "$stamp | KILLING PID $($Process.ProcessId)$(if ($WasPortOwner) { ' [was holding port 8876]' })"
            "  CommandLine: $($Process.CommandLine)"
            "  ParentProcessId: $($Process.ParentProcessId)"
            "  ParentName: $(if ($parent) { $parent.Name } else { 'unknown - parent already exited' })"
            "  ParentCommandLine: $(if ($parent) { $parent.CommandLine } else { 'unknown' })"
            ""
        )
        Add-Content -Path $logPath -Value $lines -Encoding UTF8
    }
    catch {
        # Evidence-logging must never block the actual cleanup below.
    }
}

$allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$keepProcessIds = [System.Collections.Generic.HashSet[int]]::new()
$currentKeepId = $KeepProcessId
while ($currentKeepId -gt 0 -and $keepProcessIds.Add($currentKeepId)) {
    $currentKeepProcess = $allProcesses |
        Where-Object { $_.ProcessId -eq $currentKeepId } |
        Select-Object -First 1
    if (-not $currentKeepProcess) { break }
    $currentKeepId = [int]$currentKeepProcess.ParentProcessId
}
# Real bug found live (2026-08-11): this only ever walked UP the ancestor
# chain from KeepProcessId, never down into its own children. Every time
# the supervisor called this script at its own startup, it protected
# itself and its parents but had no record of the command-bot/information-
# engine children it had already spawned (or was about to spawn) - so this
# script killed its own legitimate, currently-running services as
# "stale" matches on every single invocation, and ensure_services()
# immediately respawned them, producing a continuous kill/respawn loop
# that looked like flaky health checks but was actually self-inflicted.
# Walk DOWN from KeepProcessId too, so its whole live descendant tree
# (children, grandchildren, ...) is protected exactly like its ancestors.
if ($KeepProcessId -gt 0) {
    $frontier = [System.Collections.Generic.Queue[int]]::new()
    $frontier.Enqueue($KeepProcessId)
    while ($frontier.Count -gt 0) {
        $parentId = $frontier.Dequeue()
        foreach ($child in ($allProcesses | Where-Object { [int]$_.ParentProcessId -eq $parentId })) {
            if ($keepProcessIds.Add([int]$child.ProcessId)) {
                $frontier.Enqueue([int]$child.ProcessId)
            }
        }
    }
}

$targets = [System.Collections.Generic.HashSet[int]]::new()
foreach ($process in $allProcesses) {
    if ($keepProcessIds.Contains([int]$process.ProcessId)) { continue }
    if (-not $process.CommandLine) { continue }
    if (($patterns | Where-Object { $process.CommandLine -match $_ }).Count -gt 0) {
        [void]$targets.Add([int]$process.ProcessId)
    }
}

$healthOwner = Get-NetTCPConnection -State Listen -LocalPort 8876 -ErrorAction SilentlyContinue |
    Select-Object -First 1
$portOwnerId = 0
if ($healthOwner -and -not $keepProcessIds.Contains([int]$healthOwner.OwningProcess)) {
    $portOwnerId = [int]$healthOwner.OwningProcess
    [void]$targets.Add($portOwnerId)
}

foreach ($id in $targets) {
    $target = $allProcesses | Where-Object { $_.ProcessId -eq $id } | Select-Object -First 1
    if ($target) {
        Write-KillEvidence -Process $target -AllProcesses $allProcesses -WasPortOwner ($id -eq $portOwnerId)
    }
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
