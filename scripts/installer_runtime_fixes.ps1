Set-StrictMode -Version Latest

function Get-SetupStageTimeoutSeconds {
    param([Parameter(Mandatory = $true)][string]$Stage)

    $Timeouts = @{
        'setup-script-parse-validation' = 30
        'setup-attempt-initialization' = 60
        'repository-verification' = 60
        'backup-created' = 300
        'canonical-credential-migration' = 120
        'canonical-credential-validation' = 120
        'previous-runtime-cleanup' = 120
        'isolated-virtual-environment' = 300
        'pip-upgrade' = 300
        'dependency-installation' = 600
        'editable-project-installation' = 300
        'dependency-integrity-check' = 120
        'package-import-check' = 120
        'source-compilation' = 300
        'automated-test-suite' = 600
        'installation-verification' = 120
        'live-read-only-verification' = 120
        'startup-task-registration' = 120
        # First-run Discord reconciliation may create/reuse dozens of channels and
        # publish mandatory cards, 27 lessons, and journals under Discord rate limits.
        'application-start-and-readiness' = 900
        'final-health-verification' = 120
    }

    if ($Timeouts.ContainsKey($Stage)) {
        return [int]$Timeouts[$Stage]
    }
    return 600
}

function Read-SharedTextFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ''
    }

    $Share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $Stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        $Share
    )
    $Reader = New-Object IO.StreamReader($Stream, [Text.Encoding]::UTF8, $true)
    try {
        return $Reader.ReadToEnd()
    } finally {
        $Reader.Dispose()
        $Stream.Dispose()
    }
}

