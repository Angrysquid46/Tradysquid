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
    echo INSTALLATION FAILED.
    echo The watchdog task could not be created.
    pause
    exit /b 1
)

echo Starting the supervisor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ENSURE-SUPERVISOR.ps1"
if errorlevel 1 (
    echo.
    echo INSTALLATION FAILED.
    echo The supervisor did not start with a fresh heartbeat.
    pause
    exit /b 1
)

echo.
echo Running real automation acceptance tests...
echo This deliberately stops the supervisor and proves the Windows watchdog
 echo restores the full stack without human help. It also verifies Discord's
 echo actual Learning Center order is 01 through 27.
echo.
python "%~dp0run_with_env.py" "%~dp0automation_acceptance.py"
if errorlevel 1 (
    echo.
    echo ============================================
    echo   INSTALLATION FAILED ACCEPTANCE TESTS
    echo ============================================
    echo.
    echo Tradysquids is NOT considered automatic or complete.
    echo Review state\automation-acceptance.json and
    echo state\supervisor-watchdog.log for the exact failed check.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   AUTOMATION ACCEPTANCE PASSED
 echo ============================================
echo.
echo Verified on this laptop:
echo   - local main matches origin/main
 echo   - Windows watchdog task is enabled and runs every five minutes
 echo   - the supervisor was deliberately killed and automatically restored
 echo   - command bot, information engine, and ngrok returned healthy
 echo   - the local status response works after recovery
 echo   - Discord synchronization completed
 echo   - Learning Center is visibly ordered 01 through 27
 echo.
echo Installation is complete because the required behavior was proven.
echo.
pause
exit /b 0
