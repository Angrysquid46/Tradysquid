@echo off
setlocal
cd /d "%~dp0"
if not exist state mkdir state
title AXIOM Launcher

if exist "state\axiom-stop.flag" exit /b 0

:restart
echo [%date% %time%] Starting AXIOM...>> "%~dp0state\axiom-startup.log"
set "PATH=%~dp0.venv-tradysquid\Scripts;%PATH%"
python -u -m bots.claude.launch >> "%~dp0state\axiom-startup.log" 2>&1
set "AXIOM_EXIT=%ERRORLEVEL%"
echo [%date% %time%] AXIOM exited with code %AXIOM_EXIT%.>> "%~dp0state\axiom-startup.log"

if exist "state\axiom-stop.flag" (
    echo AXIOM stop flag detected.
    exit /b 0
)

echo AXIOM exited with code %AXIOM_EXIT%. Restarting in 15 seconds...
timeout /t 15 /nobreak >nul
goto restart
