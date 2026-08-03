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
$ExitCodePath = Join-Path $StateDirectory 'setup-entry-exit-code.txt'
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

function Write-EntryExitCode {
    param([Parameter(Mandatory = $true)][int]$Code)

    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
    [IO.File]::WriteAllText(
        $ExitCodePath,
        [string]$Code,
        [Text.UTF8Encoding]::new($false)
    )
}

function Write-EarlyFailureReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Message,
        [object[]]$ParserErrors = @()
    )

    $FinishedAt = Get-Date
    $Commit = $null
    try {
        $Commit = (& git -C $Root rev-parse HEAD 2>$null).Trim()
    } catch {
        $Commit = $null
    }

    $Receipt = [ordered]@{
        status = 'FAILED'
        attempt_id = $AttemptId
        observed_at = $FinishedAt.ToString('o')
        started_at = $StartedAt.ToString('o')
        finished_at = $FinishedAt.ToString('o')
        failed_stage = $Stage
        error = $Message
        parser_errors = @($ParserErrors)
        setup_body_started = $false
        receipt_source = 'scripts/setup_entry.ps1'
        repository_path = $Root
        setup_script_path = $SetupBody
        setup_commit = $Commit
        expected_clean_commit = $ExpectedCleanCommit
        process_id = $PID
        parent_process_id = $ParentProcessId
        exit_code_receipt = $ExitCodePath
        secret_values_written = $false
    }

    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
    @(
        'FAILED'
        "attempt_id=$AttemptId"
        "failed_stage=$Stage"
        "error=$Message"
    ) | Set-Content -LiteralPath $ResultText -Encoding UTF8
}

try {
    foreach ($Directory in @($StateDirectory, $LogDirectory)) {
        New-Item -ItemType Directory -Force -Path $Directory | Out-Null
    }
    Remove-Item -LiteralPath $ExitCodePath -Force -ErrorAction SilentlyContinue

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
    & $SetupBody -AttemptId $AttemptId -ExpectedCleanCommit $ExpectedCleanCommit

    $BodyExitCode = 1
    if (Test-Path -LiteralPath $ResultJson -PathType Leaf) {
        try {
            $Receipt = Get-Content -LiteralPath $ResultJson -Raw | ConvertFrom-Json
            if ($Receipt.attempt_id -eq $AttemptId -and $Receipt.status -eq 'PASS') {
                $BodyExitCode = 0
            }
        } catch {
            $BodyExitCode = 1
        }
    }

    Write-EntryExitCode -Code $BodyExitCode
    exit $BodyExitCode
} catch {
    $Message = $_.Exception.Message
    Write-EarlyFailureReceipt -Stage 'setup-process-before-receipt' -Message $Message
    Write-EntryExitCode -Code 1
    Write-Host 'FAILED SETUP STAGE: setup-process-before-receipt' -ForegroundColor Red
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}
