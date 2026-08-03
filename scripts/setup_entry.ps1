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
$SetupBody = Join-Path $PSScriptRoot 'setup.ps1'
$ResultJson = Join-Path $Root 'SETUP-RESULT.json'
$ResultText = Join-Path $Root 'SETUP-RESULT.txt'
$StateDirectory = Join-Path $Root 'state'
$LogDirectory = Join-Path $Root 'logs'
$StageStatePath = Join-Path $StateDirectory 'setup-stage-state.json'
$StartupReceiptPath = Join-Path $StateDirectory 'startup.json'
$ExitCodePath = Join-Path $StateDirectory 'setup-entry-exit-code.txt'
$BodyStdoutPath = Join-Path $LogDirectory 'setup-body-stdout.log'
$BodyStderrPath = Join-Path $LogDirectory 'setup-body-stderr.log'
$StartedAt = Get-Date
$ParentProcessId = $null

try {
    $CurrentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
    if ($CurrentProcess) {
        $ParentProcessId = $CurrentProcess.ParentProcessId
    }
} catch {
    $ParentProcessId = $null
}

function Get-SanitizedEntryText {
    param([AllowNull()][string]$Text)

    if ($null -eq $Text) {
        return ''
    }
    $Sanitized = $Text
    foreach ($Name in @(
        'DISCORD_BOT_TOKEN',
        'TRADIER_ACCESS_TOKEN',
        'TRADIER_TOKEN',
        'OPENAI_API_KEY',
        'GITHUB_UPGRADE_TOKEN',
        'NGROK_AUTHTOKEN',
        'TRADINGVIEW_WEBHOOK_SECRET'
    )) {
        $Pattern = '(?im)(' + [regex]::Escape($Name) + '\s*=\s*)[^\r\n]+'
        $Sanitized = [regex]::Replace($Sanitized, $Pattern, '$1<redacted>')
    }
    $Sanitized = [regex]::Replace(
        $Sanitized,
        '(?im)(Authorization\s*:\s*)(Bot|Bearer)\s+[^\s\r\n]+',
        '$1$2 <redacted>'
    )
    return $Sanitized
}

function Write-EntryExitCode {
    param([Parameter(Mandatory = $true)][int]$Code)

    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
    [IO.File]::WriteAllText(
        $ExitCodePath,
        [string]$Code,
        [Text.UTF8Encoding]::new($false)
    )
}

function Get-CurrentCommit {
    try {
        return (& git -C $Root rev-parse HEAD 2>$null).Trim()
    } catch {
        return $null
    }
}

function Write-EarlyFailureReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Message,
        [object[]]$ParserErrors = @(),
        [bool]$SetupBodyStarted = $false,
        [AllowNull()][int]$BodyExitCode = $null
    )

    $FinishedAt = Get-Date
    $SafeMessage = Get-SanitizedEntryText -Text $Message
    $Receipt = [ordered]@{
        status = 'FAILED'
        attempt_id = $AttemptId
        observed_at = $FinishedAt.ToString('o')
        started_at = $StartedAt.ToString('o')
        finished_at = $FinishedAt.ToString('o')
        failed_stage = $Stage
        error = $SafeMessage
        parser_errors = @($ParserErrors)
        setup_body_started = $SetupBodyStarted
        setup_body_exit_code = $BodyExitCode
        receipt_source = 'scripts/setup_entry.ps1'
        repository_path = $Root
        setup_script_path = $SetupBody
        setup_commit = Get-CurrentCommit
        expected_clean_commit = $ExpectedCleanCommit
        process_id = $PID
        parent_process_id = $ParentProcessId
        exit_code_receipt = $ExitCodePath
        body_stdout = $BodyStdoutPath
        body_stderr = $BodyStderrPath
        secret_values_written = $false
    }

    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
    @(
        'FAILED'
        "attempt_id=$AttemptId"
        "failed_stage=$Stage"
        "error=$SafeMessage"
        "setup_body_started=$SetupBodyStarted"
        "setup_body_exit_code=$BodyExitCode"
    ) | Set-Content -LiteralPath $ResultText -Encoding UTF8
}

function Test-CurrentBodyReceipt {
    if (-not (Test-Path -LiteralPath $ResultJson -PathType Leaf)) {
        return $false
    }
    try {
        $Receipt = Get-Content -LiteralPath $ResultJson -Raw | ConvertFrom-Json
        if ($Receipt.attempt_id -ne $AttemptId) { return $false }
        if (-not $Receipt.observed_at) { return $false }
        if ([datetime]$Receipt.observed_at -lt $StartedAt) { return $false }
        if ([IO.Path]::GetFullPath([string]$Receipt.repository_path) -ne [IO.Path]::GetFullPath($Root)) {
            return $false
        }
        if ($Receipt.setup_commit -ne $ExpectedCleanCommit) { return $false }
        return $true
    } catch {
        return $false
    }
}

