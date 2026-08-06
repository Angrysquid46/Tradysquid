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
