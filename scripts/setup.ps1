param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$AttemptId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$Log = Join-Path $Root 'logs\setup.log'
$VenvPath = Join-Path $Root '.venv-tradysquid'
$Python = Join-Path $VenvPath 'Scripts\python.exe'
$State = Join-Path $Root 'state'
$StageStatePath = Join-Path $State 'setup-stage-state.json'
$LivePreflightPath = Join-Path $State 'live-preflight.json'
$StartedAt = Get-Date
$SetupCommit = $null
$ParentProcessId = $null

try {
    $SetupCommit = (& git -C $Root rev-parse HEAD 2>$null).Trim()
} catch {
    $SetupCommit = $null
}

try {
    $CurrentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
    if ($CurrentProcess) {
        $ParentProcessId = $CurrentProcess.ParentProcessId
    }
} catch {
    $ParentProcessId = $null
}

$RequiredDirectories = @(
    (Join-Path $Root 'logs')
    (Join-Path $Root 'backups')
    $State
    (Join-Path $Root 'data')
)

foreach ($Directory in $RequiredDirectories) {
    New-Item -ItemType Directory -Force -Path $Directory | Out-Null
}

$status = 'FAILED'
$failure = $null
$failedStage = $null
$currentStage = 'setup-attempt-initialization'
$backup = ''
$projectInstallation = 'NOT STARTED'
$packageImport = 'NOT STARTED'
$packagePath = $null
$livePreflightStatus = 'NOT STARTED'
$livePreflightTradierStatus = 'NOT CHECKED'
$livePreflightWarnings = @()
$stageRecords = @()
$TranscriptStarted = $false

function Write-StageState {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][datetime]$StageStartedAt
    )

    [ordered]@{
        attempt_id = $AttemptId
        current_stage = $Name
        stage_status = $Status
        stage_started_at = $StageStartedAt.ToString('o')
        updated_at = (Get-Date).ToString('o')
        process_id = $PID
        parent_process_id = $ParentProcessId
        setup_commit = $SetupCommit
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StageStatePath -Encoding UTF8
}

function Add-StageRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][datetime]$Started,
        [Parameter(Mandatory = $true)][datetime]$Finished,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [AllowNull()][string]$ErrorMessage
    )

    $script:stageRecords += [pscustomobject]@{
        name = $Name
        status = $Status
        started_at = $Started.ToString('o')
        finished_at = $Finished.ToString('o')
        duration_seconds = [Math]::Round(($Finished - $Started).TotalSeconds, 3)
        exit_code = $ExitCode
        error = $ErrorMessage
    }
}

function Convert-StageRecordsToPlainArray {
    $PlainStages = @()
    foreach ($StageRecord in $script:stageRecords) {
        $PlainStages += [pscustomobject]@{
            name = [string]$StageRecord.name
            status = [string]$StageRecord.status
            started_at = [string]$StageRecord.started_at
            finished_at = [string]$StageRecord.finished_at
            duration_seconds = [double]$StageRecord.duration_seconds
            exit_code = [int]$StageRecord.exit_code
            error = if ($null -eq $StageRecord.error) { $null } else { [string]$StageRecord.error }
        }
    }
    return $PlainStages
}

function Invoke-SetupStage {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    $script:currentStage = $Name
    $StageStarted = Get-Date
    Write-StageState -Name $Name -Status 'RUNNING' -StageStartedAt $StageStarted
    Write-Host "START: $Name"

    try {
        $global:LASTEXITCODE = 0
        & $Action
        $ExitCode = $LASTEXITCODE
        if ($null -ne $ExitCode -and $ExitCode -ne 0) {
            throw "$Name returned exit code $ExitCode."
        }

        $Finished = Get-Date
        $NormalizedExitCode = if ($null -eq $ExitCode) { 0 } else { [int]$ExitCode }
        Add-StageRecord -Name $Name -Status 'PASS' -Started $StageStarted -Finished $Finished -ExitCode $NormalizedExitCode -ErrorMessage $null
        Write-StageState -Name $Name -Status 'PASS' -StageStartedAt $StageStarted
        Write-Host "PASS: $Name"
    } catch {
        $Finished = Get-Date
        $Message = [string]$_.Exception.Message
        $StageExitCode = if ($LASTEXITCODE) { [int]$LASTEXITCODE } else { 1 }
        Add-StageRecord -Name $Name -Status 'FAILED' -Started $StageStarted -Finished $Finished -ExitCode $StageExitCode -ErrorMessage $Message
        Write-StageState -Name $Name -Status 'FAILED' -StageStartedAt $StageStarted
        Write-Host "FAILED: $Name`: $Message" -ForegroundColor Red
        throw
    }
}

