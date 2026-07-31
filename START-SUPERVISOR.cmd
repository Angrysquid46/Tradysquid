@echo off
setlocal
cd /d "%~dp0"
if not exist state mkdir state
title Tradysquids Supervisor

:restart
echo [%date% %time%] Starting Tradysquids Supervisor...
python run_with_env.py tradysquid_supervisor.py
set "SUPERVISOR_EXIT=%ERRORLEVEL%"

if "%SUPERVISOR_EXIT%"=="0" (
    exit /b 0
)

echo Tradysquids Supervisor exited with code %SUPERVISOR_EXIT%.
echo Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto restart
