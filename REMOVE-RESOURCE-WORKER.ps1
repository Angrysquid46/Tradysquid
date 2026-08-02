[CmdletBinding()]
param(
    [string]$TaskName = "Tradysquid Resource Worker",
    [string]$ShareHost = "",
    [switch]$RemoveVirtualEnvironment,
    [switch]$RemoveWorkerEnvironment
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
}
else {
    Write-Host "Scheduled task was not installed: $TaskName"
}

if ($ShareHost) {
    & cmdkey.exe "/delete:$ShareHost" | Out-Null
    Write-Host "Removed saved share credential for: $ShareHost"
}

if ($RemoveVirtualEnvironment) {
    $venv = Join-Path $RepoRoot ".venv-worker"
    if (Test-Path $venv) {
        Remove-Item -LiteralPath $venv -Recurse -Force
        Write-Host "Removed: $venv"
    }
}

if ($RemoveWorkerEnvironment) {
    $envFile = Join-Path $RepoRoot ".env.worker"
    if (Test-Path $envFile) {
        Remove-Item -LiteralPath $envFile -Force
        Write-Host "Removed: $envFile"
    }
}

Write-Host "Resource worker removal complete. Shared results and production data were not deleted."
