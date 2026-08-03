param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit,

    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$LegacyCommit = 'ba75aae5f34f3889404bfe0c7c0b96663a92a657'
$ExpectedRemote = 'Angrysquid46/Tradysquid'
$CleanBranch = 'clean-rebuild'
$ArchiveBranch = 'archive/current-failed-implementation'
$InstallerRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'installer_helpers.ps1')

$Repository = $null
$OriginalBranch = $null
$OriginalCommit = $null
$BackupRoot = $null
$AttemptId = [guid]::NewGuid().ToString()
$Status = 'FAILED'
$FailedStage = 'initialization'
$ErrorMessage = $null
$SetupReceipt = $null
$SetupExitCode = 1
$StartedAt = Get-Date
$StopFlag = $null
$ResultPath = $null
$ExternalResultPath = $null

function Write-AutoResult {
    param([Parameter(Mandatory = $true)][string]$CurrentStatus)

    $ObservedBranch = $null
    $ObservedCommit = $null
    if ($Repository) {
        try { $ObservedBranch = (& git -C $Repository branch --show-current 2>$null).Trim() } catch {}
        try { $ObservedCommit = (& git -C $Repository rev-parse HEAD 2>$null).Trim() } catch {}
    }

    $Payload = [ordered]@{
        status = $CurrentStatus
        attempt_id = $AttemptId
        started_at = $StartedAt.ToString('o')
        observed_at = (Get-Date).ToString('o')
        failed_stage = $FailedStage
        error = $ErrorMessage
        repository_path = $Repository
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        expected_clean_commit = $ExpectedCleanCommit
        final_branch = $ObservedBranch
        final_commit = $ObservedCommit
        setup_exit_code = $SetupExitCode
        setup_receipt_status = if ($SetupReceipt) { [string]$SetupReceipt.status } else { $null }
        setup_failed_stage = if ($SetupReceipt) { [string]$SetupReceipt.failed_stage } else { $null }
        setup_error = if ($SetupReceipt) { [string]$SetupReceipt.error } else { $null }
        backup_root = $BackupRoot
        full_environment_preserved = $true
        secret_values_written = $false
    }

    $Json = $Payload | ConvertTo-Json -Depth 8
    foreach ($Path in @($ResultPath, $ExternalResultPath)) {
        if ([string]::IsNullOrWhiteSpace([string]$Path)) { continue }
        try {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
            $Json | Set-Content -LiteralPath $Path -Encoding UTF8
        } catch {}
    }
}

function Stop-RepositoryPython {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Escaped = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match $Escaped -and
            $_.Name -in @('python.exe', 'pythonw.exe')
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Copy-RuntimeSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    foreach ($Name in @('.env', 'data', 'state', 'logs')) {
        $Source = Join-Path $Root $Name
        if (-not (Test-Path -LiteralPath $Source)) { continue }
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    }

    $EnvironmentBackup = Join-Path $Destination '.env'
    if (-not (Test-Path -LiteralPath $EnvironmentBackup -PathType Leaf)) {
        throw 'The complete local .env was not preserved in the external handoff backup.'
    }
    return Get-VerifiedFileHash -Path $EnvironmentBackup
}

function Restore-RuntimeSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Source
    )

    foreach ($Name in @('.env', 'data', 'state', 'logs')) {
        $BackupItem = Join-Path $Source $Name
        if (-not (Test-Path -LiteralPath $BackupItem)) { continue }
        $Destination = Join-Path $Root $Name
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue
        }
        Copy-Item -LiteralPath $BackupItem -Destination $Destination -Recurse -Force
    }
}

function Start-LegacySupervisor {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Launcher = Join-Path $Root 'START-SUPERVISOR.cmd'
    if (Test-Path -LiteralPath $Launcher -PathType Leaf) {
        Start-Process -FilePath $Launcher -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
    }
}

