$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) { throw 'Virtual environment is missing. Run SETUP-AND-START.cmd.' }
$PidFile = Join-Path $Root 'state\tradysquid.pid.json'
if (Test-Path $PidFile) {
  try { $pidValue = (Get-Content $PidFile -Raw | ConvertFrom-Json).pid; if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) { throw "Tradysquid is already running with PID $pidValue" } } catch { if ($_.Exception.Message -like 'Tradysquid is already*') { throw }; Remove-Item $PidFile -Force }
}
$Log = Join-Path $Root 'logs\launcher.log'
$p = Start-Process -FilePath $Python -ArgumentList '-m','tradysquid.app' -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $Log -RedirectStandardError (Join-Path $Root 'logs\launcher-errors.log')
Start-Sleep -Seconds 3
if ($p.HasExited) { throw 'Tradysquid exited during startup. Check logs.' }
Write-Host 'PASS'
