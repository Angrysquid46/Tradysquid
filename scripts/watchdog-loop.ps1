# Runs ENSURE-SUPERVISOR.ps1 once immediately, then forever on a 2-minute
# interval, hidden, for the lifetime of the logon session. Launched from
# the current user's own Startup folder (see install below) - deliberately
# NOT a Scheduled Task, since modifying/creating one requires elevated
# (admin) rights this checkout doesn't have and can't get non-interactively.
# A per-user Startup-folder entry needs no elevation at all and achieves
# the same practical outcome: the supervisor gets checked and relaunched
# on every logon, and again every 2 minutes for as long as this user stays
# logged in.

$Ensure = Join-Path $PSScriptRoot '..\ENSURE-SUPERVISOR.ps1'
while ($true) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Ensure
    } catch {
        # Never let one failed check kill the loop itself.
    }
    Start-Sleep -Seconds 120
}
