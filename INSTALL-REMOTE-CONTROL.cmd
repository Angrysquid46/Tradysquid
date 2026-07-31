@echo off
setlocal
title Install Tradysquids Remote Control
cd /d "%~dp0"

echo.
echo ============================================
echo   INSTALLING TRADYSQUIDS REMOTE CONTROL
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo Git is not installed or not available in PATH.
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not available in PATH.
    pause
    exit /b 1
)

echo Checking local configuration...
python check_command_setup.py
if errorlevel 1 (
    echo.
    echo Tradysquids setup is incomplete. Fix the items shown above first.
    pause
    exit /b 1
)

echo Closing old manually started Tradysquids processes...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_tradysquid_processes.ps1" >nul 2>&1

timeout /t 2 /nobreak >nul

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" mkdir "%STARTUP%"

(
    echo @echo off
    echo start "" wscript.exe "%~dp0start_supervisor_hidden.vbs"
) > "%STARTUP%\Tradysquids Supervisor.cmd"

echo Starting the supervisor now...
start "" wscript.exe "%~dp0start_supervisor_hidden.vbs"

timeout /t 6 /nobreak >nul

echo.
echo Installation complete.
echo.
echo Tradysquids will now:
echo   - start automatically when you sign into Windows
echo   - keep the laptop awake while the supervisor is running
echo   - restart the bot, scanner engine, and ngrok if they crash
echo   - check GitHub for approved updates every two minutes
echo   - validate updates and roll back failed deployments
echo   - synchronize Discord commands, channels, guides, and permissions
echo   - report deployments in Discord
echo.
echo This is the final one-time laptop setup.
echo.
pause
