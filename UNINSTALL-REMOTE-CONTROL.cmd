@echo off
setlocal
title Remove Tradysquids Remote Control
cd /d "%~dp0"

if not exist state mkdir state
> "state\supervisor-stop.flag" echo uninstall

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del /q "%STARTUP%\Tradysquids Supervisor.cmd" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL-SUPERVISOR-WATCHDOG.ps1" -Remove >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_tradysquid_processes.ps1" >nul 2>&1

echo Tradysquids automatic startup, watchdog, and supervisor processes were removed.
pause
