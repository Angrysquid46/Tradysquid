@echo off
setlocal
cd /d "%~dp0"
title Tradysquid

echo ============================================
echo   TRADYSQUID - START EVERYTHING
echo ============================================
echo.

if not exist ".env" (
    echo No .env found in this folder.
    echo Copy your existing .env from your current Tradysquid folder into
    echo this one, then run this file again.
    echo.
    pause
    exit /b 1
)

echo Checking configuration...
python check_command_setup.py
if errorlevel 1 (
    echo.
    echo Configuration is incomplete - see the message above.
    pause
    exit /b 1
)

echo.
echo Installing/checking dependencies (only downloads what's missing)...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo Dependency install failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Starting Tradysquid. Leave this window open - it IS the bot.
echo Press Ctrl+C to stop it.
echo.

:restart
python -u run_with_env.py run_supervisor_simple.py
echo.
echo Tradysquid stopped with exit code %ERRORLEVEL%. Restarting in 10 seconds...
echo Press Ctrl+C now if you meant to stop it for good.
timeout /t 10
goto restart
