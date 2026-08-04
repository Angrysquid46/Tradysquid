param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit,

    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,

    [Parameter(Mandatory = $true)]
    [string]$CredentialHandoffPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$CredentialHandoffSha256
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
$Handoff = $null
$InstalledEnvironment = $null
$AttemptId = $null
$EvidencePath = $null
$InnerFailedStage = $null
$InnerFailureReason = $null
$SetupLog = $null
$Switched = $false
$RollbackResult = 'NOT REQUIRED'
$Steps = @()

function Add-Step {
    param([Parameter(Mandatory = $true)][string]$Message)

    $script:Steps += $Message
    Write-Host $Message
}

function Get-OptionalProperty {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$Default = $null
    )

    if ($null -eq $Object) {
        return $Default
    }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $Default
    }
    if ($null -eq $Property.Value) {
        return $Default
    }
    return $Property.Value
}

function Test-Administrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object System.Security.Principal.WindowsPrincipal($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-VerifiedRepository {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Resolved = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath (Join-Path $Resolved '.git'))) {
        throw 'Supplied repository path is not a Git working tree.'
    }

    $Remote = (& git -C $Resolved remote get-url origin 2>$null)
    if ($LASTEXITCODE -ne 0 -or $Remote -notmatch [regex]::Escape($ExpectedRemote)) {
        throw 'Supplied repository has an unexpected or unreadable Git remote.'
    }
    return $Resolved
}

function New-ExternalBackup {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Parent = Split-Path -Parent $Root
    $Destination = Join-Path $Parent ('Tradysquid-legacy-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $Installation = Join-Path $Destination 'installation'
    New-Item -ItemType Directory -Force -Path $Installation | Out-Null

    & git -C $Root status --porcelain=v1 -uall | Set-Content (Join-Path $Destination 'git-status.txt') -Encoding UTF8
    & git -C $Root diff | Set-Content (Join-Path $Destination 'tracked-working-tree.patch') -Encoding UTF8
    & git -C $Root diff --cached | Set-Content (Join-Path $Destination 'staged-working-tree.patch') -Encoding UTF8
    & git -C $Root branch --all --verbose | Set-Content (Join-Path $Destination 'git-branches.txt') -Encoding UTF8
    & git -C $Root log -1 --format=fuller | Set-Content (Join-Path $Destination 'git-head.txt') -Encoding UTF8

    $RobocopyArguments = @(
        $Root
        $Installation
        '/E'
        '/COPY:DAT'
        '/DCOPY:DAT'
        '/R:1'
        '/W:1'
        '/XJ'
        '/XD'
        '.git'
        '.venv'
        '.venv-tradysquid'
        '__pycache__'
        '.pytest_cache'
        '/XF'
        '*.pyc'
        '*.pyo'
    )
    & robocopy @RobocopyArguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Local backup failed with robocopy exit code $LASTEXITCODE."
    }

    $EnvBackup = Join-Path $Installation '.env'
    if (-not (Test-Path -LiteralPath $EnvBackup -PathType Leaf)) {
        throw 'The ignored .env was not preserved in the external backup.'
    }

    $EnvHash = Get-VerifiedFileHash -Path $EnvBackup
    [ordered]@{
        status = 'PASS'
        observed_at = (Get-Date).ToString('o')
        repository = $Root
        installation = $Installation
        env_backup = $EnvBackup
        env_sha256 = $EnvHash
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Destination 'backup-receipt.json') -Encoding UTF8
    return $Destination
}

function Stop-TradysquidPython {
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

function Restore-PreviousInstallation {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Branch,
        [Parameter(Mandatory = $true)][string]$BackupRoot
    )

    try {
        & git -C $Root switch --force $Branch
        if ($LASTEXITCODE -ne 0) {
            & git -C $Root switch --force main
            if ($LASTEXITCODE -ne 0) {
                throw 'Could not restore the previous Git branch.'
            }
        }

        $EnvBackup = Join-Path $BackupRoot 'installation\.env'
        $RestoredHash = Restore-FileExact -BackupPath $EnvBackup -DestinationPath (Join-Path $Root '.env')
        Add-Step "Original .env restored with SHA-256 $RestoredHash"

        $LegacyStart = Join-Path $Root 'START-SUPERVISOR.cmd'
        if (Test-Path -LiteralPath $LegacyStart -PathType Leaf) {
            Start-Process -FilePath $LegacyStart -WorkingDirectory $Root | Out-Null
        }
        return 'PASS'
    } catch {
        Add-Step ('Rollback error: ' + $_.Exception.Message)
        return 'FAILED'
    }
}

