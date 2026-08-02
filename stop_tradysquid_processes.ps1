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
if ($healthOwner -and -not $keepProcessIds.Contains([int]$healthOwner.OwningProcess)) {
    [void]$targets.Add([int]$healthOwner.OwningProcess)
}

foreach ($id in $targets) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
