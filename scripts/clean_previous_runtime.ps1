$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
# Only processes whose command line points to this repository are eligible.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Root*" -and ($_.Name -in @('python.exe','pythonw.exe','powershell.exe','cmd.exe')) } | ForEach-Object {
  if ($_.ProcessId -ne $PID) { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like '*Tradysquid*' } | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Root 'state\*.pid*') -Force -ErrorAction SilentlyContinue