function Write-SanitizedLogFile {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    $RawText = Read-SharedTextFile -Path $SourcePath
    $SafeText = Get-SanitizedText -Text $RawText
    $Parent = Split-Path -Parent $DestinationPath
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null

    $TemporaryPath = $DestinationPath + '.new'
    for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
        try {
            [IO.File]::WriteAllText(
                $TemporaryPath,
                $SafeText,
                [Text.UTF8Encoding]::new($false)
            )
            Move-Item -LiteralPath $TemporaryPath -Destination $DestinationPath -Force
            return $SafeText
        } catch {
            Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
            if ($Attempt -eq 10) {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Remove-FileAfterRedirectRelease {
    param([Parameter(Mandatory = $true)][string]$Path)

    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
            return $true
        } catch {
            if ($Attempt -eq 20) {
                return $false
            }
            Start-Sleep -Milliseconds 250
        }
    }
    return $false
}

function Stop-SetupProcessTree {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $TaskKill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($TaskKill) {
        & $TaskKill.Source /PID $ProcessId /T /F *> $null
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-SetupProcess {
    param(
        [Parameter(Mandatory = $true)][string]$SetupEntryScript,
        [Parameter(Mandatory = $true)][string]$SetupBodyScript,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$AttemptId,
        [Parameter(Mandatory = $true)][string]$ExpectedCleanCommit
    )

    Test-PowerShellScriptSyntax -Path $SetupEntryScript | Out-Null
    Test-PowerShellScriptSyntax -Path $SetupBodyScript | Out-Null
    $PreviousArtifacts = Archive-PreviousSetupArtifacts -Root $WorkingDirectory

    $LogDirectory = Join-Path $WorkingDirectory 'logs'
    $StateDirectory = Join-Path $WorkingDirectory 'state'
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null

    $StdoutPath = Join-Path $LogDirectory 'setup-child-stdout.log'
    $StderrPath = Join-Path $LogDirectory 'setup-child-stderr.log'
    $RawStdoutPath = Join-Path $LogDirectory 'setup-child-stdout.raw.log'
    $RawStderrPath = Join-Path $LogDirectory 'setup-child-stderr.raw.log'
    $HeartbeatPath = Join-Path $StateDirectory 'setup-heartbeat.json'
    $StageStatePath = Join-Path $StateDirectory 'setup-stage-state.json'
    $EntryExitCodePath = Join-Path $StateDirectory 'setup-entry-exit-code.txt'

    foreach ($Path in @($RawStdoutPath, $RawStderrPath, $StdoutPath, $StderrPath)) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }

    $Arguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"' + $SetupEntryScript + '"')
        '-AttemptId'
        $AttemptId
        '-ExpectedCleanCommit'
        $ExpectedCleanCommit
    )

    $StartedAt = Get-Date
    $ProcessParameters = @{
        FilePath = (Get-Command powershell.exe -ErrorAction Stop).Source
        ArgumentList = $Arguments
        WorkingDirectory = $WorkingDirectory
        NoNewWindow = $true
        PassThru = $true
        RedirectStandardOutput = $RawStdoutPath
        RedirectStandardError = $RawStderrPath
    }
    $Process = Start-Process @ProcessParameters
    if ($null -eq $Process) {
        throw 'Could not start the clean setup process.'
    }

    $ProcessId = [int]$Process.Id
    $CurrentStage = 'setup-attempt-initialization'
    $StageStartedAt = $StartedAt
    $LastHeartbeatAt = [datetime]::MinValue
    $LastConsoleUpdateAt = [datetime]::MinValue
    $TimedOutStage = $null

    while (-not $Process.HasExited) {
        Start-Sleep -Seconds 2
        $Process.Refresh()

        if (Test-Path -LiteralPath $StageStatePath -PathType Leaf) {
            try {
                $StageState = Get-Content -LiteralPath $StageStatePath -Raw | ConvertFrom-Json
                if ($StageState.attempt_id -eq $AttemptId -and $StageState.current_stage) {
                    if ($CurrentStage -ne [string]$StageState.current_stage) {
                        $CurrentStage = [string]$StageState.current_stage
                        $StageStartedAt = [datetime]$StageState.stage_started_at
                    }
                }
            } catch {
                $null = $_
            }
        }

        $Now = Get-Date
        if (($Now - $LastHeartbeatAt).TotalSeconds -ge 10) {
            Write-SetupHeartbeat -Path $HeartbeatPath -AttemptId $AttemptId -CurrentStage $CurrentStage -StageStartedAt $StageStartedAt -ProcessId $ProcessId
            $LastHeartbeatAt = $Now
        }
        if (($Now - $LastConsoleUpdateAt).TotalSeconds -ge 15) {
            $Elapsed = [Math]::Round(($Now - $StageStartedAt).TotalSeconds)
            Write-Host "Still running: $CurrentStage - $Elapsed seconds"
            $LastConsoleUpdateAt = $Now
        }

        $TimeoutSeconds = Get-SetupStageTimeoutSeconds -Stage $CurrentStage
        if (($Now - $StageStartedAt).TotalSeconds -gt $TimeoutSeconds) {
            $TimedOutStage = $CurrentStage
            Stop-SetupProcessTree -ProcessId $ProcessId
            break
        }
    }

    $NativeExitCode = $null
    try {
        $Process.WaitForExit()
        $Process.Refresh()
        if ($Process.HasExited) {
            $NativeExitCode = [int]$Process.ExitCode
        }
    } finally {
        $Process.Dispose()
    }
    $ExitedAt = Get-Date

    # Never rewrite the file used by RedirectStandardOutput/RedirectStandardError.
    # Windows may retain those handles briefly even after the child exits.
    $Stdout = Write-SanitizedLogFile -SourcePath $RawStdoutPath -DestinationPath $StdoutPath
    $Stderr = Write-SanitizedLogFile -SourcePath $RawStderrPath -DestinationPath $StderrPath
    $RawStdoutRemoved = Remove-FileAfterRedirectRelease -Path $RawStdoutPath
    $RawStderrRemoved = Remove-FileAfterRedirectRelease -Path $RawStderrPath

    foreach ($Line in @($Stdout -split "`r?`n" | Select-Object -Last 30)) {
        if (-not [string]::IsNullOrWhiteSpace($Line)) {
            Write-Host $Line
        }
    }
    foreach ($Line in @($Stderr -split "`r?`n" | Select-Object -Last 30)) {
        if (-not [string]::IsNullOrWhiteSpace($Line)) {
            Write-Host "STDERR: $Line" -ForegroundColor Red
        }
    }

    $ExitCode = $null
    if (Test-Path -LiteralPath $EntryExitCodePath -PathType Leaf) {
        $RawExitCode = (Get-Content -LiteralPath $EntryExitCodePath -Raw).Trim()
        $ParsedExitCode = 0
        if ([int]::TryParse($RawExitCode, [ref]$ParsedExitCode)) {
            $ExitCode = $ParsedExitCode
        }
    }
    if ($null -eq $ExitCode) {
        $ExitCode = $NativeExitCode
    }
    if ($null -eq $ExitCode) {
        $ExitCode = 1
    }
    if ($TimedOutStage) {
        $ExitCode = 124
    }

    return [pscustomobject]@{
        ProcessId = $ProcessId
        StartedAt = $StartedAt.ToString('o')
        ExitedAt = $ExitedAt.ToString('o')
        ExitCode = [int]$ExitCode
        WaitedForExit = $true
        AttemptId = $AttemptId
        StdoutPath = $StdoutPath
        StderrPath = $StderrPath
        RawStdoutPath = $RawStdoutPath
        RawStderrPath = $RawStderrPath
        RawStdoutRemoved = $RawStdoutRemoved
        RawStderrRemoved = $RawStderrRemoved
        EntryExitCodePath = $EntryExitCodePath
        PreviousArtifacts = $PreviousArtifacts
        TimedOutStage = $TimedOutStage
        LastObservedStage = $CurrentStage
    }
}
