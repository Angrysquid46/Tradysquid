@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Tradysquid One-Click Installer

rem Append a dot so the quoted argument does not end in a backslash. A trailing
rem backslash before a quote can become a literal quote in PowerShell's path.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ONE-CLICK-TRADYSQUID.ps1" -RepositoryPath "%~dp0."
set "TRADYSQUID_EXIT=%ERRORLEVEL%"

echo.
if "%TRADYSQUID_EXIT%"=="0" (
    echo Tradysquid one-click installation finished successfully.
) else (
    echo Tradysquid one-click installation failed with exit code %TRADYSQUID_EXIT%.
)
echo.
pause
exit /b %TRADYSQUID_EXIT%
