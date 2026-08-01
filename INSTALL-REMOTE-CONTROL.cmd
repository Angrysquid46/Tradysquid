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

if not exist state mkdir state
> "state\supervisor-stop.flag" echo maintenance

echo Closing old manually started Tradysquids processes...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_tradysquid_processes.ps1" >nul 2>&1

timeout /t 2 /nobreak >nul
del /q "state\supervisor-stop.flag" >nul 2>&1

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" mkdir "%STARTUP%"

(
    echo @echo off
    echo start "" wscript.exe "%~dp0start_supervisor_hidden.vbs"
) > "%STARTUP%\Tradysquids Supervisor.cmd"

echo Installing the independent five-minute watchdog...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL-SUPERVISOR-WATCHDOG.ps1"
if errorlevel 1 (
    echo.
    echo The supervisor files are installed, but the watchdog task could not be created.
    echo Review the error above before relying on automatic recovery.
    pause
    exit /b 1
)

echo Starting the supervisor now...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ENSURE-SUPERVISOR.ps1"

timeout /t 8 /nobreak >nul

echo.
echo Installation complete.
echo.
echo Tradysquids will now:
echo   - start automatically when you sign into Windows
echo   - be checked and relaunched every five minutes if the supervisor dies
echo   - keep the laptop awake while the supervisor is running
echo   - restart the bot, scanner engine, and ngrok if they crash
echo   - check GitHub for approved updates every two minutes
echo   - show Git fetch failures in Discord instead of hiding them locally
echo   - retry failed Discord structure synchronization without needing another commit
echo   - validate updates and roll back failed deployments
echo   - synchronize Discord commands, channels, guides, and permissions
echo   - report deployments and verified service readiness in Discord
echo.
echo This is the final one-time laptop setup.
echo.
pause
