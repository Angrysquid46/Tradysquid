param(
    [int]$KeepProcessId = 0
)

$patterns = @(
    'discord_command_bot\.py',
    'local_information_engine\.py',
    'run_ngrok\.py',
    'tradysquid_supervisor\.py',
    'ngrok(\.exe)?\s+http\s+8080'
)

Get-CimInstance Win32_Process |
    Where-Object {
        $process = $_
        $process.ProcessId -ne $KeepProcessId -and
        $process.CommandLine -and
        ($patterns | Where-Object { $process.CommandLine -match $_ }).Count -gt 0
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
