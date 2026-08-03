$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$Log = Join-Path $Root 'logs\setup.log'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs'),(Join-Path $Root 'backups'),(Join-Path $Root 'state'),(Join-Path $Root 'data') | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
$status='FAILED'; $steps=@()
try {
  $remote = git -C $Root remote get-url origin
  if ($remote -notmatch 'Angrysquid46/Tradysquid') { throw 'Unexpected Git remote.' }
  $backup = Join-Path $Root ("backups\pre-setup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  foreach ($name in '.env','data','logs','state') { $source=Join-Path $Root $name; if (Test-Path $source) { Copy-Item $source $backup -Recurse -Force } }
  $steps += 'backup-created'
  & (Join-Path $PSScriptRoot 'clean_previous_runtime.ps1')
  $py = Get-Command py -ErrorAction SilentlyContinue
  if (!$py) { throw 'Python launcher is not installed.' }
  & py -3.12 -m venv (Join-Path $Root '.venv')
  $python=Join-Path $Root '.venv\Scripts\python.exe'
  & $python -m pip install --upgrade pip
  & $python -m pip install -r (Join-Path $Root 'requirements-dev.txt')
  & $python -m pip check
  & $python -m pytest
  if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed.' }
  & $python (Join-Path $PSScriptRoot 'verify_installation.py')
  if ($LASTEXITCODE -ne 0) { throw 'Installation verification failed.' }
  & $python (Join-Path $PSScriptRoot 'verify_live.py')
  if ($LASTEXITCODE -ne 0) { throw 'Live read-only verification failed.' }
  $taskName='Tradysquid Startup'
  $action=New-ScheduledTaskAction -Execute (Join-Path $Root 'START.cmd')
  $trigger=New-ScheduledTaskTrigger -AtLogOn
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description 'Start the single-computer Tradysquid paper-trading system' -Force | Out-Null
  & (Join-Path $PSScriptRoot 'start.ps1')
  $status='PASS'
} catch {
  $steps += $_.Exception.Message
  $status='FAILED'
} finally {
  $result=@{status=$status; observed_at=(Get-Date).ToString('o'); steps=$steps; log=$Log} | ConvertTo-Json -Depth 5
  $result | Set-Content $ResultJson -Encoding UTF8
  $status | Set-Content $ResultText -Encoding UTF8
  Stop-Transcript | Out-Null
  Write-Host $status
}
if ($status -ne 'PASS') { exit 1 }