if (-not (Test-Administrator)) {
    $ElevationArguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"' + $ScriptPath + '"')
        '-ExpectedCleanCommit'
        $ExpectedCleanCommit
        '-RepositoryPath'
        ('"' + $RepositoryPath + '"')
        '-CredentialHandoffPath'
        ('"' + $CredentialHandoffPath + '"')
        '-CredentialHandoffSha256'
        $CredentialHandoffSha256
    )
    $ElevationParameters = @{
        FilePath = 'powershell.exe'
        ArgumentList = $ElevationArguments
        Verb = 'RunAs'
        Wait = $true
        PassThru = $true
    }
    $Elevated = Start-Process @ElevationParameters
    exit $Elevated.ExitCode
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

    $FailureStage = 'repository-verification'
    $Repository = Resolve-VerifiedRepository -Root $RepositoryPath
    Add-Step "Repository path received and verified: $Repository"

    $OriginalBranch = (& git -C $Repository branch --show-current).Trim()
    $OriginalCommit = (& git -C $Repository rev-parse HEAD).Trim()
    if (-not $OriginalBranch) {
        $OriginalBranch = 'main'
    }
    Add-Step "Current branch: $OriginalBranch"
    Add-Step "Current commit: $OriginalCommit"

    $FailureStage = 'credential-handoff-verification'
    $Handoff = Read-CanonicalCredentialHandoff -RepositoryPath $Repository -HandoffPath $CredentialHandoffPath -ExpectedSha256 $CredentialHandoffSha256
    Add-Step "Credential handoff path received: $($Handoff.HandoffPath)"
    Add-Step "Credential handoff SHA-256 verified: $($Handoff.Sha256)"
    Add-Step "Five canonical credential names verified: $($Handoff.CanonicalNameCount)"

    $FailureStage = 'external-backup'
    $Backup = New-ExternalBackup -Root $Repository
    Add-Step "Verified local backup: $Backup"

    $FailureStage = 'runtime-stop'
    Stop-TradysquidPython -Root $Repository

    $FailureStage = 'untracked-conflict-cleanup'
    # Extracting a replacement archive over an older branch can leave files
    # that are tracked by clean-rebuild but untracked by the current branch.
    # Git correctly refuses to overwrite them. The complete installation has
    # already been copied to the external backup, so archive the exact list and
    # remove only untracked, non-ignored paths. Ignored private/runtime paths
    # such as .env, data, state, logs, and virtual environments are untouched.
    $UntrackedPaths = @(& git -C $Repository ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inventory untracked checkout conflicts.'
    }
    $UntrackedManifest = Join-Path $Backup 'untracked-paths-before-clean.txt'
    $UntrackedPaths | Set-Content -LiteralPath $UntrackedManifest -Encoding UTF8
    if ($UntrackedPaths.Count -gt 0) {
        Add-Step "Archiving and removing $($UntrackedPaths.Count) untracked checkout conflicts."
        & git -C $Repository clean -fd
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not remove archived untracked checkout conflicts.'
        }
    }

    $FailureStage = 'git-fetch'
    $FetchArguments = @(
        '-C'
        $Repository
        'fetch'
        'origin'
        "+refs/heads/$CleanBranch`:refs/remotes/origin/$CleanBranch"
        "+refs/heads/$ArchiveBranch`:refs/remotes/origin/$ArchiveBranch"
    )
    & git @FetchArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Git fetch failed.'
    }

    $ArchiveCommit = (& git -C $Repository rev-parse "refs/remotes/origin/$ArchiveBranch").Trim()
    if ($ArchiveCommit -ne $LegacyCommit) {
        throw "Archive branch mismatch. Expected $LegacyCommit but received $ArchiveCommit."
    }
    Add-Step "Archive branch verified at $ArchiveCommit"

    $CleanCommit = (& git -C $Repository rev-parse "refs/remotes/origin/$CleanBranch").Trim()
    if ($CleanCommit -ne $ExpectedCleanCommit) {
        throw "Clean branch mismatch. Expected $ExpectedCleanCommit but received $CleanCommit."
    }
    Add-Step "Tested clean commit verified: $CleanCommit"

    $FailureStage = 'branch-switch'
    & git -C $Repository switch --force-create $CleanBranch "origin/$CleanBranch"
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not switch to the clean-rebuild branch.'
    }
    $Switched = $true
    Add-Step 'Switched to clean-rebuild.'

    $FailureStage = 'canonical-env-installation'
    $InstalledEnvironment = Install-CanonicalCredentialHandoff -Handoff $Handoff -DestinationPath (Join-Path $Repository '.env')
    Add-Step "Canonical environment installed: $($InstalledEnvironment.DestinationPath)"
    Add-Step "Canonical environment reread passed: $($InstalledEnvironment.CanonicalNameCount) names"
    Add-Step 'Canonical source and destination hashes match.'

    $FailureStage = 'setup-script-parse-validation'
    $SetupEntryScript = Join-Path $Repository 'scripts\setup_entry.ps1'
    $SetupBodyScript = Join-Path $Repository 'scripts\setup.ps1'
    Test-PowerShellScriptSyntax -Path $SetupEntryScript | Out-Null
    Test-PowerShellScriptSyntax -Path $SetupBodyScript | Out-Null
    Add-Step 'PowerShell setup scripts parsed successfully.'

    $FailureStage = 'clean-setup-process'
    $AttemptId = [guid]::NewGuid().ToString()
    Add-Step "Starting setup attempt $AttemptId"
    $SetupProcess = Invoke-SetupProcess -SetupEntryScript $SetupEntryScript -SetupBodyScript $SetupBodyScript -WorkingDirectory $Repository -AttemptId $AttemptId -ExpectedCleanCommit $ExpectedCleanCommit
    Add-Step "Setup process $(Get-OptionalProperty $SetupProcess 'ProcessId' 'not available') exited with code $(Get-OptionalProperty $SetupProcess 'ExitCode' 1)."

    $ProcessStartedAt = Get-OptionalProperty $SetupProcess 'StartedAt' (Get-Date)
    $SetupReceipt = Read-CurrentSetupReceipt -Root $Repository -AttemptId $AttemptId -ProcessStartedAt ([datetime]$ProcessStartedAt) -ExpectedRepositoryPath $Repository -ExpectedCleanCommit $ExpectedCleanCommit
    if ($SetupReceipt) {
        $InnerFailedStage = [string](Get-OptionalProperty $SetupReceipt 'failed_stage' 'not available')
        $InnerFailureReason = [string](Get-OptionalProperty $SetupReceipt 'error' 'not available')
        $SetupLog = Get-OptionalProperty $SetupReceipt 'log' $null
    } else {
        $TimedOutStage = Get-OptionalProperty $SetupProcess 'TimedOutStage' $null
        if ($TimedOutStage) {
            $InnerFailedStage = [string]$TimedOutStage
            $InnerFailureReason = "Setup stage exceeded its timeout: $TimedOutStage"
        } else {
            $InnerFailedStage = 'setup-process-before-receipt'
            $InnerFailureReason = 'Current setup receipt is missing or invalid for the current attempt.'
        }
    }

    $SetupExitCode = [int](Get-OptionalProperty $SetupProcess 'ExitCode' 1)
    if ($SetupExitCode -ne 0) {
        throw "Inner setup failed at $InnerFailedStage`: $InnerFailureReason"
    }
    if ($null -eq $SetupReceipt) {
        throw 'Current setup receipt is missing or invalid for the current attempt.'
    }
    $ReceiptStatus = [string](Get-OptionalProperty $SetupReceipt 'status' 'FAILED')
    if ($ReceiptStatus -ne 'PASS') {
        throw "Clean setup receipt reported $ReceiptStatus."
    }

    $FailureStage = 'final-verification'
    $ActiveBranch = (& git -C $Repository branch --show-current).Trim()
    if ($ActiveBranch -ne $CleanBranch) {
        throw "Unexpected final branch: $ActiveBranch"
    }

    $Status = 'PASS'
    Add-Step 'Clean Tradysquid installation passed.'
} catch {
    $FailureReason = [string]$_.Exception.Message
    Add-Step ("FAILED at $FailureStage`: $FailureReason")

    if ($Switched -and $Repository -and $Backup) {
        if ($AttemptId) {
            try {
                $EvidencePath = Copy-SanitizedSetupEvidence -Root $Repository -BackupRoot $Backup -AttemptId $AttemptId -ExpectedCleanCommit $ExpectedCleanCommit
                Add-Step "Current-attempt failure evidence preserved: $EvidencePath"
            } catch {
                Add-Step ('Failure-evidence preservation error: ' + $_.Exception.Message)
            }
        }

        $RollbackResult = Restore-PreviousInstallation -Root $Repository -Branch $OriginalBranch -BackupRoot $Backup
        if ($RollbackResult -eq 'PASS') {
            $Status = 'ROLLED BACK'
        } else {
            $Status = 'FAILED'
        }
    } else {
        $Status = 'FAILED'
    }
} finally {
    $FinalBranch = $null
    if ($Repository) {
        try {
            $FinalBranch = (& git -C $Repository branch --show-current).Trim()
        } catch {
            $FinalBranch = $null
        }
    }

    $CanonicalNames = @()
    if ($Handoff) {
        $RawNames = Get-OptionalProperty $Handoff 'CanonicalNames' @()
        foreach ($Name in $RawNames) {
            $CanonicalNames += [string]$Name
        }
    }

    $SetupReceiptStatus = if ($SetupReceipt) {
        Get-OptionalProperty $SetupReceipt 'status' $null
    } else {
        $null
    }
    if (-not $SetupLog -and $SetupReceipt) {
        $SetupLog = Get-OptionalProperty $SetupReceipt 'log' $null
    }

    $Result = [ordered]@{
        status = $Status
        observed_at = (Get-Date).ToString('o')
        outer_failed_stage = $FailureStage
        inner_failed_stage = $InnerFailedStage
        sanitized_error = $FailureReason
        inner_error = $InnerFailureReason
        attempt_id = $AttemptId
        repository_path = $Repository
        requested_repository_path = $RepositoryPath
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        expected_clean_commit = $ExpectedCleanCommit
        observed_clean_commit = $CleanCommit
        credential_handoff_path = if ($Handoff) { Get-OptionalProperty $Handoff 'HandoffPath' $CredentialHandoffPath } else { $CredentialHandoffPath }
        credential_handoff_sha256_verified = ($null -ne $Handoff)
        canonical_names_present = $CanonicalNames
        canonical_name_count = $CanonicalNames.Count
        destination_env_path = if ($InstalledEnvironment) { Get-OptionalProperty $InstalledEnvironment 'DestinationPath' $null } else { $null }
        source_destination_hashes_match = if ($InstalledEnvironment) {
            (Get-OptionalProperty $InstalledEnvironment 'SourceSha256' '') -eq (Get-OptionalProperty $InstalledEnvironment 'DestinationSha256' 'mismatch')
        } else {
            $false
        }
        external_backup = $Backup
        failure_evidence = $EvidencePath
        inner_setup_process = $SetupProcess
        inner_setup_receipt_status = $SetupReceiptStatus
        setup_receipt = if ($Repository) { Join-Path $Repository 'SETUP-RESULT.json' } else { $null }
        setup_log = $SetupLog
        child_stdout = if ($SetupProcess) { Get-OptionalProperty $SetupProcess 'StdoutPath' $null } else { $null }
        child_stderr = if ($SetupProcess) { Get-OptionalProperty $SetupProcess 'StderrPath' $null } else { $null }
        rollback_result = $RollbackResult
        final_active_branch = $FinalBranch
        secret_values_written = $false
        steps = $Steps
    }
    $Result | ConvertTo-Json -Depth 10 | Set-Content $ResultPath -Encoding UTF8

    Write-Host ''
    Write-Host "FINAL STATUS: $Status"
    if ($FailureStage) {
        Write-Host "Outer failed stage: $FailureStage"
    }
    if ($InnerFailedStage) {
        Write-Host "Inner failed stage: $InnerFailedStage"
    }
    if ($InnerFailureReason) {
        Write-Host "Inner error: $InnerFailureReason"
    } elseif ($FailureReason) {
        Write-Host "Error: $FailureReason"
    }
    if ($SetupProcess) {
        Write-Host "Inner process exit code: $(Get-OptionalProperty $SetupProcess 'ExitCode' 'not available')"
        Write-Host "Child stdout: $(Get-OptionalProperty $SetupProcess 'StdoutPath' 'not available')"
        Write-Host "Child stderr: $(Get-OptionalProperty $SetupProcess 'StderrPath' 'not available')"
    }
    if ($AttemptId) {
        Write-Host "Attempt ID: $AttemptId"
    }
    if ($Repository) {
        Write-Host "Setup receipt: $(Join-Path $Repository 'SETUP-RESULT.json')"
    }
    if ($SetupLog) {
        Write-Host "Setup log: $SetupLog"
    } else {
        Write-Host 'Setup log: not available'
    }
    if ($Backup) {
        Write-Host "External backup: $Backup"
    }
    if ($EvidencePath) {
        Write-Host "Failure evidence: $EvidencePath"
    }
    Write-Host "Rollback result: $RollbackResult"
    if ($FinalBranch) {
        Write-Host "Final branch: $FinalBranch"
    }

    Stop-Transcript | Out-Null
}

if ($Status -ne 'PASS') {
    exit 1
}