try {
    $FailedStage = 'repository-verification'
    $Repository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
    $ResultPath = Join-Path $Repository 'state\clean-rebuild-auto-handoff.json'
    $StopFlag = Join-Path $Repository 'state\supervisor-stop.flag'

    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.git'))) {
        throw 'Repository path is not a Git working tree.'
    }
    $Remote = (& git -C $Repository remote get-url origin 2>$null)
    if ($LASTEXITCODE -ne 0 -or $Remote -notmatch [regex]::Escape($ExpectedRemote)) {
        throw 'Repository remote is unexpected or unreadable.'
    }

    $OriginalBranch = (& git -C $Repository branch --show-current).Trim()
    if (-not $OriginalBranch) { $OriginalBranch = 'main' }
    $OriginalCommit = (& git -C $Repository rev-parse HEAD).Trim()

    $FailedStage = 'complete-environment-preflight'
    $EnvironmentPath = Join-Path $Repository '.env'
    Test-MigrationSourceCredentials -EnvPath $EnvironmentPath | Out-Null

    $FailedStage = 'external-runtime-backup'
    $Parent = Split-Path -Parent $Repository
    $BackupRoot = Join-Path $Parent ('Tradysquid-auto-handoff-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $ExternalResultPath = Join-Path $BackupRoot 'clean-rebuild-auto-handoff.json'
    $EnvironmentHash = Copy-RuntimeSnapshot -Root $Repository -Destination $BackupRoot
    [ordered]@{
        status = 'PASS'
        repository = $Repository
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        environment_sha256 = $EnvironmentHash
        complete_environment_preserved = $true
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BackupRoot 'backup-receipt.json') -Encoding UTF8

    $FailedStage = 'runtime-stop'
    Stop-RepositoryPython -Root $Repository
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like '*Tradysquid*' } |
        Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

    $FailedStage = 'clean-branch-verification'
    & git -C $Repository fetch origin "+refs/heads/$CleanBranch`:refs/remotes/origin/$CleanBranch" "+refs/heads/$ArchiveBranch`:refs/remotes/origin/$ArchiveBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Git fetch for clean-rebuild failed.' }

    $ObservedArchive = (& git -C $Repository rev-parse "refs/remotes/origin/$ArchiveBranch").Trim()
    if ($ObservedArchive -ne $LegacyCommit) {
        throw "Archive branch mismatch. Expected $LegacyCommit but received $ObservedArchive."
    }
    $ObservedClean = (& git -C $Repository rev-parse "refs/remotes/origin/$CleanBranch").Trim()
    if ($ObservedClean -ne $ExpectedCleanCommit) {
        throw "Clean branch mismatch. Expected $ExpectedCleanCommit but received $ObservedClean."
    }

    $FailedStage = 'clean-branch-switch'
    & git -C $Repository switch --force-create $CleanBranch "origin/$CleanBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Could not switch the laptop checkout to clean-rebuild.' }

    $FailedStage = 'complete-environment-restore'
    $EnvironmentBackup = Join-Path $BackupRoot '.env'
    $RestoredHash = Restore-FileExact -BackupPath $EnvironmentBackup -DestinationPath (Join-Path $Repository '.env')
    if ($RestoredHash -ne $EnvironmentHash) {
        throw 'The restored complete environment does not match the external backup.'
    }

    $FailedStage = 'clean-setup'
    $SetupEntry = Join-Path $Repository 'scripts\setup_entry.ps1'
    $StdoutPath = Join-Path $BackupRoot 'setup-entry-stdout.log'
    $StderrPath = Join-Path $BackupRoot 'setup-entry-stderr.log'
    $Arguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"' + $SetupEntry + '"')
        '-AttemptId'
        $AttemptId
        '-ExpectedCleanCommit'
        $ExpectedCleanCommit
    )
    $Process = Start-Process -FilePath 'powershell.exe' -ArgumentList $Arguments -WorkingDirectory $Repository -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    $Process.WaitForExit()
    $SetupExitCode = [int]$Process.ExitCode

    $ReceiptPath = Join-Path $Repository 'SETUP-RESULT.json'
    if (Test-Path -LiteralPath $ReceiptPath -PathType Leaf) {
        $SetupReceipt = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json
    }
    if ($SetupExitCode -ne 0) {
        $SetupStage = if ($SetupReceipt -and $SetupReceipt.failed_stage) { [string]$SetupReceipt.failed_stage } else { 'setup-process' }
        $SetupError = if ($SetupReceipt -and $SetupReceipt.error) { [string]$SetupReceipt.error } else { "exit code $SetupExitCode" }
        throw "Clean setup failed at $SetupStage`: $SetupError"
    }
    if (-not $SetupReceipt -or [string]$SetupReceipt.attempt_id -ne $AttemptId -or [string]$SetupReceipt.status -ne 'PASS') {
        throw 'Clean setup did not produce a current PASS receipt.'
    }

    $FailedStage = $null
    $Status = 'PASS'
    Write-AutoResult -CurrentStatus $Status
} catch {
    $ErrorMessage = [string]$_.Exception.Message
    $Status = 'ROLLED BACK'

    if ($Repository -and $OriginalCommit) {
        try {
            $CleanStop = Join-Path $Repository 'scripts\stop.ps1'
            if (Test-Path -LiteralPath $CleanStop -PathType Leaf) {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CleanStop *> $null
            }
        } catch {}

        try {
            & git -C $Repository switch --force $OriginalBranch
            if ($LASTEXITCODE -ne 0) {
                & git -C $Repository switch --force main
            }
            & git -C $Repository reset --hard $OriginalCommit
        } catch {
            $Status = 'FAILED'
        }

        if ($BackupRoot) {
            try { Restore-RuntimeSnapshot -Root $Repository -Source $BackupRoot } catch { $Status = 'FAILED' }
        }
    } else {
        $Status = 'FAILED'
    }

    Write-AutoResult -CurrentStatus $Status
} finally {
    if ($StopFlag -and (Test-Path -LiteralPath $StopFlag)) {
        Remove-Item -LiteralPath $StopFlag -Force -ErrorAction SilentlyContinue
    }

    if ($Status -ne 'PASS' -and $Repository) {
        Start-LegacySupervisor -Root $Repository
    }
}

if ($Status -ne 'PASS') { exit 1 }
