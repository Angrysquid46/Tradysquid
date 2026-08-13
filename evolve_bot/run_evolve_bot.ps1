# Invoked by the "Tradysquid Evolve Bot Trading Loop" scheduled task
# (every 3 minutes, weekdays, market hours) - runs one engine.run_cycle()
# using the isolated .venv-evolve interpreter. This is what actually
# turns the bot "on": Phases 1-12 built everything this calls, but
# nothing ever invoked it on a real cadence before this task existed -
# found 2026-08-12 when the live tradelog turned out to have exactly 2
# rows, both from manual verification runs during the build, never a
# real automated trade.
#
# run_cycle() is cheap outside market hours (checks market_is_open_now()
# and returns immediately), so firing a few minutes outside the
# configured window is harmless, not something this script needs to
# guard against itself.
#
# Fully separate from the live Tradysquid supervisor (frozen per
# CLAUDE.md) - this only ever touches evolve_bot's own isolated state.

$ErrorActionPreference = "Continue"
Set-Location "C:\Tradysquid\evolve_bot"

$logPath = "C:\Tradysquid\evolve_bot\state\trading_loop_log.txt"
$logDir = Split-Path $logPath -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$result = & "..\.venv-evolve\Scripts\python.exe" "engine.py" 2>&1
Add-Content -Path $logPath -Value "[$timestamp] $result"
