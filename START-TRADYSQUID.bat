@echo off
setlocal
title Tradysquids Launcher
cd /d "%~dp0"

echo.
echo ============================================
echo        STARTING TRADYSQUIDS
echo ============================================
echo.

python check_command_setup.py
if errorlevel 1 (
    echo.
    echo Setup is incomplete. See COMMAND_BOT_SETUP.md.
    pause
    exit /b 1
)

echo Starting the background supervisor...
start "" wscript.exe "%~dp0start_supervisor_hidden.vbs"

timeout /t 5 /nobreak >nul

echo Opening the working tabs...
start "" "https://discord.com/channels/1532077258099917020/1532235137469780139"
start "" "https://www.tradingview.com/chart/"
start "" "https://github.com/Angrysquid46/Tradysquid/actions"
start "" "http://127.0.0.1:4040"

echo.
echo Tradysquids is running under the background supervisor.
echo You no longer need to keep three CMD windows open.
echo Run INSTALL-REMOTE-CONTROL.cmd once to start it automatically at Windows login.
echo.
pause
