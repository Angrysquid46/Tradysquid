[CmdletBinding()]
param(
    [string]$RepositoryPath = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedCleanCommit = '294003f50073dbd072fd3a782519afc620791915'
$ExpectedArchiveCommit = 'ba75aae5f34f3889404bfe0c7c0b96663a92a657'
$CleanBranch = 'clean-rebuild'
$ArchiveBranch = 'archive/current-failed-implementation'
$FinalStatus = 'FAILED'
$FinalExitCode = 1
$Repository = $null
$Worktree = $null

function Invoke-GitSafe {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingRepository,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$FailureMessage = 'Git command failed.'
    )

    $PreviousPreference = $ErrorActionPreference
    $Output = @()
    $ExitCode = 1
    try {
        $ErrorActionPreference = 'Continue'
        $Output = @(& git -C $WorkingRepository @Arguments 2>&1)
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }

    if ($ExitCode -ne 0) {
        $Details = ($Output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        if ([string]::IsNullOrWhiteSpace($Details)) {
            $Details = "git exit code $ExitCode"
        }
        throw "$FailureMessage $Details"
    }

    return $Output
}

function Read-JsonSafe {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Archive-PreviousAttemptArtifacts {
    param([Parameter(Mandatory = $true)][string]$Root)

    $ArchiveRoot = Join-Path $Root ('state\manual-install-archive-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null

    foreach ($RelativePath in @(
        'state\clean-rebuild-auto-launch.json',
        'state\clean-rebuild-auto-handoff.json',
        'state\clean-rebuild-auto-launch.stdout.log',
        'state\clean-rebuild-auto-launch.stderr.log',
        'state\setup-stage-state.json',
        'state\setup-heartbeat.json',
        'state\setup-entry-exit-code.txt',
        'SETUP-RESULT.json',
        'SETUP-RESULT.txt'
    )) {
        $Source = Join-Path $Root $RelativePath
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
            continue
        }
        $Destination = Join-Path $ArchiveRoot ([IO.Path]::GetFileName($Source))
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
    }

    return $ArchiveRoot
}

function Remove-TemporaryWorktreeBestEffort {
    param(
        [string]$Root,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Root) -or [string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & git -C $Root worktree remove --force $Path *> $null
        if (Test-Path -LiteralPath $Path) {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        }
        & git -C $Root worktree prune *> $null
    } catch {
        # Cleanup must never replace the real installation result.
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
}

try {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open Windows PowerShell as Administrator before running this installer.'
    }

    $Repository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.git'))) {
        throw "Tradysquid Git repository was not found at $Repository"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.env') -PathType Leaf)) {
        throw "The required local .env file is missing from $Repository"
    }

    Set-Location $Repository
    New-Item -ItemType Directory -Force -Path (Join-Path $Repository 'state') | Out-Null

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host 'TRADYSQUID AUDITED FOREGROUND INSTALLER' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host "Repository: $Repository"
    Write-Host "Target clean commit: $ExpectedCleanCommit"
    Write-Host 'This window will remain attached to the real installer.' -ForegroundColor Yellow
    Write-Host ''

    Write-Host 'Fetching the exact audited branches...' -ForegroundColor Cyan
    Invoke-GitSafe -WorkingRepository $Repository -Arguments @(
        'fetch',
        'origin',
        "+refs/heads/$CleanBranch`:refs/remotes/origin/$CleanBranch",
        "+refs/heads/$ArchiveBranch`:refs/remotes/origin/$ArchiveBranch"
    ) -FailureMessage 'Could not fetch the audited clean and archive branches.' | Out-Null

    $ObservedClean = ((Invoke-GitSafe -WorkingRepository $Repository -Arguments @(
        'rev-parse', "refs/remotes/origin/$CleanBranch"
    ) -FailureMessage 'Could not read the clean branch commit.') -join '').Trim()
    if ($ObservedClean -ne $ExpectedCleanCommit) {
        throw "Clean branch mismatch. Expected $ExpectedCleanCommit but received $ObservedClean"
    }

    $ObservedArchive = ((Invoke-GitSafe -WorkingRepository $Repository -Arguments @(
        'rev-parse', "refs/remotes/origin/$ArchiveBranch"
    ) -FailureMessage 'Could not read the archive branch commit.') -join '').Trim()
    if ($ObservedArchive -ne $ExpectedArchiveCommit) {
        throw "Archive branch mismatch. Expected $ExpectedArchiveCommit but received $ObservedArchive"
    }

    $PreviousArchive = Archive-PreviousAttemptArtifacts -Root $Repository
    Write-Host "Previous attempt receipts archived at: $PreviousArchive" -ForegroundColor DarkGray

    Remove-Item -LiteralPath (Join-Path $Repository 'state\supervisor-stop.flag') -Force -ErrorAction SilentlyContinue

    Invoke-GitSafe -WorkingRepository $Repository -Arguments @('worktree', 'prune') `
        -FailureMessage 'Could not prune stale Git worktree registrations.' | Out-Null

    $Parent = Split-Path -Parent $Repository
    $UniqueSuffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $WorktreeName = 'Tradysquid-clean-handoff-{0}-{1}-{2}' -f `
        $ExpectedCleanCommit.Substring(0, 12), $Timestamp, $UniqueSuffix
    $Worktree = Join-Path $Parent $WorktreeName

    Write-Host "Creating isolated installer worktree: $Worktree" -ForegroundColor DarkGray
    Invoke-GitSafe -WorkingRepository $Repository -Arguments @(
        'worktree', 'add', '--detach', $Worktree, $ExpectedCleanCommit
    ) -FailureMessage 'Could not create the exact audited clean installer worktree.' | Out-Null

    $Installer = Join-Path $Worktree 'scripts\auto_install_clean_rebuild.ps1'
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
        throw "The audited installer script was not found at $Installer"
    }

    $ManualLaunchReceipt = Join-Path $Repository 'state\manual-clean-install-launch.json'
    [ordered]@{
        status = 'RUNNING'
        started_at = (Get-Date).ToString('o')
        expected_clean_commit = $ExpectedCleanCommit
        repository_path = $Repository
        worktree_path = $Worktree
        installer_path = $Installer
        foreground = $true
        secret_values_written = $false
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManualLaunchReceipt -Encoding UTF8

    Write-Host ''
    Write-Host 'Starting the real clean installer now...' -ForegroundColor Green
    Write-Host 'Do not launch another installer or supervisor while this runs.' -ForegroundColor Yellow
    Write-Host ''

    $InstallerArguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $Installer + '"'),
        '-ExpectedCleanCommit', $ExpectedCleanCommit,
        '-RepositoryPath', ('"' + $Repository + '"')
    )
    $InstallerProcess = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList $InstallerArguments `
        -WorkingDirectory $Worktree `
        -NoNewWindow `
        -Wait `
        -PassThru
    $InstallerExitCode = [int]$InstallerProcess.ExitCode

    $FinalReceiptPath = Join-Path $Repository 'state\clean-rebuild-auto-handoff.json'
    $SetupReceiptPath = Join-Path $Repository 'SETUP-RESULT.json'
    $FinalReceipt = Read-JsonSafe -Path $FinalReceiptPath
    $SetupReceipt = Read-JsonSafe -Path $SetupReceiptPath

    if ($InstallerExitCode -ne 0) {
        $ReceiptStatus = if ($FinalReceipt) { [string]$FinalReceipt.status } else { 'NO FINAL RECEIPT' }
        $ReceiptStage = if ($FinalReceipt) { [string]$FinalReceipt.failed_stage } else { 'unknown' }
        $ReceiptError = if ($FinalReceipt) { [string]$FinalReceipt.error } else { 'The installer exited before producing a final receipt.' }
        throw "Installer exit code $InstallerExitCode. Status: $ReceiptStatus. Stage: $ReceiptStage. Error: $ReceiptError"
    }

    if (-not $FinalReceipt) {
        throw 'The installer exited successfully but did not produce a final handoff receipt.'
    }
    if ([string]$FinalReceipt.expected_clean_commit -ne $ExpectedCleanCommit) {
        throw 'The final handoff receipt belongs to a different clean commit.'
    }
    if (([string]$FinalReceipt.status).Trim().ToUpper() -ne 'PASS') {
        throw "The final handoff receipt did not say PASS. Status: $($FinalReceipt.status)"
    }

    if (-not $SetupReceipt) {
        throw 'The clean setup did not produce SETUP-RESULT.json.'
    }
    if (
        [string]$SetupReceipt.setup_commit -ne $ExpectedCleanCommit -and
        [string]$SetupReceipt.expected_clean_commit -ne $ExpectedCleanCommit
    ) {
        throw 'SETUP-RESULT.json belongs to a different clean commit.'
    }
    if (([string]$SetupReceipt.status).Trim().ToUpper() -ne 'PASS') {
        throw "SETUP-RESULT.json did not say PASS. Status: $($SetupReceipt.status)"
    }

    $FinalStatus = 'PASS'
    $FinalExitCode = 0
    [ordered]@{
        status = 'PASS'
        finished_at = (Get-Date).ToString('o')
        expected_clean_commit = $ExpectedCleanCommit
        installer_exit_code = $InstallerExitCode
        final_receipt = $FinalReceiptPath
        setup_receipt = $SetupReceiptPath
        secret_values_written = $false
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManualLaunchReceipt -Encoding UTF8

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host 'TRADYSQUID INSTALLATION PASSED' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host "Installed clean commit: $ExpectedCleanCommit"
    Write-Host "Final receipt: $FinalReceiptPath"
    Write-Host "Setup receipt: $SetupReceiptPath"
} catch {
    $FailureMessage = [string]$_.Exception.Message
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host 'TRADYSQUID INSTALLATION DID NOT PASS' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $FailureMessage -ForegroundColor Red

    if ($Repository) {
        $FinalReceiptPath = Join-Path $Repository 'state\clean-rebuild-auto-handoff.json'
        $SetupReceiptPath = Join-Path $Repository 'SETUP-RESULT.json'
        $FinalReceipt = Read-JsonSafe -Path $FinalReceiptPath
        $SetupReceipt = Read-JsonSafe -Path $SetupReceiptPath

        if ($FinalReceipt) {
            Write-Host ''
            Write-Host '=== FINAL HANDOFF RECEIPT ===' -ForegroundColor Cyan
            $FinalReceipt | ConvertTo-Json -Depth 12
        }
        if ($SetupReceipt) {
            Write-Host ''
            Write-Host '=== SETUP RECEIPT ===' -ForegroundColor Cyan
            $SetupReceipt | ConvertTo-Json -Depth 15
        }

        $NewestBackup = Get-ChildItem -LiteralPath (Split-Path -Parent $Repository) -Directory -Filter 'Tradysquid-auto-handoff-*' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($NewestBackup) {
            Write-Host ''
            Write-Host "Newest external backup: $($NewestBackup.FullName)" -ForegroundColor Yellow
            foreach ($LogName in @('setup-entry-stderr.log', 'setup-entry-stdout.log')) {
                $LogPath = Join-Path $NewestBackup.FullName $LogName
                if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
                    Write-Host "=== $LogName ===" -ForegroundColor Cyan
                    Get-Content -LiteralPath $LogPath -Tail 100
                }
            }
        }
    }
} finally {
    Remove-TemporaryWorktreeBestEffort -Root $Repository -Path $Worktree
    Write-Host ''
    $StatusColor = if ($FinalStatus -eq 'PASS') { 'Green' } else { 'Red' }
    Write-Host "Final foreground installer status: $FinalStatus" -ForegroundColor $StatusColor
    Read-Host 'Press Enter after copying or photographing this result'
}

exit $FinalExitCode
