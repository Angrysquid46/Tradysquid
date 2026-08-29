@echo off
setlocal
cd /d "%~dp0"
if not exist state mkdir state
if exist "state\surge-stop.flag" exit /b 0
:restart
echo [%date% %time%] Starting SURGE...>> "%~dp0state\surge-startup.log"
set "PATH=%~dp0.venv-tradysquid\Scripts;%PATH%"
python -u -m bots.surge.launch >> "%~dp0state\surge-startup.log" 2>&1
if exist "state\surge-stop.flag" exit /b 0
timeout /t 15 /nobreak >nul
goto restart
