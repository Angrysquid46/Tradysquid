# Invoked by the "Tradysquid Market Memory Collection" scheduled task
# (daily, weekdays, 3:35pm CT - 5 minutes after market close and 5
# minutes after evolve_bot's own daily refresh, so this never competes
# with either the live trading scanner or evolve_bot's own real API
# calls for rate-limit headroom).
#
# Fully independent of the live trading system - market_memory.py is
# never imported by spy_scanner.py, local_information_engine.py, or
# discord_command_bot.py, so this scheduled task cannot affect real
# trading even if it fails outright. Every step inside it is
# INSERT OR IGNORE / only-fills-gaps, so a missed day, a duplicate run,
# or running it by hand anytime (`powershell -File
# run_market_memory_collection.ps1`) is always safe.

$ErrorActionPreference = "Continue"
Set-Location "C:\Tradysquid"

$logPath = "C:\Tradysquid\state\market_memory_log.txt"
$logDir = Split-Path $logPath -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$result = & ".venv-tradysquid\Scripts\python.exe" "run_with_env.py" "market_memory.py" 2>&1
Add-Content -Path $logPath -Value "[$timestamp] $result"
