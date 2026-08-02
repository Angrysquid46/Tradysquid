[CmdletBinding()]
param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv-dev\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & $PythonCommand -m venv ".venv-dev"
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-dev.txt
& $VenvPython -m pre_commit install

$files = @(
    "market_data_runtime.py", "provider_lanes.py", "targeted_scan_runtime.py",
    "resource_mesh.py", "resource_mesh_worker.py", "resource_mesh_runtime.py",
    "resource_mesh_worker_extensions.py", "resource_mesh_worker_bootstrap.py",
    "free_provider_policy.py", "security_hygiene.py",
    "test_resource_mesh.py", "test_market_data_runtime.py",
    "test_targeted_scan_runtime.py"
)

& $VenvPython security_hygiene.py
& $VenvPython -m ruff check @files
& $VenvPython -m ruff format --check @files
& $VenvPython -m unittest -q `
    test_resource_mesh.py `
    test_market_data_runtime.py `
    test_targeted_scan_runtime.py
& $VenvPython -m pip_audit -r requirements.txt
& $VenvPython -m pip_audit -r requirements-worker.txt

Write-Host "Free quality tools are installed in .venv-dev and the pre-commit gate is active." -ForegroundColor Green
