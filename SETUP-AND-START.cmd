@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "usebackq delims=" %%I in (`powershell.exe -NoProfile -Command "[guid]::NewGuid().ToString()"`) do set "ATTEMPT_ID=%%I"
for /f "usebackq delims=" %%I in (`git -C "%~dp0." rev-parse HEAD 2^>nul`) do set "EXPECTED_COMMIT=%%I"

if not defined ATTEMPT_ID (
    echo ERROR: Could not create the setup attempt identifier.
    pause
    exit /b 1
)
if not defined EXPECTED_COMMIT (
    echo ERROR: This folder is not a valid Tradysquid Git checkout.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_entry.ps1" -AttemptId "%ATTEMPT_ID%" -ExpectedCleanCommit "%EXPECTED_COMMIT%"
set "TRADYSQUID_EXIT=%ERRORLEVEL%"
echo.
if "%TRADYSQUID_EXIT%"=="0" (
    echo Tradysquid setup and startup passed.
) else (
    echo Tradysquid setup failed with exit code %TRADYSQUID_EXIT%.
)
pause
exit /b %TRADYSQUID_EXIT%
