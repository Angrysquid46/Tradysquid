@echo off
setlocal
cd /d "%~dp0"
if not exist state mkdir state
title Tradysquids Supervisor

if exist "state\supervisor-stop.flag" exit /b 0

:restart
echo [%date% %time%] Starting Tradysquids Supervisor...
python "%~dp0run_with_env.py" "%~dp0run_supervisor.py"
set "SUPERVISOR_EXIT=%ERRORLEVEL%"

if exist "state\supervisor-stop.flag" (
    echo Tradysquids Supervisor stop flag detected.
    exit /b 0
)

if "%SUPERVISOR_EXIT%"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ENSURE-SUPERVISOR.ps1" -CheckOnly >nul 2>&1
    if not errorlevel 1 exit /b 0
)

echo Tradysquids Supervisor exited with code %SUPERVISOR_EXIT%.
echo Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto restart
