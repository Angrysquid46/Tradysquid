param(
    [string]$Repository = "C:\Users\strea\OneDrive\Desktop\Tradysquid-main",
    [string]$Bundle = (Join-Path $PSScriptRoot "tradysquid-final-release.bundle")
)

$ErrorActionPreference = 'Stop'
$TargetRef = 'refs/remotes/offline-recovery/main'
$BackupRoot = Join-Path $Repository 'state\offline-recovery-backup'
$Stopped = $false
$Before = ''

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git -C $Repository @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed:`n$($output -join "`n")"
    }
    return ($output -join "`n").Trim()
}

function Start-Tradysquid {
    Remove-Item (Join-Path $Repository 'state\supervisor-stop.flag') -ErrorAction SilentlyContinue
    Start-Process (Join-Path $Repository 'START-SUPERVISOR.cmd')
}

function Copy-RuntimeFile {
    param([string]$Relative)
    $source = Join-Path $Repository $Relative
    if (-not (Test-Path $source -PathType Leaf)) { return }
    $target = Join-Path $BackupRoot $Relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    if ((Get-Item $source).Length -ne (Get-Item $target).Length) {
        throw "Runtime backup verification failed for $Relative"
    }
}

function Restore-RuntimeFiles {
    param([string[]]$Paths)
    foreach ($relative in $Paths) {
        $source = Join-Path $BackupRoot $relative
        if (-not (Test-Path $source -PathType Leaf)) { continue }
        $target = Join-Path $Repository $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
}

Write-Host 'Tradysquid final offline deployment' -ForegroundColor Cyan
Write-Host "Repository: $Repository"
Write-Host "Bundle:     $Bundle"

if (-not (Test-Path (Join-Path $Repository '.git'))) {
    throw "Existing Tradysquid Git repository not found at $Repository"
}
if (-not (Test-Path $Bundle -PathType Leaf)) {
    throw "Recovery bundle not found at $Bundle"
}

# Git writes successful bundle verification details to stderr. cmd.exe prevents
# Windows PowerShell from converting that successful native output into a fatal
# NativeCommandError.
$verifyCommand = 'git -C "{0}" bundle verify "{1}" 2>&1' -f $Repository, $Bundle
$verifyOutput = & cmd.exe /d /s /c $verifyCommand
if ($LASTEXITCODE -ne 0) {
    throw "Bundle verification failed:`n$($verifyOutput -join "`n")"
}
Write-Host 'Bundle verification passed.' -ForegroundColor Green

$Before = Invoke-Git rev-parse HEAD
$branch = Invoke-Git rev-parse --abbrev-ref HEAD
if ($branch -ne 'main') {
    throw "Offline deployment requires the existing checkout to be on main, not $branch. Nothing was stopped."
}

& git -C $Repository update-ref -d $TargetRef 2>$null
$fetch = & git -C $Repository fetch $Bundle "refs/remotes/origin/main:$TargetRef" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Bundle import failed. Nothing was stopped or changed.`n$($fetch -join "`n")"
}
$Target = Invoke-Git rev-parse $TargetRef
Write-Host "Current commit: $Before"
Write-Host "Release commit: $Target"

& git -C $Repository merge-base --is-ancestor $Before $Target
if ($LASTEXITCODE -ne 0) {
    throw 'Release is not a safe fast-forward from the installed checkout. Nothing was stopped or changed.'
}

$statusLines = @(& git -C $Repository status --porcelain --untracked-files=no)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect tracked changes.' }
$runtimePaths = New-Object System.Collections.Generic.List[string]
$blockedPaths = New-Object System.Collections.Generic.List[string]
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) { continue }
    $relative = $line.Substring(3).Trim()
    if ($relative -match ' -> ') { $relative = ($relative -split ' -> ', 2)[1].Trim() }
    $normalized = $relative.Replace('\', '/')
    $runtime = (
        $normalized.StartsWith('state/') -or
        $normalized.StartsWith('docs/trade-snapshots/') -or
        $normalized.StartsWith('docs/tickers/') -or
        $normalized -in @(
            'config/scanner.json',
            'docs/index.html',
            'docs/ford-market-chart.svg',
            'docs/ford-market-chart.png'
        )
    )
    if ($runtime) { $runtimePaths.Add($relative) }
    else { $blockedPaths.Add($relative) }
}
if ($blockedPaths.Count -gt 0) {
    throw "Unexpected tracked source/config changes block deployment. Nothing was stopped:`n$($blockedPaths -join "`n")"
}

Remove-Item $BackupRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
foreach ($relative in $runtimePaths) { Copy-RuntimeFile $relative }
$rollbackRef = 'refs/heads/backup/offline-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& git -C $Repository update-ref $rollbackRef $Before
if ($LASTEXITCODE -ne 0) {
    throw 'Could not create the rollback reference. Nothing was stopped or changed.'
}
Write-Host "Rollback reference: $rollbackRef"

if ($Before -eq $Target) {
    Write-Host 'The release is already installed. Restarting the intended simple supervisor.' -ForegroundColor Yellow
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repository 'stop_tradysquid_processes.ps1')
    $Stopped = $true
    Start-Tradysquid
    Write-Host "Installed commit: $($Target.Substring(0,12))" -ForegroundColor Green
    exit 0
}

Write-Host 'Preflight passed. Stopping Tradysquid for the transaction...'
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repository 'stop_tradysquid_processes.ps1')
$Stopped = $true

try {
    if ($runtimePaths.Count -gt 0) {
        & git -C $Repository checkout -- @runtimePaths
        if ($LASTEXITCODE -ne 0) { throw 'Could not clean tracked runtime files for fast-forward.' }
    }

    & git -C $Repository merge --ff-only $Target
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward merge failed.' }

    Restore-RuntimeFiles -Paths @($runtimePaths)

    Push-Location $Repository
    try {
        python -c "import deployment_validation_manifest as m; print(m.validate_manifest())"
        if ($LASTEXITCODE -ne 0) { throw 'Deployment validation manifest failed.' }

        python -c "import subprocess,sys,deployment_validation_manifest as m; raise SystemExit(subprocess.run([sys.executable,'-m','py_compile',*m.COMPILE_MODULES]).returncode)"
        if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }

        python -c "import subprocess,sys,deployment_validation_manifest as m; raise SystemExit(subprocess.run([sys.executable,'-m','unittest','-q',*m.FOCUSED_TEST_MODULES]).returncode)"
        if ($LASTEXITCODE -ne 0) { throw 'Focused deployment tests failed.' }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "Validation failed. Rolling back to $Before" -ForegroundColor Red
    & git -C $Repository reset --hard $Before | Out-Host
    Restore-RuntimeFiles -Paths @($runtimePaths)
    Start-Tradysquid
    throw
}

Start-Tradysquid
Start-Sleep -Seconds 20
$installed = Invoke-Git rev-parse --short=12 HEAD
Write-Host "Installed commit: $installed" -ForegroundColor Green
Write-Host 'Supervisor restarted through START-SUPERVISOR.cmd.' -ForegroundColor Green
Write-Host 'Discord channels and live verification are runtime jobs and were not used as deployment gates.'

$diagnostics = Join-Path $Repository 'SUPERVISOR-DIAGNOSTICS.ps1'
if (Test-Path $diagnostics) {
    powershell -NoProfile -ExecutionPolicy Bypass -File $diagnostics
}

Remove-Item $BackupRoot -Recurse -Force -ErrorAction SilentlyContinue
