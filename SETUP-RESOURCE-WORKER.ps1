[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MeshRoot,

    [string]$TaskName = "Tradysquid Resource Worker",

    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Set-EnvValue(
    [string]$Path,
    [string]$Name,
    [string]$Value
) {
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -LiteralPath $Path
    }
    $escaped = [Regex]::Escape($Name)
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$escaped=") {
            $found = $true
            "$Name=$Value"
        }
        else {
            $line
        }
    }
    if (-not $found) {
        $updated += "$Name=$Value"
    }
    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
}

Write-Step "Checking the shared resource-mesh folder"
if (-not (Test-Path -LiteralPath $MeshRoot)) {
    throw "The mesh folder is not reachable: $MeshRoot"
}
$probe = Join-Path $MeshRoot ("worker-write-test-" + [Guid]::NewGuid().ToString("N") + ".tmp")
Set-Content -LiteralPath $probe -Value "Tradysquid worker write test" -Encoding UTF8
Remove-Item -LiteralPath $probe -Force

Write-Step "Creating the isolated worker Python environment"
$VenvPython = Join-Path $RepoRoot ".venv-worker\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & $PythonCommand -m venv ".venv-worker"
}
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r "requirements-worker.txt"

Write-Step "Creating the worker-only environment file"
$WorkerEnv = Join-Path $RepoRoot ".env.worker"
if (-not (Test-Path $WorkerEnv)) {
    Copy-Item ".env.worker.example" $WorkerEnv
}
Set-EnvValue -Path $WorkerEnv -Name "RESOURCE_MESH_ROOT" -Value $MeshRoot
if (-not ((Get-Content -LiteralPath $WorkerEnv) -match '^RESOURCE_WORKER_ID=.+')) {
    Set-EnvValue -Path $WorkerEnv -Name "RESOURCE_WORKER_ID" -Value ("worker-" + $env:COMPUTERNAME.ToLowerInvariant())
}

Write-Step "Running a worker self-test"
& $VenvPython "resource_mesh_worker.py" --once
if ($LASTEXITCODE -ne 0) {
    throw "The resource worker self-test failed with exit code $LASTEXITCODE"
}

Write-Step "Installing the current-user scheduled task"
$Launcher = Join-Path $RepoRoot "START-RESOURCE-WORKER.bat"
$Action = New-ScheduledTaskAction -Execute $Launcher -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Free-data and compute worker for Tradysquid. No brokerage or Discord credentials required."
Start-ScheduledTask -TaskName $TaskName

Write-Step "Worker installation complete"
Write-Host "Task: $TaskName"
Write-Host "Mesh: $MeshRoot"
Write-Host "Environment: $WorkerEnv"
Write-Host "Add optional free provider keys to .env.worker whenever they are available."
