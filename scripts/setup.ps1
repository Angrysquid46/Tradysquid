$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$Log = Join-Path $Root 'logs\setup.log'
$VenvPath = Join-Path $Root '.venv-tradysquid'
$Python = Join-Path $VenvPath 'Scripts\python.exe'
$State = Join-Path $Root 'state'

New-Item -ItemType Directory -Force -Path `
  (Join-Path $Root 'logs'),` 
  (Join-Path $Root 'backups'),` 
  $State,` 
  (Join-Path $Root 'data') | Out-Null

Start-Transcript -Path $Log -Append | Out-Null
$status = 'FAILED'
$failure = $null
$failedStage = $null
$currentStage = $null
$backup = ''
$projectInstallation = 'NOT STARTED'
$packageImport = 'NOT STARTED'
$packagePath = $null
$stageRecords = New-Object System.Collections.Generic.List[object]

function Invoke-SetupStage {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][scriptblock]$Action
  )

  $script:currentStage = $Name
  $started = Get-Date
  Write-Host "START: $Name"
  try {
    $global:LASTEXITCODE = 0
    & $Action
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
      throw "$Name returned exit code $exitCode."
    }
    $finished = Get-Date
    $script:stageRecords.Add([pscustomobject]@{
      name = $Name
      status = 'PASS'
      started_at = $started.ToString('o')
      finished_at = $finished.ToString('o')
      duration_seconds = [Math]::Round(($finished - $started).TotalSeconds, 3)
      exit_code = if ($null -eq $exitCode) { 0 } else { $exitCode }
      error = $null
    })
    Write-Host "PASS: $Name"
  } catch {
    $finished = Get-Date
    $message = $_.Exception.Message
    $script:stageRecords.Add([pscustomobject]@{
      name = $Name
      status = 'FAILED'
      started_at = $started.ToString('o')
      finished_at = $finished.ToString('o')
      duration_seconds = [Math]::Round(($finished - $started).TotalSeconds, 3)
      exit_code = if ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
      error = $message
    })
    Write-Host "FAILED: $Name`: $message" -ForegroundColor Red
    throw
  }
}

function Remove-IncompleteVenv {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (!(Test-Path -LiteralPath $Path)) { return }
  for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
      Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
      return
    } catch {
      if ($attempt -eq 5) { throw }
      Start-Sleep -Seconds 2
    }
  }
}

