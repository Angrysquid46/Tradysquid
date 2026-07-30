@echo off
setlocal
set "TARGET=%~dp0START-TRADYSQUID.bat"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop'); $path=Join-Path $desktop 'Start Tradysquids.lnk'; $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($path); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0'; $s.Description='Start Tradysquids Discord command server and ngrok'; $s.Save(); Write-Host ('Desktop shortcut created: '+$path)"

pause
