@echo off
setlocal
cd /d "%~dp0"
title Tradysquid Final Offline Deployment v4
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0OFFLINE-RECOVERY-INSTALL.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
  echo Tradysquid offline deployment finished successfully.
) else (
  echo Tradysquid offline deployment stopped with code %EXIT_CODE%.
  echo Read the error above. The installer preserves or restores the prior working version.
)
echo.
pause
exit /b %EXIT_CODE%
