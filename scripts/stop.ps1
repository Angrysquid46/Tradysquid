$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'state\tradysquid.pid.json'
if (!(Test-Path $PidFile)) { Write-Host 'PASS'; exit 0 }
$data = Get-Content $PidFile -Raw | ConvertFrom-Json
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$($data.pid)" -ErrorAction SilentlyContinue
if ($p -and $p.CommandLine -like '*tradysquid.app*' -and $p.ExecutablePath -like "$(Join-Path $Root '.venv')*") {
  Stop-Process -Id $data.pid
  for ($i=0; $i -lt 20 -and (Get-Process -Id $data.pid -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
  if (Get-Process -Id $data.pid -ErrorAction SilentlyContinue) { Stop-Process -Id $data.pid -Force }
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host 'PASS'
