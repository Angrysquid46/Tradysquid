param(
    [string]$Repository = "C:\Users\strea\OneDrive\Desktop\Tradysquid-main",
    [string]$Bundle = (Join-Path $PSScriptRoot "tradysquid-offline-recovery.bundle")
)

$ErrorActionPreference = "Stop"
$TargetRef = "refs/remotes/offline-recovery/main"
$ExpectedCommitPrefix = "767d27045b59"
$RuntimePaths = @(
    "state/discord-report-state.json",
    "state/ford-plays-log.csv"
)
$Stopped = $false
$Before = ""
$BackupDirectory = ""

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git -C $Repository @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed:`n$($output -join "`n")"
    }
    return ($output -join "`n").Trim()
}

function Start-Tradysquid {
    Remove-Item (Join-Path $Repository "state\supervisor-stop.flag") -ErrorAction SilentlyContinue
    Start-Process (Join-Path $Repository "START-SUPERVISOR.cmd")
}

function Get-TrackedChanges {
    $lines = & git -C $Repository status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect tracked repository changes."
    }
    return @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-ChangedPath([string]$StatusLine) {
    if ($StatusLine.Length -lt 4) { return "" }
    $path = $StatusLine.Substring(3).Trim()
    if ($path -match " -> ") {
        $path = ($path -split " -> ")[-1]
    }
    return $path.Replace("\", "/")
}

function Assert-OnlyRuntimeChanges {
    $changes = Get-TrackedChanges
    $unexpected = @()
    foreach ($line in $changes) {
        $path = Get-ChangedPath $line
        if ($RuntimePaths -notcontains $path) {
            $unexpected += $line
        }
    }
    if ($unexpected.Count -gt 0) {
        throw "Unexpected tracked changes were found. Nothing was changed:`n$($unexpected -join "`n")"
    }
    return $changes
}

function Backup-RuntimeState {
    $script:BackupDirectory = Join-Path $Repository ("state\offline-recovery-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
    foreach ($relative in $RuntimePaths) {
        $source = Join-Path $Repository $relative
        if (Test-Path $source) {
            $destination = Join-Path $BackupDirectory ([IO.Path]::GetFileName($relative))
            Copy-Item $source $destination -Force
        }
    }
    Write-Host "Runtime backup: $BackupDirectory"
}

function Restore-RuntimeState {
    if (-not $BackupDirectory -or -not (Test-Path $BackupDirectory)) { return }
    foreach ($relative in $RuntimePaths) {
        $source = Join-Path $BackupDirectory ([IO.Path]::GetFileName($relative))
        if (Test-Path $source) {
            $destination = Join-Path $Repository $relative
            New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
            Copy-Item $source $destination -Force
        }
    }
}

Write-Host "Tradysquid offline recovery" -ForegroundColor Cyan
Write-Host "Repository: $Repository"
Write-Host "Bundle:     $Bundle"

if (-not (Test-Path $Repository)) {
    throw "Repository folder does not exist: $Repository"
}
if (-not (Test-Path (Join-Path $Repository ".git"))) {
    throw "The target is not the existing Git repository: $Repository"
}
if (-not (Test-Path $Bundle)) {
    throw "Recovery bundle is missing: $Bundle"
}

$verifyCommand = 'git -C "{0}" bundle verify "{1}" 2>&1' -f $Repository, $Bundle
$bundleCheck = & cmd.exe /d /s /c $verifyCommand
if ($LASTEXITCODE -ne 0) {
    throw "Recovery bundle verification failed:`n$($bundleCheck -join "`n")"
}
Write-Host "Bundle verification passed."

Assert-OnlyRuntimeChanges | Out-Null
$Before = Invoke-Git rev-parse HEAD
Write-Host "Current commit: $Before"

& git -C $Repository update-ref -d $TargetRef 2>$null
$fetchOutput = & git -C $Repository fetch $Bundle "refs/remotes/origin/main:$TargetRef" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not import the offline bundle. Nothing was stopped:`n$($fetchOutput -join "`n")"
}
$Target = Invoke-Git rev-parse $TargetRef
Write-Host "Bundle commit:  $Target"
if (-not $Target.StartsWith($ExpectedCommitPrefix)) {
    throw "Bundle commit $Target does not match expected release $ExpectedCommitPrefix."
}

if ($Before -eq $Target) {
    Write-Host "The recovered version is already installed. Restarting Tradysquid."
    Start-Tradysquid
    exit 0
}

& git -C $Repository merge-base --is-ancestor $Before $Target
if ($LASTEXITCODE -ne 0) {
    throw "The recovery commit is not a fast-forward from the installed version. Nothing was stopped or changed."
}

$RollbackRef = "refs/heads/backup/offline-recovery-" + (Get-Date -Format "yyyyMMdd-HHmmss")
& git -C $Repository update-ref $RollbackRef $Before
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the rollback reference. Nothing was stopped or changed."
}
Write-Host "Rollback reference: $RollbackRef"

try {
    Write-Host "Stopping Tradysquid after all preflight checks passed..."
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repository "stop_tradysquid_processes.ps1")
    $Stopped = $true

    Assert-OnlyRuntimeChanges | Out-Null
    Backup-RuntimeState

    foreach ($relative in $RuntimePaths) {
        & git -C $Repository restore --source=HEAD -- $relative 2>$null
    }

    $remaining = Get-TrackedChanges
    if ($remaining.Count -gt 0) {
        throw "Tracked files remained modified after preserving runtime state:`n$($remaining -join "`n")"
    }

    Invoke-Git merge --ff-only $Target | Out-Host
    Restore-RuntimeState

    Push-Location $Repository
    try {
        python -m py_compile `
            network_compat.py `
            applied_upgrades.py `
            run_with_env.py `
            run_supervisor_resilient.py `
            local_information_engine_bootstrap.py `
            sync_discord_structure_reports.py
        if ($LASTEXITCODE -ne 0) {
            throw "Python compile validation failed."
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    if ($Stopped -and $Before) {
        Write-Host "Installation failed. Rolling back to $Before" -ForegroundColor Red
        & git -C $Repository reset --hard $Before | Out-Host
        Restore-RuntimeState
        Start-Tradysquid
    }
    throw
}

Write-Host "Code installed and runtime data restored. Applying Discord structure..."
Push-Location $Repository
try {
    python run_with_env.py sync_discord_structure.py --apply
    $SyncExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

Start-Tradysquid
Start-Sleep -Seconds 15

$Installed = Invoke-Git rev-parse --short=12 HEAD
Write-Host "Installed commit: $Installed" -ForegroundColor Green
Write-Host "Supervisor restarted."
if ($SyncExit -ne 0) {
    Write-Warning "Discord structure sync did not finish, but the verified code is installed and the supervisor will retry."
}
else {
    Write-Host "Discord structure synchronization completed." -ForegroundColor Green
}

$finalChanges = Get-TrackedChanges
if ($finalChanges.Count -gt 0) {
    Write-Warning "Unexpected tracked changes remain:`n$($finalChanges -join "`n")"
}
else {
    Write-Host "Repository tracked files are clean; runtime files are preserved and ignored." -ForegroundColor Green
}
