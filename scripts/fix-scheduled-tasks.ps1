# Run this ONCE from an elevated (Run as Administrator) PowerShell window.
#
# Fixes two real gaps found live on 2026-08-11:
#   1. The only scheduled task on this machine ("Tradysquid Startup") points
#      at scripts\start.ps1, which launches `python -m tradysquid.app` - the
#      unused rewrite package, not the actual deployed system. It's been
#      crash-failing (access violation) since 2026-08-05 and hasn't run
#      since. Redirected here to ENSURE-SUPERVISOR.ps1, the real launcher.
#   2. ENSURE-SUPERVISOR.ps1 is designed to run on a recurring interval (it
#      has a heartbeat-freshness check built for exactly that), but nothing
#      was ever scheduled to actually invoke it periodically - so there was
#      no ongoing self-healing if the supervisor crashed mid-session, only
#      whatever happened to still be running. This adds that missing
#      recurring watchdog task.

$ErrorActionPreference = 'Stop'
$Root = 'C:\Tradysquid'
$Ensure = Join-Path $Root 'ENSURE-SUPERVISOR.ps1'
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Ensure`""

# 1. Redirect the existing logon-triggered task to the real launcher.
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Arguments -WorkingDirectory $Root
Set-ScheduledTask -TaskName 'Tradysquid Startup' -Action $action
Write-Host "Updated 'Tradysquid Startup' to launch ENSURE-SUPERVISOR.ps1 instead of the retired tradysquid.app package."

# 2. Add a recurring watchdog so a mid-session crash gets caught too, not
#    just a fresh logon. Every 2 minutes, indefinitely.
$watchdogName = 'Tradysquid Watchdog'
if (Get-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $watchdogName -Confirm:$false
}
$watchdogAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Arguments -WorkingDirectory $Root
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$watchdogPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$watchdogSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $watchdogName -Action $watchdogAction -Trigger $watchdogTrigger -Principal $watchdogPrincipal -Settings $watchdogSettings -Description 'Checks the Tradysquid supervisor every 2 minutes and relaunches it if the heartbeat has gone stale or the health port has no healthy owner.'
Write-Host "Registered '$watchdogName' - runs ENSURE-SUPERVISOR.ps1 every 2 minutes."

Write-Host ""
Write-Host "Done. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName 'Tradysquid Startup','Tradysquid Watchdog' | Select TaskName, State"