function Get-FallbackFailureDetails {
    param([Parameter(Mandatory = $true)][int]$BodyExitCode)

    $Stage = 'setup-process-before-receipt'
    $Parts = New-Object System.Collections.Generic.List[string]
    $Parts.Add("Setup body exited with code $BodyExitCode before writing a valid current-attempt receipt.")

    if (Test-Path -LiteralPath $StageStatePath -PathType Leaf) {
        try {
            $State = Get-Content -LiteralPath $StageStatePath -Raw | ConvertFrom-Json
            if ($State.attempt_id -eq $AttemptId -and $State.current_stage) {
                $Stage = [string]$State.current_stage
                $Parts.Add("Last recorded setup stage was $Stage with status $($State.stage_status).")
            }
        } catch {
            $null = $_
        }
    }

    if (Test-Path -LiteralPath $StartupReceiptPath -PathType Leaf) {
        try {
            $Startup = Get-Content -LiteralPath $StartupReceiptPath -Raw | ConvertFrom-Json
            if ($Startup.status -eq 'FAILED' -and $Startup.error) {
                $Parts.Add("Application startup failed: $($Startup.error)")
            }
        } catch {
            $null = $_
        }
    }

    if (Test-Path -LiteralPath $BodyStderrPath -PathType Leaf) {
        $Tail = (Get-Content -LiteralPath $BodyStderrPath -Tail 20 -ErrorAction SilentlyContinue) -join ' | '
        if ($Tail) {
            $Parts.Add("Setup stderr: $Tail")
        }
    }

    return [pscustomobject]@{
        Stage = $Stage
        Message = Get-SanitizedEntryText -Text ($Parts -join ' ')
    }
}

try {
    foreach ($Directory in @($StateDirectory, $LogDirectory)) {
        New-Item -ItemType Directory -Force -Path $Directory | Out-Null
    }
    foreach ($Path in @($ExitCodePath, $BodyStdoutPath, $BodyStderrPath)) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $SetupBody -PathType Leaf)) {
        throw "Setup body was not found: $SetupBody"
    }

    $Tokens = $null
    $ParseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $SetupBody,
        [ref]$Tokens,
        [ref]$ParseErrors
    )

    if ($ParseErrors.Count -gt 0) {
        $SafeErrors = @(
            $ParseErrors | ForEach-Object {
                [pscustomobject]@{
                    message = $_.Message
                    line = $_.Extent.StartLineNumber
                    column = $_.Extent.StartColumnNumber
                    text = $_.Extent.Text
                }
            }
        )
        $Message = 'PowerShell syntax validation failed: ' + ($SafeErrors | ConvertTo-Json -Compress)
        Write-EarlyFailureReceipt -Stage 'setup-script-parse-validation' -Message $Message -ParserErrors $SafeErrors
        Write-EntryExitCode -Code 1
        Write-Host 'FAILED SETUP STAGE: setup-script-parse-validation' -ForegroundColor Red
        Write-Host "ERROR: $Message" -ForegroundColor Red
        exit 1
    }

    Write-Host 'PASS: setup-script-parse-validation'
    Write-Host "SETUP ATTEMPT: $AttemptId"

    $PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = $PowerShellPath
    $ProcessInfo.Arguments = (
        '-NoProfile -ExecutionPolicy Bypass -File "' +
        $SetupBody +
        '" -AttemptId "' +
        $AttemptId +
        '" -ExpectedCleanCommit "' +
        $ExpectedCleanCommit +
        '"'
    )
    $ProcessInfo.WorkingDirectory = $Root
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true

    $BodyProcess = New-Object System.Diagnostics.Process
    $BodyProcess.StartInfo = $ProcessInfo
    if (-not $BodyProcess.Start()) {
        throw 'Could not start the setup body process.'
    }

    $StdoutTask = $BodyProcess.StandardOutput.ReadToEndAsync()
    $StderrTask = $BodyProcess.StandardError.ReadToEndAsync()
    $BodyProcess.WaitForExit()
    $StdoutTask.Wait()
    $StderrTask.Wait()

    $BodyExitCode = [int]$BodyProcess.ExitCode
    $SafeStdout = Get-SanitizedEntryText -Text $StdoutTask.Result
    $SafeStderr = Get-SanitizedEntryText -Text $StderrTask.Result
    [IO.File]::WriteAllText($BodyStdoutPath, $SafeStdout, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($BodyStderrPath, $SafeStderr, [Text.UTF8Encoding]::new($false))

    if ($SafeStdout) {
        Write-Host $SafeStdout.TrimEnd()
    }
    if ($SafeStderr) {
        [Console]::Error.WriteLine($SafeStderr.TrimEnd())
    }

    if (-not (Test-CurrentBodyReceipt)) {
        $Fallback = Get-FallbackFailureDetails -BodyExitCode $BodyExitCode
        Write-EarlyFailureReceipt `
            -Stage $Fallback.Stage `
            -Message $Fallback.Message `
            -SetupBodyStarted $true `
            -BodyExitCode $BodyExitCode
        $BodyExitCode = 1
    }

    Write-EntryExitCode -Code $BodyExitCode
    exit $BodyExitCode
} catch {
    $Message = Get-SanitizedEntryText -Text $_.Exception.Message
    Write-EarlyFailureReceipt -Stage 'setup-process-before-receipt' -Message $Message
    Write-EntryExitCode -Code 1
    Write-Host 'FAILED SETUP STAGE: setup-process-before-receipt' -ForegroundColor Red
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}
