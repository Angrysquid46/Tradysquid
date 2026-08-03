$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Python=Join-Path $Root '.venv\Scripts\python.exe'
$Before=(git -C $Root rev-parse HEAD)
$Backup=Join-Path $Root ("backups\pre-update-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.db')
if (Test-Path (Join-Path $Root 'data\tradysquid.db')) { Copy-Item (Join-Path $Root 'data\tradysquid.db') $Backup }
try {
  git -C $Root fetch origin
  git -C $Root merge --ff-only origin/main
  & $Python -m pip install -r (Join-Path $Root 'requirements-dev.txt')
  & $Python -m pytest
  if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
  & (Join-Path $PSScriptRoot 'stop.ps1')
  & (Join-Path $PSScriptRoot 'start.ps1')
  @{status='PASS';previous=$Before;current=(git -C $Root rev-parse HEAD)} | ConvertTo-Json | Set-Content (Join-Path $Root 'UPDATE-RESULT.json')
  'PASS' | Set-Content (Join-Path $Root 'UPDATE-RESULT.txt')
  Write-Host 'PASS'
} catch {
  git -C $Root reset --hard $Before
  & (Join-Path $PSScriptRoot 'start.ps1')
  @{status='ROLLED BACK';previous=$Before;error=$_.Exception.Message} | ConvertTo-Json | Set-Content (Join-Path $Root 'UPDATE-RESULT.json')
  'ROLLED BACK' | Set-Content (Join-Path $Root 'UPDATE-RESULT.txt')
  Write-Host 'ROLLED BACK'; exit 1
}