try {
  Invoke-SetupStage -Name 'repository-verification' -Action {
    $remote = & git -C $Root remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch 'Angrysquid46/Tradysquid') {
      throw 'Unexpected or unreadable Git remote.'
    }
  }

  Invoke-SetupStage -Name 'backup-created' -Action {
    $script:backup = Join-Path $Root ("backups\pre-setup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $script:backup | Out-Null
    foreach ($name in '.env','data','logs','state') {
      $source = Join-Path $Root $name
      if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $script:backup -Recurse -Force
      }
    }
  }

  Invoke-SetupStage -Name 'canonical-credential-migration' -Action {
    Push-Location $Root
    try {
      & py -3.12 -m tradysquid.operations.credential_migration --root $Root
      if ($LASTEXITCODE -ne 0) { throw 'Credential migration failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'canonical-credential-validation' -Action {
    Push-Location $Root
    try {
      & py -3.12 -m tradysquid.operations.install_preflight `
        --env (Join-Path $Root '.env') `
        --phase canonical `
        --receipt (Join-Path $State 'post-migration-credentials.json')
      if ($LASTEXITCODE -ne 0) { throw 'Canonical credential validation failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'previous-runtime-cleanup' -Action {
    & (Join-Path $PSScriptRoot 'clean_previous_runtime.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Previous runtime cleanup failed.' }
  }

  Invoke-SetupStage -Name 'isolated-virtual-environment' -Action {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (!$py) { throw 'Python launcher is not installed.' }
    $reuseVenv = $false
    if (Test-Path -LiteralPath $Python -PathType Leaf) {
      & $Python --version *> $null
      if ($LASTEXITCODE -eq 0) { $reuseVenv = $true }
      else { Remove-IncompleteVenv -Path $VenvPath }
    } elseif (Test-Path -LiteralPath $VenvPath) {
      Remove-IncompleteVenv -Path $VenvPath
    }
    if (!$reuseVenv) {
      & py -3.12 -m venv $VenvPath
      if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
      throw 'Isolated virtual environment Python was not created.'
    }
  }

  Invoke-SetupStage -Name 'pip-upgrade' -Action {
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
  }

  Invoke-SetupStage -Name 'dependency-installation' -Action {
    & $Python -m pip install -r (Join-Path $Root 'requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
  }

  Invoke-SetupStage -Name 'editable-project-installation' -Action {
    Push-Location $Root
    try {
      & $Python -m pip install --editable .
      if ($LASTEXITCODE -ne 0) { throw 'Editable project installation failed.' }
      $script:projectInstallation = 'PASS'
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'dependency-integrity-check' -Action {
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency integrity check failed.' }
  }

  Invoke-SetupStage -Name 'package-import-check' -Action {
    Push-Location $Root
    try {
      $script:packagePath = (& $Python -c "import pathlib, tradysquid; print(pathlib.Path(tradysquid.__file__).resolve())").Trim()
      if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:packagePath)) {
        throw 'Package import check failed.'
      }
      $script:packageImport = 'PASS'
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'source-compilation' -Action {
    Push-Location $Root
    try {
      & $Python -m compileall -q tradysquid scripts tests
      if ($LASTEXITCODE -ne 0) { throw 'Source compilation failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'automated-test-suite' -Action {
    Push-Location $Root
    try {
      & $Python -m pytest
      if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'installation-verification' -Action {
    Push-Location $Root
    try {
      & $Python -m scripts.verify_installation
      if ($LASTEXITCODE -ne 0) { throw 'Installation verification failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'live-read-only-verification' -Action {
    Push-Location $Root
    try {
      & $Python -m scripts.verify_live
      if ($LASTEXITCODE -ne 0) { throw 'Live read-only verification failed.' }
    } finally {
      Pop-Location
    }
  }

  Invoke-SetupStage -Name 'startup-task-registration' -Action {
    $taskName = 'Tradysquid Startup'
    $cmd = $env:ComSpec
    if ([string]::IsNullOrWhiteSpace($cmd)) { $cmd = 'cmd.exe' }
    $startCmd = Join-Path $Root 'START.cmd'
    $action = New-ScheduledTaskAction `
      -Execute $cmd `
      -Argument ('/d /c ""' + $startCmd + '""') `
      -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask `
      -TaskName $taskName `
      -Action $action `
      -Trigger $trigger `
      -Description 'Start the single-computer Tradysquid paper-trading system' `
      -Force | Out-Null
  }

  Invoke-SetupStage -Name 'application-start-and-readiness' -Action {
    & (Join-Path $PSScriptRoot 'start.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Application start or readiness verification failed.' }
  }

  Invoke-SetupStage -Name 'final-health-verification' -Action {
    $startup = Get-Content -LiteralPath (Join-Path $State 'startup.json') -Raw | ConvertFrom-Json
    $discord = Get-Content -LiteralPath (Join-Path $State 'discord-readiness.json') -Raw | ConvertFrom-Json
    $publishing = Get-Content -LiteralPath (Join-Path $State 'discord-publishing-bootstrap.json') -Raw | ConvertFrom-Json
    if ($startup.status -ne 'RUNNING') { throw 'Application startup receipt is not RUNNING.' }
    if ($discord.status -ne 'PASS') { throw 'Discord readiness receipt is not PASS.' }
    if ($publishing.status -ne 'PASS') { throw 'Discord publishing receipt is not PASS.' }
    if ([int]$publishing.persistent_cards.failed -ne 0) {
      throw 'One or more mandatory Discord cards failed publishing.'
    }
  }

  $status = 'PASS'
} catch {
  $failure = $_.Exception.Message
  $failedStage = $currentStage
  $status = 'FAILED'
  Write-Host "FAILED SETUP STAGE: $failedStage" -ForegroundColor Red
  Write-Host "ERROR: $failure" -ForegroundColor Red
  Write-Host "Detailed setup log: $Log" -ForegroundColor Yellow
} finally {
  $resultObject = [ordered]@{
    status = $status
    observed_at = (Get-Date).ToString('o')
    failed_stage = $failedStage
    error = $failure
    stages = @($stageRecords)
    backup = $backup
    log = $Log
    python_executable = $Python
    virtual_environment = $VenvPath
    tradysquid_package_path = $packagePath
    project_installation = $projectInstallation
    package_import = $packageImport
    startup_receipt = Join-Path $State 'startup.json'
    discord_readiness_receipt = Join-Path $State 'discord-readiness.json'
    discord_publishing_receipt = Join-Path $State 'discord-publishing-bootstrap.json'
    secret_values_written = $false
  }
  $resultObject | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
  @(
    $status,
    "failed_stage=$failedStage",
    "error=$failure",
    ($stageRecords | ForEach-Object { "$($_.status) $($_.name) $($_.duration_seconds)s" })
  ) | Set-Content -LiteralPath $ResultText -Encoding UTF8
  Stop-Transcript | Out-Null
  Write-Host $status
}

if ($status -ne 'PASS') { exit 1 }
