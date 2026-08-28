@echo off
setlocal
cd /d "%~dp0"
if not exist state mkdir state
title RIPTIDE Launcher
if exist "state\riptide-stop.flag" exit /b 0

:restart
echo [%date% %time%] Starting RIPTIDE...>> "%~dp0state\riptide-startup.log"
set "PATH=%~dp0.venv-tradysquid\Scripts;%PATH%"
python -u -m bots.riptide.launch >> "%~dp0state\riptide-startup.log" 2>&1
set "RIPTIDE_EXIT=%ERRORLEVEL%"
echo [%date% %time%] RIPTIDE exited with code %RIPTIDE_EXIT%.>> "%~dp0state\riptide-startup.log"
if exist "state\riptide-stop.flag" exit /b 0
timeout /t 15 /nobreak >nul
goto restart
