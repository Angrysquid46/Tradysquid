param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$LegacyCommit = 'ba75aae5f34f3889404bfe0c7c0b96663a92a657'
$ExpectedRemote = 'Angrysquid46/Tradysquid'
$CleanBranch = 'clean-rebuild'
$ArchiveBranch = 'archive/current-failed-implementation'
$ScriptPath = $PSCommandPath
$ScriptRoot = Split-Path -Parent $ScriptPath
. (Join-Path $ScriptRoot 'installer_helpers.ps1')

$ResultPath = Join-Path $ScriptRoot '..\CLEAN-REBUILD-INSTALL-RESULT.json'
$LogPath = Join-Path $ScriptRoot '..\logs\clean-rebuild-install.log'
$Repository = $null
$Backup = $null
$OriginalBranch = $null
$OriginalCommit = $null
$CleanCommit = $null
$SetupProcess = $null
$SetupReceipt = $null
$Switched = $false
$RollbackResult = 'NOT REQUIRED'
$Steps = New-Object System.Collections.Generic.List[string]

function Add-Step {
    param([Parameter(Mandatory=$true)][string]$Message)
    $Steps.Add($Message)
    Write-Host $Message
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-TradysquidRepository {
    $candidates = New-Object System.Collections.Generic.List[string]
    $candidates.Add((Get-Location).Path)
    $candidates.Add((Split-Path -Parent $ScriptRoot))
    $candidates.Add('C:\Tradysquid\app')
    $candidates.Add('C:\Tradysquid')
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE 'Tradysquid'))
        $candidates.Add((Join-Path $env:USERPROFILE 'Documents\Tradysquid'))
        $candidates.Add((Join-Path $env:USERPROFILE 'Desktop\Tradysquid'))
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) { continue }
        if (-not (Test-Path -LiteralPath (Join-Path $candidate '.git'))) { continue }
        try {
            $remote = (& git -C $candidate remote get-url origin 2>$null)
            if ($LASTEXITCODE -eq 0 -and $remote -match [regex]::Escape($ExpectedRemote)) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        } catch {
            continue
        }
    }
    throw "Could not locate the local $ExpectedRemote repository."
}

function New-ExternalBackup {
    param([Parameter(Mandatory=$true)][string]$Root)

    $parent = Split-Path -Parent $Root
    $destination = Join-Path $parent ('Tradysquid-legacy-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $installation = Join-Path $destination 'installation'
    New-Item -ItemType Directory -Force -Path $installation | Out-Null

    & git -C $Root status --porcelain=v1 -uall |
        Set-Content (Join-Path $destination 'git-status.txt') -Encoding UTF8
    & git -C $Root diff |
        Set-Content (Join-Path $destination 'tracked-working-tree.patch') -Encoding UTF8
    & git -C $Root diff --cached |
        Set-Content (Join-Path $destination 'staged-working-tree.patch') -Encoding UTF8
    & git -C $Root branch --all --verbose |
        Set-Content (Join-Path $destination 'git-branches.txt') -Encoding UTF8
    & git -C $Root log -1 --format=fuller |
        Set-Content (Join-Path $destination 'git-head.txt') -Encoding UTF8

    $robocopyArgs = @(
        $Root,
        $installation,
        '/E',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/R:1',
        '/W:1',
        '/XJ',
        '/XD', '.git', '.venv', '.venv-tradysquid', '__pycache__', '.pytest_cache',
        '/XF', '*.pyc', '*.pyo'
    )
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Local backup failed with robocopy exit code $LASTEXITCODE."
    }

    $envSource = Join-Path $Root '.env'
    $envBackup = Join-Path $installation '.env'
    if (-not (Test-Path -LiteralPath $envBackup -PathType Leaf)) {
        throw 'The ignored .env was not preserved in the external backup.'
    }
    $envHash = Get-VerifiedFileHash -Path $envBackup
    $receipt = [ordered]@{
        status = 'PASS'
        observed_at = (Get-Date).ToString('o')
        repository = $Root
        installation = $installation
        env_backup = $envBackup
        env_sha256 = $envHash
        secret_values_written = $false
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content (Join-Path $destination 'backup-receipt.json') -Encoding UTF8
    return $destination
}

function Stop-TradysquidPython {
    param([Parameter(Mandatory=$true)][string]$Root)

    $escaped = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match $escaped -and
            $_.Name -in @('python.exe', 'pythonw.exe')
        } |
        ForEach-Object {
            Add-Step "Stopping repository-owned Python process $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like '*Tradysquid*' } |
        ForEach-Object {
            Add-Step "Disabling previous Tradysquid task: $($_.TaskName)"
            Disable-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue | Out-Null
        }
}

function Read-SetupReceipt {
    param([Parameter(Mandatory=$true)][string]$Root)

    $path = Join-Path $Root 'SETUP-RESULT.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    } catch {
        Add-Step ('Could not parse setup receipt: ' + $_.Exception.Message)
        return $null
    }
}

