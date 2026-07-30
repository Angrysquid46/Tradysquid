@echo off
setlocal
title Tradysquids Launcher
cd /d "%~dp0"

echo.
echo ============================================
echo      STARTING TRADYSQUIDS COMMAND SERVER
echo ============================================
echo.

python check_command_setup.py
if errorlevel 1 (
    echo.
    echo Setup is incomplete. See COMMAND_BOT_SETUP.md.
    pause
    exit /b 1
)

set "NGROK_EXE="
where ngrok.exe >nul 2>&1
if not errorlevel 1 set "NGROK_EXE=ngrok.exe"

if not defined NGROK_EXE if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe" set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe"
if not defined NGROK_EXE if exist "%LOCALAPPDATA%\ngrok\ngrok.exe" set "NGROK_EXE=%LOCALAPPDATA%\ngrok\ngrok.exe"
if not defined NGROK_EXE if exist "%USERPROFILE%\Downloads\ngrok.exe" set "NGROK_EXE=%USERPROFILE%\Downloads\ngrok.exe"
if not defined NGROK_EXE if exist "%~dp0ngrok.exe" set "NGROK_EXE=%~dp0ngrok.exe"
if not defined NGROK_EXE for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ngrok.Ngrok_*\ngrok.exe" 2^>nul') do if not defined NGROK_EXE set "NGROK_EXE=%%G"

if not defined NGROK_EXE (
    echo.
    echo ngrok.exe could not be found.
    echo Put ngrok.exe in this folder or add its folder to Windows PATH.
    start "" "https://dashboard.ngrok.com/get-started/setup/windows"
    pause
    exit /b 1
)

echo Starting the local Discord command service...
start "Tradysquids Command Bot" cmd /k "cd /d ""%~dp0"" && python run_with_env.py discord_command_bot.py"

timeout /t 2 /nobreak >nul

echo Starting the secure ngrok tunnel...
start "Tradysquids ngrok Tunnel" cmd /k "cd /d ""%~dp0"" && python run_ngrok.py ""%NGROK_EXE%"""

timeout /t 3 /nobreak >nul

echo Opening the working tabs...
start "" "https://discord.com/channels/1532077258099917020/1532235137469780139"
start "" "https://www.tradingview.com/chart/1OTbDz14/?symbol=NYSE:F"
start "" "https://github.com/Angrysquid46/Tradysquid/actions"
start "" "http://127.0.0.1:4040"

echo.
echo Tradysquids is starting.
echo Keep the Command Bot and ngrok windows open.
echo You may close this launcher window.
echo.
pause
