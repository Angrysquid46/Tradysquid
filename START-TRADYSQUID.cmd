@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Tradysquid

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv-tradysquid\Scripts\python.exe"
set "STATE=%ROOT%state"
set "LOGS=%ROOT%logs"

if not exist "%ROOT%.env" (
    echo ERROR: %ROOT%.env is missing.
    pause
    exit /b 1
)
if not exist "%PYTHON%" (
    echo ERROR: %PYTHON% is missing.
    echo Run the separate Tradysquid installation process once before ordinary startup.
    pause
    exit /b 1
)

"%PYTHON%" -c "import apscheduler, discord, dotenv, requests, tradysquid" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Tradysquid dependencies are missing or invalid in .venv-tradysquid.
    echo Ordinary startup will not reinstall or modify the environment.
    pause
    exit /b 1
)

if not exist "%STATE%" mkdir "%STATE%"
if not exist "%LOGS%" mkdir "%LOGS%"

powershell.exe -NoProfile -Command "$p='%STATE%\tradysquid.pid.json'; if(Test-Path -LiteralPath $p){try{$id=[int](Get-Content -LiteralPath $p -Raw|ConvertFrom-Json).pid; if(Get-Process -Id $id -ErrorAction SilentlyContinue){exit 10}; Remove-Item -LiteralPath $p -Force}catch{Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue}}; exit 0"
if errorlevel 10 (
    echo TRADYSQUID IS ALREADY RUNNING.
    exit /b 0
)

del /q "%STATE%\startup.json" "%STATE%\discord-readiness.json" "%STATE%\discord-publishing-bootstrap.json" >nul 2>&1

powershell.exe -NoProfile -Command "$p=Start-Process -FilePath $env:PYTHON -ArgumentList @('-m','tradysquid.app') -WorkingDirectory $env:ROOT -WindowStyle Hidden -RedirectStandardOutput ($env:LOGS + '\launcher.log') -RedirectStandardError ($env:LOGS + '\launcher-errors.log') -PassThru; [IO.File]::WriteAllText(($env:STATE + '\launcher-process-id.txt'),[string]$p.Id)"
if errorlevel 1 (
    echo ERROR: Windows could not start the Tradysquid Python process.
    pause
    exit /b 1
)

echo Waiting up to 300 seconds for Discord readiness...
for /L %%S in (1,1,300) do (
    powershell.exe -NoProfile -Command "$s='%STATE%\startup.json';$d='%STATE%\discord-readiness.json';$p='%STATE%\discord-publishing-bootstrap.json';$l='%STATE%\launcher-process-id.txt'; try{$launched=if(Test-Path $l){[int](Get-Content $l -Raw)}else{0};if($launched -gt 0 -and -not (Get-Process -Id $launched -ErrorAction SilentlyContinue)){exit 2};$sv=if(Test-Path $s){Get-Content $s -Raw|ConvertFrom-Json}else{$null};$dv=if(Test-Path $d){Get-Content $d -Raw|ConvertFrom-Json}else{$null};$pv=if(Test-Path $p){Get-Content $p -Raw|ConvertFrom-Json}else{$null};if($sv.status -eq 'FAILED' -or $dv.status -eq 'FAILED' -or $pv.status -eq 'FAILED'){exit 2};if($sv.status -eq 'RUNNING' -and $dv.status -eq 'PASS' -and [int]$dv.slash_commands_synchronized -gt 0 -and $pv.status -eq 'PASS' -and [int]$pv.persistent_cards.failed -eq 0 -and (Get-Process -Id ([int]$sv.pid) -ErrorAction SilentlyContinue)){exit 0}}catch{};exit 3" >nul 2>&1
    set "READY_EXIT=!ERRORLEVEL!"
    if "!READY_EXIT!"=="0" goto :ready
    if "!READY_EXIT!"=="2" goto :failed
    timeout /t 1 /nobreak >nul
)

echo ERROR: Discord readiness timed out after 300 seconds.
goto :details

:failed
echo ERROR: Tradysquid reported a startup or Discord readiness failure.

:details
powershell.exe -NoProfile -Command "$paths=@('%STATE%\startup.json','%STATE%\discord-readiness.json','%STATE%\discord-publishing-bootstrap.json');foreach($p in $paths){if(Test-Path $p){try{$v=Get-Content $p -Raw|ConvertFrom-Json;Write-Host ([IO.Path]::GetFileName($p) + ': status=' + $v.status);if($v.error){Write-Host ('error=' + $v.error)}}catch{}}};if(Test-Path '%LOGS%\launcher-errors.log'){Get-Content '%LOGS%\launcher-errors.log' -Tail 20}"
pause
exit /b 1

:ready
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "(Get-Content '%STATE%\startup.json' -Raw|ConvertFrom-Json).pid"`) do set "BOT_PID=%%P"
for /f "usebackq delims=" %%C in (`powershell.exe -NoProfile -Command "(Get-Content '%STATE%\discord-readiness.json' -Raw|ConvertFrom-Json).slash_commands_synchronized"`) do set "COMMAND_COUNT=%%C"
echo.
echo TRADYSQUID IS RUNNING
echo Process ID: !BOT_PID!
echo Discord commands synchronized: !COMMAND_COUNT!
exit /b 0
