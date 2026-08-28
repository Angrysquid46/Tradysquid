<#
Watchdog for RIPTIDE (Codex's independent paper challenger), parallel to
ENSURE-SUPERVISOR.ps1 but separate from the main Tradysquid stack. RIPTIDE
owns a single-instance TCP lock port (127.0.0.1:8893). If nothing is
listening on it, RIPTIDE is relaunched hidden via start_riptide_hidden.vbs.
(which owns its own crash-restart loop; this watchdog only recovers from the
whole process tree being gone, e.g. after a reboot or the window being
closed).

BLACKTIDE (bots/blacktide, Codex-owned) is deliberately NOT managed here:
it already runs its own independent launch process (confirmed live,
2026-08-25, pre-dating this watchdog) with its own session/clean-start
semantics that belong to Codex's own operational choices, not this file's.
#>
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$StateDir = Join-Path $Root 'state'
$LogPath = Join-Path $StateDir 'competition-watchdog.log'

if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogPath -Value "$stamp | $Message" -Encoding UTF8
}

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

$bots = @(
    @{ Name = 'RIPTIDE'; Port = 8893; StopFlag = Join-Path $StateDir 'riptide-stop.flag'; Launcher = Join-Path $Root 'start_riptide_hidden.vbs' }
)

$unhealthy = @()
foreach ($bot in $bots) {
    if (Test-Path $bot.StopFlag) {
        if (-not $CheckOnly) { Write-WatchdogLog "$($bot.Name) stop flag present; skipping." }
        continue
    }
    if (Test-PortListening -Port $bot.Port) {
        if (-not $CheckOnly) { Write-WatchdogLog "$($bot.Name) healthy (port $($bot.Port) owned)." }
        continue
    }
    $unhealthy += $bot
}

if ($unhealthy.Count -eq 0) {
    exit 0
}
if ($CheckOnly) {
    exit 1
}

foreach ($bot in $unhealthy) {
    Write-WatchdogLog "$($bot.Name) not running (port $($bot.Port) free); relaunching hidden."
    Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $bot.Launcher + '"') -WindowStyle Hidden
}

Start-Sleep -Seconds 5
foreach ($bot in $unhealthy) {
    $ok = Test-PortListening -Port $bot.Port
    Write-WatchdogLog "$($bot.Name) post-relaunch check: $(if ($ok) { 'listening' } else { 'not yet listening (may still be starting)' })."
}
exit 0
