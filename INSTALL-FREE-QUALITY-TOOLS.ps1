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

& $VenvPython security_hygiene.py
& $VenvPython -m ruff check `
    market_data_runtime.py provider_lanes.py targeted_scan_runtime.py `
    resource_mesh.py resource_mesh_worker.py resource_mesh_runtime.py `
    security_hygiene.py test_resource_mesh.py test_market_data_runtime.py
& $VenvPython -m unittest -q test_resource_mesh.py test_market_data_runtime.py

Write-Host "Free quality tools are installed in .venv-dev and the pre-commit gate is active." -ForegroundColor Green
