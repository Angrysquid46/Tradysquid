$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$receipt=Join-Path $Root 'UPDATE-RESULT.json'
if (!(Test-Path $receipt)) { throw 'No update receipt is available.' }
$previous=(Get-Content $receipt -Raw | ConvertFrom-Json).previous
if (!$previous) { throw 'Update receipt has no previous commit.' }
& (Join-Path $PSScriptRoot 'stop.ps1')
git -C $Root reset --hard $previous
& (Join-Path $PSScriptRoot 'start.ps1')
Write-Host 'PASS'
