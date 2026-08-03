Set-StrictMode -Version Latest

function Read-DotEnv {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Environment file was not found: $Path"
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction Stop) {
        if ($line -match '^\s*([^#=\s]+)\s*=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $values
}

function Get-FirstPresentName {
    param(
        [Parameter(Mandatory=$true)][hashtable]$Values,
        [Parameter(Mandatory=$true)][string[]]$Names
    )

    foreach ($name in $Names) {
        if ($Values.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace([string]$Values[$name])) {
            return $name
        }
    }
    return $null
}

function Test-MigrationSourceCredentials {
    param([Parameter(Mandatory=$true)][string]$EnvPath)

    $values = Read-DotEnv -Path $EnvPath
    $sources = [ordered]@{}
    $missing = New-Object System.Collections.Generic.List[string]

    $discordToken = Get-FirstPresentName -Values $values -Names @('DISCORD_BOT_TOKEN')
    if ($discordToken) { $sources['DISCORD_BOT_TOKEN'] = $discordToken }
    else { $missing.Add('DISCORD_BOT_TOKEN') }

    $discordGuild = Get-FirstPresentName -Values $values -Names @('DISCORD_GUILD_ID')
    if ($discordGuild) { $sources['DISCORD_GUILD_ID'] = $discordGuild }
    else { $missing.Add('DISCORD_GUILD_ID') }

    $discordOwner = Get-FirstPresentName -Values $values -Names @(
        'DISCORD_OWNER_USER_ID',
        'DISCORD_ALLOWED_USER_ID'
    )
    if ($discordOwner) {
        $sources['DISCORD_OWNER_USER_ID'] = $discordOwner
    } elseif ($discordToken -and $discordGuild) {
        $sources['DISCORD_OWNER_USER_ID'] = 'Discord guild owner_id lookup'
    } else {
        $missing.Add('DISCORD_OWNER_USER_ID source')
    }

    $tradierToken = Get-FirstPresentName -Values $values -Names @(
        'TRADIER_ACCESS_TOKEN',
        'TRADIER_TOKEN'
    )
    if ($tradierToken) { $sources['TRADIER_ACCESS_TOKEN'] = $tradierToken }
    else { $missing.Add('TRADIER_ACCESS_TOKEN or TRADIER_TOKEN') }

    $tradierEnvironment = Get-FirstPresentName -Values $values -Names @(
        'TRADIER_ENVIRONMENT',
        'TRADIER_BASE_URL'
    )
    $sources['TRADIER_ENVIRONMENT'] = if ($tradierEnvironment) {
        $tradierEnvironment
    } else {
        'migration default'
    }

    if ($missing.Count -gt 0) {
        throw ('Migration source credentials are incomplete: ' + ($missing -join ', '))
    }

    return [pscustomobject]@{
        Status = 'PASS'
        Phase = 'pre-migration'
        Sources = $sources
        SecretValuesWritten = $false
    }
}

function Test-CanonicalCredentials {
    param([Parameter(Mandatory=$true)][string]$EnvPath)

    $values = Read-DotEnv -Path $EnvPath
    $required = @(
        'DISCORD_BOT_TOKEN',
        'DISCORD_GUILD_ID',
        'DISCORD_OWNER_USER_ID',
        'TRADIER_ACCESS_TOKEN',
        'TRADIER_ENVIRONMENT'
    )
    $missing = @($required | Where-Object {
        -not $values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$values[$_])
    })

    if ($missing.Count -gt 0) {
        throw ('Canonical credentials are incomplete after migration: ' + ($missing -join ', '))
    }

    return [pscustomobject]@{
        Status = 'PASS'
        Phase = 'post-migration'
        CanonicalNames = $required
        SecretValuesWritten = $false
    }
}

function Get-VerifiedFileHash {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "File was not found for hashing: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Restore-FileExact {
    param(
        [Parameter(Mandatory=$true)][string]$BackupPath,
        [Parameter(Mandatory=$true)][string]$DestinationPath
    )

    $destinationParent = Split-Path -Parent $DestinationPath
    if ($destinationParent) {
        New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    }
    Copy-Item -LiteralPath $BackupPath -Destination $DestinationPath -Force

    $backupHash = Get-VerifiedFileHash -Path $BackupPath
    $restoredHash = Get-VerifiedFileHash -Path $DestinationPath
    if ($backupHash -ne $restoredHash) {
        throw 'Restored file hash does not match the backup.'
    }
    return $restoredHash
}

function Invoke-SetupProcess {
    param(
        [Parameter(Mandatory=$true)][string]$SetupScript,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory
    )

    if (-not (Test-Path -LiteralPath $SetupScript -PathType Leaf)) {
        throw "Setup script was not found: $SetupScript"
    }

    $startedAt = Get-Date
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $SetupScript + '"'
    $process = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList $arguments `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -Wait `
        -PassThru
    $exitedAt = Get-Date

    return [pscustomobject]@{
        ProcessId = $process.Id
        StartedAt = $startedAt.ToString('o')
        ExitedAt = $exitedAt.ToString('o')
        ExitCode = $process.ExitCode
        WaitedForExit = $true
    }
}