function Restore-PreviousInstallation {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$BackupRoot
    )

    try {
        & git -C $Root switch --force $Branch
        if ($LASTEXITCODE -ne 0) {
            & git -C $Root switch --force main
            if ($LASTEXITCODE -ne 0) { throw 'Could not restore the previous Git branch.' }
        }

        $envBackup = Join-Path $BackupRoot 'installation\.env'
        $restoredHash = Restore-FileExact `
            -BackupPath $envBackup `
            -DestinationPath (Join-Path $Root '.env')
        Add-Step "Original .env restored with SHA-256 $restoredHash"

        $legacyStart = Join-Path $Root 'START-SUPERVISOR.cmd'
        if (Test-Path -LiteralPath $legacyStart -PathType Leaf) {
            Start-Process -FilePath $legacyStart -WorkingDirectory $Root | Out-Null
        }
        return 'PASS'
    } catch {
        Add-Step ('Rollback error: ' + $_.Exception.Message)
        return 'FAILED'
    }
}

if (-not (Test-Administrator)) {
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $ScriptPath + '"'),
        '-ExpectedCleanCommit', $ExpectedCleanCommit
    )
    Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs | Out-Null
    exit 0
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
Start-Transcript -Path $LogPath -Append | Out-Null
$Status = 'FAILED'
$FailureStage = $null
$FailureReason = $null

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git for Windows is not installed or is not available in PATH.'
    }

    $FailureStage = 'repository-discovery'
    $Repository = Find-TradysquidRepository
    Add-Step "Repository found: $Repository"

    $OriginalBranch = (& git -C $Repository branch --show-current).Trim()
    $OriginalCommit = (& git -C $Repository rev-parse HEAD).Trim()
    if (-not $OriginalBranch) { $OriginalBranch = 'main' }
    Add-Step "Current branch: $OriginalBranch"
    Add-Step "Current commit: $OriginalCommit"

    $FailureStage = 'external-backup'
    $Backup = New-ExternalBackup -Root $Repository
    Add-Step "Verified local backup: $Backup"

    $FailureStage = 'pre-migration-validation'
    $preflight = Test-MigrationSourceCredentials -EnvPath (Join-Path $Repository '.env')
    Add-Step ('Migration sources accepted: ' + (($preflight.Sources.Values | Sort-Object) -join ', '))

    $FailureStage = 'runtime-stop'
    Stop-TradysquidPython -Root $Repository

    $FailureStage = 'git-fetch'
    & git -C $Repository fetch origin `
        "+refs/heads/$CleanBranch`:refs/remotes/origin/$CleanBranch" `
        "+refs/heads/$ArchiveBranch`:refs/remotes/origin/$ArchiveBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }

    $archiveCommit = (& git -C $Repository rev-parse "refs/remotes/origin/$ArchiveBranch").Trim()
    if ($archiveCommit -ne $LegacyCommit) {
        throw "Archive branch mismatch. Expected $LegacyCommit but received $archiveCommit."
    }
    Add-Step "Archive branch verified at $archiveCommit"

    $CleanCommit = (& git -C $Repository rev-parse "refs/remotes/origin/$CleanBranch").Trim()
    if ($CleanCommit -ne $ExpectedCleanCommit) {
        throw "Clean branch mismatch. Expected $ExpectedCleanCommit but received $CleanCommit."
    }
    Add-Step "Tested clean commit verified: $CleanCommit"

    $FailureStage = 'branch-switch'
    & git -C $Repository switch --force-create $CleanBranch "origin/$CleanBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Could not switch to the clean-rebuild branch.' }
    $Switched = $true

    $FailureStage = 'environment-restore-before-migration'
    Restore-FileExact `
        -BackupPath (Join-Path $Backup 'installation\.env') `
        -DestinationPath (Join-Path $Repository '.env') | Out-Null
    Add-Step 'Original .env restored unchanged before migration.'

    $FailureStage = 'credential-migration'
    Push-Location $Repository
    try {
        & py -3.12 -m tradysquid.operations.credential_migration --root $Repository
        $migrationExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($migrationExitCode -ne 0) {
        throw "Credential migration failed with exit code $migrationExitCode."
    }

    $FailureStage = 'post-migration-validation'
    $canonical = Test-CanonicalCredentials -EnvPath (Join-Path $Repository '.env')
    Add-Step ('Canonical credentials validated: ' + (($canonical.CanonicalNames | Sort-Object) -join ', '))

    $FailureStage = 'clean-setup-process'
    $setupScript = Join-Path $Repository 'scripts\setup.ps1'
    $SetupProcess = Invoke-SetupProcess `
        -SetupScript $setupScript `
        -WorkingDirectory $Repository
    Add-Step "Setup process $($SetupProcess.ProcessId) exited with code $($SetupProcess.ExitCode)."

    $SetupReceipt = Read-SetupReceipt -Root $Repository
    if ($SetupProcess.ExitCode -ne 0) {
        throw "Clean setup exited with code $($SetupProcess.ExitCode)."
    }
    if ($null -eq $SetupReceipt) {
        throw 'Clean setup did not create a readable SETUP-RESULT.json.'
    }
    if ($SetupReceipt.status -ne 'PASS') {
        throw "Clean setup receipt reported $($SetupReceipt.status)."
    }

    $FailureStage = 'final-verification'
    $activeBranch = (& git -C $Repository branch --show-current).Trim()
    if ($activeBranch -ne $CleanBranch) {
        throw "Unexpected final branch: $activeBranch"
    }
    $Status = 'PASS'
    Add-Step 'Clean Tradysquid installation passed.'
} catch {
    $FailureReason = $_.Exception.Message
    Add-Step ("FAILED at $FailureStage`: $FailureReason")
    if ($Switched -and $Repository -and $Backup) {
        $RollbackResult = Restore-PreviousInstallation `
            -Root $Repository `
            -Branch $OriginalBranch `
            -BackupRoot $Backup
        $Status = if ($RollbackResult -eq 'PASS') { 'ROLLED BACK' } else { 'FAILED' }
    } else {
        $Status = 'FAILED'
    }
} finally {
    $finalBranch = $null
    if ($Repository) {
        try { $finalBranch = (& git -C $Repository branch --show-current).Trim() }
        catch { $finalBranch = $null }
    }

    $result = [ordered]@{
        status = $Status
        observed_at = (Get-Date).ToString('o')
        failed_stage = $FailureStage
        sanitized_error = $FailureReason
        repository = $Repository
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        expected_clean_commit = $ExpectedCleanCommit
        observed_clean_commit = $CleanCommit
        external_backup = $Backup
        inner_setup_process = $SetupProcess
        inner_setup_receipt_status = if ($SetupReceipt) { $SetupReceipt.status } else { $null }
        setup_log = if ($SetupReceipt) { $SetupReceipt.log } else { $null }
        rollback_result = $RollbackResult
        final_active_branch = $finalBranch
        secret_values_written = $false
        steps = @($Steps)
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content $ResultPath -Encoding UTF8

    Write-Host ''
    Write-Host "FINAL STATUS: $Status"
    if ($FailureStage) { Write-Host "Failed stage: $FailureStage" }
    if ($FailureReason) { Write-Host "Error: $FailureReason" }
    if ($SetupProcess) { Write-Host "Inner setup exit code: $($SetupProcess.ExitCode)" }
    if ($SetupReceipt -and $SetupReceipt.log) { Write-Host "Setup log: $($SetupReceipt.log)" }
    if ($Backup) { Write-Host "External backup: $Backup" }
    Write-Host "Rollback result: $RollbackResult"
    if ($finalBranch) { Write-Host "Final active branch: $finalBranch" }

    Stop-Transcript | Out-Null
}

if ($Status -ne 'PASS') { exit 1 }
