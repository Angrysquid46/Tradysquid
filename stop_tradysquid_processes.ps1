param(
    [int]$KeepProcessId = 0
)

$patterns = @(
    'discord_command_bot(_public)?\.py',
    'local_information_engine(_public|_bootstrap)?\.py',
    'run_ngrok\.py',
    'tradysquid_supervisor\.py',
    'run_supervisor_simple\.py',
    'run_supervisor_resilient\.py',
    'run_supervisor\.py',
    'ngrok(\.exe)?\s+http\s+8080'
)

$allProcesses = @(Get-CimInstance Win32_Process)
$keepProcessIds = [System.Collections.Generic.HashSet[int]]::new()
$currentKeepId = $KeepProcessId
while ($currentKeepId -gt 0 -and $keepProcessIds.Add($currentKeepId)) {
    $currentKeepProcess = $allProcesses |
        Where-Object { $_.ProcessId -eq $currentKeepId } |
        Select-Object -First 1
    if (-not $currentKeepProcess) {
        break
    }
    $currentKeepId = [int]$currentKeepProcess.ParentProcessId
}

$allProcesses |
    Where-Object {
        $process = $_
        -not $keepProcessIds.Contains([int]$process.ProcessId) -and
        $process.CommandLine -and
        ($patterns | Where-Object { $process.CommandLine -match $_ }).Count -gt 0
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