function Remove-IncompleteVenv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            if ($Attempt -eq 5) {
                throw
            }
            Start-Sleep -Seconds 2
        }
    }
}

try {
    Invoke-SetupStage -Name 'setup-attempt-initialization' -Action {
        Start-Transcript -Path $Log -Append | Out-Null
        $script:TranscriptStarted = $true
        if ($SetupCommit -ne $ExpectedCleanCommit) {
            throw "Setup commit mismatch. Expected $ExpectedCleanCommit but received $SetupCommit."
        }
        Write-Host "Attempt ID: $AttemptId"
        Write-Host "Setup commit: $SetupCommit"
        Write-Host "Repository: $Root"
    }

    Invoke-SetupStage -Name 'repository-verification' -Action {
        $Remote = & git -C $Root remote get-url origin
        if ($LASTEXITCODE -ne 0 -or $Remote -notmatch 'Angrysquid46/Tradysquid') {
            throw 'Unexpected or unreadable Git remote.'
        }
    }

    Invoke-SetupStage -Name 'backup-created' -Action {
        $script:backup = Join-Path $Root ("backups\pre-setup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Force -Path $script:backup | Out-Null
        foreach ($Name in @('.env', 'data', 'logs', 'state')) {
            $Source = Join-Path $Root $Name
            if (Test-Path -LiteralPath $Source) {
                Copy-Item -LiteralPath $Source -Destination $script:backup -Recurse -Force
            }
        }
    }

    Invoke-SetupStage -Name 'canonical-credential-migration' -Action {
        Push-Location $Root
        try {
            & py -3.12 -m tradysquid.operations.credential_migration --root $Root
            if ($LASTEXITCODE -ne 0) {
                throw 'Credential migration failed.'
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'canonical-credential-validation' -Action {
        Push-Location $Root
        try {
            $PreflightArguments = @(
                '-3.12'
                '-m'
                'tradysquid.operations.install_preflight'
                '--env'
                (Join-Path $Root '.env')
                '--phase'
                'canonical'
                '--receipt'
                (Join-Path $State 'post-migration-credentials.json')
            )
            & py @PreflightArguments
            if ($LASTEXITCODE -ne 0) {
                throw 'Canonical credential validation failed.'
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'previous-runtime-cleanup' -Action {
        & (Join-Path $PSScriptRoot 'clean_previous_runtime.ps1')
        if ($LASTEXITCODE -ne 0) {
            throw 'Previous runtime cleanup failed.'
        }
    }

    Invoke-SetupStage -Name 'isolated-virtual-environment' -Action {
        $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $PythonLauncher) {
            throw 'Python launcher is not installed.'
        }

        $ReuseVenv = $false
        if (Test-Path -LiteralPath $Python -PathType Leaf) {
            & $Python --version *> $null
            if ($LASTEXITCODE -eq 0) {
                $ReuseVenv = $true
            } else {
                Remove-IncompleteVenv -Path $VenvPath
            }
        } elseif (Test-Path -LiteralPath $VenvPath) {
            Remove-IncompleteVenv -Path $VenvPath
        }

        if (-not $ReuseVenv) {
            & py -3.12 -m venv $VenvPath
            if ($LASTEXITCODE -ne 0) {
                throw 'Virtual environment creation failed.'
            }
        }

        if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw 'Isolated virtual environment Python was not created.'
        }
    }

    Invoke-SetupStage -Name 'pip-upgrade' -Action {
        & $Python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw 'pip upgrade failed.'
        }
    }

    Invoke-SetupStage -Name 'dependency-installation' -Action {
        & $Python -m pip install -r (Join-Path $Root 'requirements-dev.txt')
        if ($LASTEXITCODE -ne 0) {
            throw 'Dependency installation failed.'
        }
    }

    Invoke-SetupStage -Name 'editable-project-installation' -Action {
        Push-Location $Root
        try {
            & $Python -m pip install --editable .
            if ($LASTEXITCODE -ne 0) {
                throw 'Editable project installation failed.'
            }
            $script:projectInstallation = 'PASS'
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'dependency-integrity-check' -Action {
        & $Python -m pip check
        if ($LASTEXITCODE -ne 0) {
            throw 'Dependency integrity check failed.'
        }
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
            if ($LASTEXITCODE -ne 0) {
                throw 'Source compilation failed.'
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'automated-test-suite' -Action {
        Push-Location $Root
        try {
            & $Python -m pytest
            if ($LASTEXITCODE -ne 0) {
                throw 'Automated tests failed.'
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'installation-verification' -Action {
        Push-Location $Root
        try {
            & $Python -m scripts.verify_installation
            if ($LASTEXITCODE -ne 0) {
                throw 'Installation verification failed.'
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'live-read-only-verification' -Action {
        Remove-Item -LiteralPath $LivePreflightPath -Force -ErrorAction SilentlyContinue
        Push-Location $Root
        try {
            & $Python -m scripts.verify_live
            $LiveExitCode = $LASTEXITCODE

            if (-not (Test-Path -LiteralPath $LivePreflightPath -PathType Leaf)) {
                throw "Live verifier returned exit code $LiveExitCode without creating $LivePreflightPath"
            }

            $LiveReceipt = Get-Content -LiteralPath $LivePreflightPath -Raw | ConvertFrom-Json
            $script:livePreflightStatus = [string]$LiveReceipt.status
            $script:livePreflightTradierStatus = if ($LiveReceipt.tradier_live_status) {
                [string]$LiveReceipt.tradier_live_status
            } else {
                'NOT REPORTED'
            }
            $script:livePreflightWarnings = @($LiveReceipt.warnings)

            Write-Host ("Live preflight status: " + $script:livePreflightStatus)
            Write-Host ("Tradier live status: " + $script:livePreflightTradierStatus)

            foreach ($Warning in $script:livePreflightWarnings) {
                Write-Host (
                    "LIVE PREFLIGHT WARNING: category={0}; check={1}; error={2}" -f
                    $Warning.category,
                    $Warning.check,
                    $Warning.error
                ) -ForegroundColor Yellow
            }

            if ($LiveExitCode -ne 0 -or $LiveReceipt.status -ne 'PASS') {
                $Category = if ($LiveReceipt.category) { [string]$LiveReceipt.category } else { 'UNKNOWN' }
                $Check = if ($LiveReceipt.failed_check) { [string]$LiveReceipt.failed_check } else { 'unknown-check' }
                $ErrorText = if ($LiveReceipt.error) { [string]$LiveReceipt.error } else { 'No sanitized error was reported.' }
                throw "Live preflight failed: category=$Category; check=$Check; error=$ErrorText"
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-SetupStage -Name 'startup-task-registration' -Action {
        $TaskName = 'Tradysquid Startup'
        $CommandShell = $env:ComSpec
        if ([string]::IsNullOrWhiteSpace($CommandShell)) {
            $CommandShell = 'cmd.exe'
        }

        $StartCommand = Join-Path $Root 'START.cmd'
        $TaskActionParameters = @{
            Execute = $CommandShell
            Argument = '/d /c ""' + $StartCommand + '""'
            WorkingDirectory = $Root
        }
        $TaskAction = New-ScheduledTaskAction @TaskActionParameters
        $TaskTrigger = New-ScheduledTaskTrigger -AtLogOn
        $RegistrationParameters = @{
            TaskName = $TaskName
            Action = $TaskAction
            Trigger = $TaskTrigger
            Description = 'Start the single-computer Tradysquid paper-trading system'
            Force = $true
        }
        Register-ScheduledTask @RegistrationParameters | Out-Null
    }

    Invoke-SetupStage -Name 'application-start-and-readiness' -Action {
        & (Join-Path $PSScriptRoot 'start.ps1')
        if ($LASTEXITCODE -ne 0) {
            throw 'Application start or readiness verification failed.'
        }
    }

    Invoke-SetupStage -Name 'final-health-verification' -Action {
        $Startup = Get-Content -LiteralPath (Join-Path $State 'startup.json') -Raw | ConvertFrom-Json
        $Discord = Get-Content -LiteralPath (Join-Path $State 'discord-readiness.json') -Raw | ConvertFrom-Json
        $Publishing = Get-Content -LiteralPath (Join-Path $State 'discord-publishing-bootstrap.json') -Raw | ConvertFrom-Json

        if ($Startup.status -ne 'RUNNING') {
            throw 'Application startup receipt is not RUNNING.'
        }
        if ($Discord.status -ne 'PASS') {
            throw 'Discord readiness receipt is not PASS.'
        }
        if ($Publishing.status -ne 'PASS') {
            throw 'Discord publishing receipt is not PASS.'
        }
        if ([int]$Publishing.persistent_cards.failed -ne 0) {
            throw 'One or more mandatory Discord cards failed publishing.'
        }
    }

    $status = 'PASS'
} catch {
    $failure = [string]$_.Exception.Message
    $failedStage = $currentStage
    $status = 'FAILED'
    Write-Host "FAILED SETUP STAGE: $failedStage" -ForegroundColor Red
    Write-Host "ERROR: $failure" -ForegroundColor Red
    Write-Host "Detailed setup log: $Log" -ForegroundColor Yellow
} finally {
    $FinishedAt = Get-Date
    $StageArray = Convert-StageRecordsToPlainArray
    $ResultObject = [ordered]@{
        status = [string]$status
        attempt_id = [string]$AttemptId
        observed_at = $FinishedAt.ToString('o')
        started_at = $StartedAt.ToString('o')
        finished_at = $FinishedAt.ToString('o')
        failed_stage = $failedStage
        error = $failure
        stages = $StageArray
        backup = $backup
        log = $Log
        repository_path = $Root
        setup_script_path = $PSCommandPath
        setup_commit = $SetupCommit
        expected_clean_commit = $ExpectedCleanCommit
        process_id = [int]$PID
        parent_process_id = $ParentProcessId
        python_executable = $Python
        virtual_environment = $VenvPath
        tradysquid_package_path = $packagePath
        project_installation = $projectInstallation
        package_import = $packageImport
        live_preflight_receipt = $LivePreflightPath
        live_preflight_status = $livePreflightStatus
        live_preflight_tradier_status = $livePreflightTradierStatus
        live_preflight_warnings = @($livePreflightWarnings)
        startup_receipt = Join-Path $State 'startup.json'
        discord_readiness_receipt = Join-Path $State 'discord-readiness.json'
        discord_publishing_receipt = Join-Path $State 'discord-publishing-bootstrap.json'
        secret_values_written = $false
    }

    try {
        $ResultObject | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
        $ResultLines = @(
            [string]$status
            "attempt_id=$AttemptId"
            "failed_stage=$failedStage"
            "error=$failure"
        )
        foreach ($StageRecord in $StageArray) {
            $ResultLines += "$($StageRecord.status) $($StageRecord.name) $($StageRecord.duration_seconds)s"
        }
        $ResultLines | Set-Content -LiteralPath $ResultText -Encoding UTF8
    } catch {
        $ReceiptError = [string]$_.Exception.Message
        $MinimalReceipt = [ordered]@{
            status = [string]$status
            attempt_id = [string]$AttemptId
            observed_at = (Get-Date).ToString('o')
            failed_stage = $failedStage
            error = $failure
            receipt_error = $ReceiptError
            repository_path = $Root
            setup_commit = $SetupCommit
            expected_clean_commit = $ExpectedCleanCommit
            log = $Log
            secret_values_written = $false
        }
        $MinimalReceipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
        @(
            [string]$status
            "attempt_id=$AttemptId"
            "failed_stage=$failedStage"
            "error=$failure"
            "receipt_error=$ReceiptError"
        ) | Set-Content -LiteralPath $ResultText -Encoding UTF8
    }

    if ($TranscriptStarted) {
        Stop-Transcript | Out-Null
    }
    Write-Host $status
}

if ($status -ne 'PASS') {
    exit 1
}
