$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$Log = Join-Path $Root 'logs\setup.log'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs'),(Join-Path $Root 'backups'),(Join-Path $Root 'state'),(Join-Path $Root 'data') | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
$status='FAILED'; $steps=New-Object System.Collections.Generic.List[string]; $backup=''

function Add-Step([string]$Message) {
  $steps.Add($Message)
  Write-Host $Message
}

function Invoke-Native([string]$Description, [scriptblock]$Command) {
  Add-Step $Description
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE."
  }
}

try {
  $remote = git -C $Root remote get-url origin
  if ($LASTEXITCODE -ne 0 -or $remote -notmatch 'Angrysquid46/Tradysquid') { throw 'Unexpected or unreadable Git remote.' }
  Add-Step 'repository-verified'

  $backup = Join-Path $Root ("backups\pre-setup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  foreach ($name in '.env','data','logs','state') {
    $source=Join-Path $Root $name
    if (Test-Path $source) { Copy-Item $source $backup -Recurse -Force }
  }
  Add-Step 'backup-created'

  $py = Get-Command py -ErrorAction SilentlyContinue
  if (!$py) { throw 'Python launcher is not installed.' }
  Invoke-Native 'credential-name-migration' {
    Push-Location $Root
    try { & py -3.12 -m tradysquid.operations.credential_migration --root $Root }
    finally { Pop-Location }
  }
  Add-Step 'credentials-preserved-with-canonical-names'

  & (Join-Path $PSScriptRoot 'clean_previous_runtime.ps1')
  Add-Step 'previous-runtime-cleaned'

  Invoke-Native 'virtual-environment-creation' { & py -3.12 -m venv (Join-Path $Root '.venv') }
  $python=Join-Path $Root '.venv\Scripts\python.exe'
  if (!(Test-Path $python)) { throw 'Virtual environment Python was not created.' }
  Invoke-Native 'pip-upgrade' { & $python -m pip install --upgrade pip }
  Invoke-Native 'dependency-installation' { & $python -m pip install -r (Join-Path $Root 'requirements-dev.txt') }
  Invoke-Native 'dependency-integrity-check' { & $python -m pip check }
  Invoke-Native 'automated-test-suite' {
    Push-Location $Root
    try { & $python -m pytest }
    finally { Pop-Location }
  }
  Invoke-Native 'installation-verification' { & $python (Join-Path $PSScriptRoot 'verify_installation.py') }
  Invoke-Native 'live-read-only-verification' { & $python (Join-Path $PSScriptRoot 'verify_live.py') }

  $taskName='Tradysquid Startup'
  $cmd = $env:ComSpec
  if ([string]::IsNullOrWhiteSpace($cmd)) { $cmd = 'cmd.exe' }
  $startCmd = Join-Path $Root 'START.cmd'
  $action=New-ScheduledTaskAction -Execute $cmd -Argument ('/d /c ""' + $startCmd + '""') -WorkingDirectory $Root
  $trigger=New-ScheduledTaskTrigger -AtLogOn
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description 'Start the single-computer Tradysquid paper-trading system' -Force | Out-Null
  Add-Step 'startup-task-registered'

  & (Join-Path $PSScriptRoot 'start.ps1')
  if ($LASTEXITCODE -ne 0) { throw "Application startup failed with exit code $LASTEXITCODE." }
  Add-Step 'application-started'
  $status='PASS'
} catch {
  $failure = $_.Exception.Message
  $steps.Add('FAILED: ' + $failure)
  Write-Host ('FAILED: ' + $failure) -ForegroundColor Red
  Write-Host ('Detailed setup log: ' + $Log) -ForegroundColor Yellow
  $status='FAILED'
} finally {
  $result=@{
    status=$status
    observed_at=(Get-Date).ToString('o')
    steps=@($steps)
    backup=$backup
    log=$Log
  } | ConvertTo-Json -Depth 5
  $result | Set-Content $ResultJson -Encoding UTF8
  ($status + [Environment]::NewLine + ($steps -join [Environment]::NewLine)) | Set-Content $ResultText -Encoding UTF8
  Stop-Transcript | Out-Null
  Write-Host $status
}
if ($status -ne 'PASS') { exit 1 }
