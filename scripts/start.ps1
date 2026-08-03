$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) { throw 'Virtual environment is missing. Run SETUP-AND-START.cmd.' }
$PidFile = Join-Path $Root 'state\tradysquid.pid.json'
$Startup = Join-Path $Root 'state\startup.json'
if (Test-Path $PidFile) {
  try {
    $pidValue = (Get-Content $PidFile -Raw | ConvertFrom-Json).pid
    if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) { throw "Tradysquid is already running with PID $pidValue" }
  } catch {
    if ($_.Exception.Message -like 'Tradysquid is already*') { throw }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
  }
}
Remove-Item $Startup -Force -ErrorAction SilentlyContinue
$Log = Join-Path $Root 'logs\launcher.log'
$p = Start-Process -FilePath $Python -ArgumentList '-m','tradysquid.app' -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $Log -RedirectStandardError (Join-Path $Root 'logs\launcher-errors.log')
for ($i=0; $i -lt 60; $i++) {
  if ($p.HasExited) { throw 'Tradysquid exited during startup. Check logs.' }
  if (Test-Path $Startup) {
    $receipt = Get-Content $Startup -Raw | ConvertFrom-Json
    if ($receipt.status -eq 'RUNNING' -and $receipt.pid -eq $p.Id -and $receipt.scheduler_running -and $receipt.strategy_count -eq 6) {
      Write-Host 'PASS'; exit 0
    }
  }
  Start-Sleep -Seconds 1
}
throw 'Tradysquid did not produce a valid startup receipt within 60 seconds.'
