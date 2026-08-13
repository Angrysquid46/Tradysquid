# Invoked by the "Tradysquid Evolve Bot Daily Refresh" scheduled task
# (daily, every day including weekends, before market open) - the
# owner's explicit ask: "I want it daily so we catch everything" after
# learning that regenerating the backtest / retraining / checking for
# new logic proposals only ever happened on the Monday weekly review
# before this. Also directly runnable by hand right after a manual
# Robinhood MCP pull (`powershell -File run_daily_refresh.ps1`) instead
# of waiting for the next scheduled run - same script either way.
#
# Two real steps: refresh_pipeline.run_refresh() (backtest regen ->
# retrain -> proposals, skipped cheaply when no new Robinhood data
# exists) and presentation.post_dashboard() (gated on its own daily
# cadence, reflects real live trades independent of any data pull).
# Runs every day, not just weekdays, since a manual pull could happen on
# a weekend and shouldn't sit unprocessed until Monday.

$ErrorActionPreference = "Continue"
Get-Content "C:\Tradysquid\.env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        if (-not (Test-Path "env:$($parts[0].Trim())")) {
            Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
        }
    }
}
Set-Location "C:\Tradysquid\evolve_bot"

$logPath = "C:\Tradysquid\evolve_bot\state\daily_refresh_log.txt"
$logDir = Split-Path $logPath -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$result = & "..\.venv-evolve\Scripts\python.exe" -c "import json, refresh_pipeline, presentation; print(json.dumps({'refresh': refresh_pipeline.run_refresh(), 'dashboard': presentation.post_dashboard()['status']}))" 2>&1
Add-Content -Path $logPath -Value "[$timestamp] $result"
