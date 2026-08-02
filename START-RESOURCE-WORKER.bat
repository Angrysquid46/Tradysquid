@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-worker\Scripts\python.exe" (
  echo Resource worker virtual environment is missing.
  echo Run SETUP-RESOURCE-WORKER.ps1 first.
  exit /b 1
)

if not exist ".env.worker" (
  echo .env.worker is missing.
  echo Copy .env.worker.example to .env.worker and configure RESOURCE_MESH_ROOT.
  exit /b 1
)

".venv-worker\Scripts\python.exe" resource_mesh_worker.py
exit /b %errorlevel%
