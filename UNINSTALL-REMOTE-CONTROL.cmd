@echo off
setlocal
title Remove Tradysquids Remote Control
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del /q "%STARTUP%\Tradysquids Supervisor.cmd" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_tradysquid_processes.ps1" >nul 2>&1

echo Tradysquids automatic startup and supervisor processes were removed.
pause
