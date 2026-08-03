$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$Log = Join-Path $Root 'logs\setup.log'
$VenvPath = Join-Path $Root '.venv-tradysquid'
$Python = Join-Path $VenvPath 'Scripts\python.exe'

New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs'),(Join-Path $Root 'backups'),(Join-Path $Root 'state'),(Join-Path $Root 'data') | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
$status='FAILED'
$steps=New-Object System.Collections.Generic.List[string]
$backup=''
$failure=$null
$projectInstallation='NOT STARTED'
$packageImport='NOT STARTED'
$packagePath=$null
$installationVerifierExitCode=$null
$liveVerifierExitCode=$null
$installationVerifierWorkingDirectory=$Root
$liveVerifierWorkingDirectory=$Root

function Add-Step([string]$Message) {
  $steps.Add($Message)
  Write-Host $Message
}

function Invoke-Native([string]$Description, [scriptblock]$Command) {
  Add-Step $Description
  $global:LASTEXITCODE = 0
  & $Command
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "$Description failed with exit code $exitCode."
  }
}

function Remove-IncompleteVenv([string]$Path) {
  if (!(Test-Path $Path)) { return }
  for ($attempt=1; $attempt -le 5; $attempt++) {
    try {
      Remove-Item $Path -Recurse -Force -ErrorAction Stop
      return
    } catch {
      if ($attempt -eq 5) { throw }
      Start-Sleep -Seconds 2
    }
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

  Invoke-Native 'canonical-credential-validation' {
    Push-Location $Root
    try {
      & py -3.12 -m tradysquid.operations.install_preflight `
        --env (Join-Path $Root '.env') `
        --phase canonical `
        --receipt (Join-Path $Root 'state\post-migration-credentials.json')
    } finally { Pop-Location }
  }
  Add-Step 'canonical-credentials-validated-after-migration'

  & (Join-Path $PSScriptRoot 'clean_previous_runtime.ps1')
  Add-Step 'previous-runtime-cleaned'

  # The failed application used .venv. The rebuild deliberately uses its own
  # path so a locked legacy python.exe cannot block installation.
  $reuseVenv = $false
  if (Test-Path $Python) {
    & $Python --version *> $null
    if ($LASTEXITCODE -eq 0) {
      $reuseVenv = $true
      Add-Step 'isolated-virtual-environment-reused'
    } else {
      Remove-IncompleteVenv $VenvPath
    }
  } elseif (Test-Path $VenvPath) {
    Remove-IncompleteVenv $VenvPath
  }

  if (!$reuseVenv) {
    Invoke-Native 'isolated-virtual-environment-creation' { & py -3.12 -m venv $VenvPath }
  }
  if (!(Test-Path $Python)) { throw 'Isolated virtual environment Python was not created.' }

  Invoke-Native 'pip-upgrade' { & $Python -m pip install --upgrade pip }
  Invoke-Native 'dependency-installation' { & $Python -m pip install -r (Join-Path $Root 'requirements-dev.txt') }
  Invoke-Native 'project-installation' {
    Push-Location $Root
    try { & $Python -m pip install --editable . }
    finally { Pop-Location }
  }
  $projectInstallation='PASS'
  Invoke-Native 'dependency-integrity-check' { & $Python -m pip check }

  Add-Step 'package-import-check'
  Push-Location $Root
  try {
    $packagePath = (& $Python -c "import pathlib, tradysquid; print(pathlib.Path(tradysquid.__file__).resolve())").Trim()
    $packageImportExitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($packageImportExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($packagePath)) {
    throw "package-import-check failed with exit code $packageImportExitCode."
  }
  $packageImport='PASS'

  Invoke-Native 'automated-test-suite' {
    Push-Location $Root
    try { & $Python -m pytest }
    finally { Pop-Location }
  }

  Add-Step 'installation-verification'
  Push-Location $Root
  try {
    & $Python -m scripts.verify_installation
    $installationVerifierExitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($installationVerifierExitCode -ne 0) {
    throw "installation-verification failed with exit code $installationVerifierExitCode."
  }

  Add-Step 'live-read-only-verification'
  Push-Location $Root
  try {
    & $Python -m scripts.verify_live
    $liveVerifierExitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($liveVerifierExitCode -ne 0) {
    throw "live-read-only-verification failed with exit code $liveVerifierExitCode."
  }

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
    error=$failure
    python_executable=$Python
    virtual_environment=$VenvPath
    tradysquid_package_path=$packagePath
    project_installation=$projectInstallation
    package_import=$packageImport
    installation_verifier=@{
      module='scripts.verify_installation'
      invocation='python -m scripts.verify_installation'
      working_directory=$installationVerifierWorkingDirectory
      exit_code=$installationVerifierExitCode
    }
    live_verifier=@{
      module='scripts.verify_live'
      invocation='python -m scripts.verify_live'
      working_directory=$liveVerifierWorkingDirectory
      exit_code=$liveVerifierExitCode
    }
    secret_values_written=$false
  } | ConvertTo-Json -Depth 7
  $result | Set-Content $ResultJson -Encoding UTF8
  ($status + [Environment]::NewLine + ($steps -join [Environment]::NewLine)) | Set-Content $ResultText -Encoding UTF8
  Stop-Transcript | Out-Null
  Write-Host $status
}
if ($status -ne 'PASS') { exit 1 }
