$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv-tradysquid\Scripts\python.exe'
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw 'Tradysquid virtual environment is missing. Run SETUP-AND-START.cmd.'
}

$State = Join-Path $Root 'state'
$PidFile = Join-Path $State 'tradysquid.pid.json'
$Startup = Join-Path $State 'startup.json'
$DiscordReadiness = Join-Path $State 'discord-readiness.json'
$PublishingReadiness = Join-Path $State 'discord-publishing-bootstrap.json'
$Log = Join-Path $Root 'logs\launcher.log'
$ErrorLog = Join-Path $Root 'logs\launcher-errors.log'
New-Item -ItemType Directory -Force -Path $State,(Join-Path $Root 'logs') | Out-Null

if (Test-Path -LiteralPath $PidFile) {
  try {
    $pidValue = (Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json).pid
    if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
      throw "Tradysquid is already running with PID $pidValue"
    }
  } catch {
    if ($_.Exception.Message -like 'Tradysquid is already*') { throw }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
  }
}

foreach ($path in $Startup,$DiscordReadiness,$PublishingReadiness) {
  Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

$p = Start-Process `
  -FilePath $Python `
  -ArgumentList '-m','tradysquid.app' `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -PassThru `
  -RedirectStandardOutput $Log `
  -RedirectStandardError $ErrorLog

for ($i=0; $i -lt 180; $i++) {
  if ($p.HasExited) {
    $tail = ''
    if (Test-Path -LiteralPath $ErrorLog) {
      $tail = (Get-Content -LiteralPath $ErrorLog -Tail 20 -ErrorAction SilentlyContinue) -join ' | '
    }
    throw "Tradysquid exited during startup with code $($p.ExitCode). $tail"
  }

  if (
    (Test-Path -LiteralPath $Startup) -and
    (Test-Path -LiteralPath $DiscordReadiness) -and
    (Test-Path -LiteralPath $PublishingReadiness)
  ) {
    try {
      $startupReceipt = Get-Content -LiteralPath $Startup -Raw | ConvertFrom-Json
      $discordReceipt = Get-Content -LiteralPath $DiscordReadiness -Raw | ConvertFrom-Json
      $publishingReceipt = Get-Content -LiteralPath $PublishingReadiness -Raw | ConvertFrom-Json

      $valid = (
        $startupReceipt.status -eq 'RUNNING' -and
        [int]$startupReceipt.pid -eq $p.Id -and
        $startupReceipt.scheduler_running -eq $true -and
        [int]$startupReceipt.strategy_count -eq 6 -and
        $startupReceipt.discord_ready -eq $true -and
        $startupReceipt.discord_publishing_ready -eq $true -and
        $discordReceipt.status -eq 'PASS' -and
        [int]$discordReceipt.slash_commands_synchronized -gt 0 -and
        $publishingReceipt.status -eq 'PASS' -and
        [int]$publishingReceipt.persistent_cards.failed -eq 0
      )
      if ($valid) {
        Write-Host 'PASS'
        exit 0
      }

      if ($startupReceipt.status -eq 'FAILED') {
        throw ('Application startup receipt failed: ' + $startupReceipt.error)
      }
      if ($discordReceipt.status -eq 'FAILED') {
        throw ('Discord readiness failed: ' + $discordReceipt.error)
      }
      if ($publishingReceipt.status -eq 'FAILED') {
        throw 'Discord publishing bootstrap failed.'
      }
    } catch {
      if ($_.Exception.Message -like '*failed*') { throw }
    }
  }
  Start-Sleep -Seconds 1
}

throw 'Tradysquid did not reach application, Discord, and publishing readiness within 180 seconds.'
