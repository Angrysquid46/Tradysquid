param(
    [string]$Repository = "C:\Users\strea\OneDrive\Desktop\Tradysquid-main",
    [string]$Bundle = (Join-Path $PSScriptRoot "tradysquid-offline-recovery.bundle")
)

$ErrorActionPreference = "Stop"
$TargetRef = "refs/remotes/offline-recovery/main"

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

$bundleCheck = & git bundle verify $Bundle 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Recovery bundle verification failed:`n$($bundleCheck -join "`n")"
}

$dirty = & git -C $Repository status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the repository working tree."
}
if ($dirty) {
    throw "Tracked files have local changes. Nothing was stopped or changed.`n$($dirty -join "`n")"
}

$before = Invoke-Git rev-parse HEAD
Write-Host "Current commit: $before"

& git -C $Repository update-ref -d $TargetRef 2>$null
$fetchOutput = & git -C $Repository fetch $Bundle "refs/remotes/origin/main:$TargetRef" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not import the offline bundle. Nothing was stopped.`n$($fetchOutput -join "`n")"
}
$target = Invoke-Git rev-parse $TargetRef
Write-Host "Bundle commit:  $target"

if ($before -eq $target) {
    Write-Host "The repository already contains the recovered version. Restarting services only."
    Start-Tradysquid
    exit 0
}

& git -C $Repository merge-base --is-ancestor $before $target
if ($LASTEXITCODE -ne 0) {
    throw "The recovery commit is not a fast-forward from the installed version. Nothing was stopped or changed."
}

$backupRef = "refs/heads/backup/offline-recovery-" + (Get-Date -Format "yyyyMMdd-HHmmss")
& git -C $Repository update-ref $backupRef $before
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the rollback reference. Nothing was stopped or changed."
}
Write-Host "Rollback reference: $backupRef"

Write-Host "Stopping Tradysquid only after bundle, ancestry, and rollback checks passed..."
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repository "stop_tradysquid_processes.ps1")

try {
    Invoke-Git merge --ff-only $target | Out-Host

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
    Write-Host "Validation failed. Rolling back to $before" -ForegroundColor Red
    & git -C $Repository reset --hard $before | Out-Host
    Start-Tradysquid
    throw
}

Write-Host "Code installed and compiled. Applying Discord structure..."
Push-Location $Repository
try {
    python run_with_env.py sync_discord_structure.py --apply
    $syncExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

Start-Tradysquid
Start-Sleep -Seconds 15

$installed = Invoke-Git rev-parse --short=12 HEAD
Write-Host "Installed commit: $installed" -ForegroundColor Green
Write-Host "Supervisor restarted."
if ($syncExit -ne 0) {
    Write-Warning "Discord structure sync did not finish, but the verified code remains installed and the supervisor will retry."
}
else {
    Write-Host "Discord structure synchronization completed." -ForegroundColor Green
}

Write-Host "Expected latest commit prefix: cfff04b5f64d"
