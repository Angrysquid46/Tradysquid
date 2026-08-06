$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$CurrentPid = $PID
$Stopped = @()

# Stop only Python runtimes whose command line points to this repository.
# Do not terminate cmd.exe or powershell.exe here: those processes may be the
# installer itself or its parent wrapper. Killing them caused the outer
# installer to roll back while setup was still running.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProcessId -ne $CurrentPid -and
    $_.CommandLine -and
    $_.CommandLine -like "*$Root*" -and
    $_.Name -in @('python.exe', 'pythonw.exe')
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $Stopped += $_.ProcessId
  }

Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskName -like '*Tradysquid*' } |
  Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

Remove-Item (Join-Path $Root 'state\*.pid*') -Force -ErrorAction SilentlyContinue
Write-Host ('Stopped repository Python processes: ' + (($Stopped | ForEach-Object { [string]$_ }) -join ', '))
