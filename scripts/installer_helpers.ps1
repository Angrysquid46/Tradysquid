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

function Get-CanonicalCredentialNames {
    return @(
        'DISCORD_BOT_TOKEN',
        'DISCORD_GUILD_ID',
        'DISCORD_OWNER_USER_ID',
        'TRADIER_ACCESS_TOKEN',
        'TRADIER_ENVIRONMENT'
    )
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
    $required = Get-CanonicalCredentialNames
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

function Test-PathOutsideRepository {
    param(
        [Parameter(Mandatory=$true)][string]$RepositoryPath,
        [Parameter(Mandatory=$true)][string]$CandidatePath
    )

    $repository = [IO.Path]::GetFullPath($RepositoryPath).TrimEnd('\', '/')
    $candidate = [IO.Path]::GetFullPath($CandidatePath)
    $prefix = $repository + [IO.Path]::DirectorySeparatorChar
    if (
        $candidate.Equals($repository, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw 'Credential handoff must be stored outside the repository.'
    }
    return $true
}

function Read-CanonicalCredentialHandoff {
    param(
        [Parameter(Mandatory=$true)][string]$RepositoryPath,
        [Parameter(Mandatory=$true)][string]$HandoffPath,
        [Parameter(Mandatory=$true)][string]$ExpectedSha256
    )

    if ($ExpectedSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Credential handoff SHA-256 must contain 64 hexadecimal characters.'
    }

    $resolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
    $resolvedHandoff = (Resolve-Path -LiteralPath $HandoffPath -ErrorAction Stop).Path
    Test-PathOutsideRepository -RepositoryPath $resolvedRepository -CandidatePath $resolvedHandoff | Out-Null

    $observedHash = Get-VerifiedFileHash -Path $resolvedHandoff
    if ($observedHash -ne $ExpectedSha256.ToLowerInvariant()) {
        throw 'Credential handoff SHA-256 does not match.'
    }

    $required = Get-CanonicalCredentialNames
    $requiredLookup = @{}
    foreach ($name in $required) { $requiredLookup[$name] = $true }

    $values = @{}
    $duplicates = New-Object System.Collections.Generic.List[string]
    foreach ($rawLine in Get-Content -LiteralPath $resolvedHandoff -Encoding UTF8 -ErrorAction Stop) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -notmatch '^([^#=\s]+)=(.*)$') {
            throw 'Credential handoff contains an invalid line.'
        }
        $name = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if (-not $requiredLookup.ContainsKey($name)) {
            throw "Credential handoff contains an unexpected name: $name"
        }
        if ($values.ContainsKey($name)) {
            $duplicates.Add($name)
            continue
        }
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "Credential handoff contains a blank value for $name."
        }
        $values[$name] = $value
    }

    if ($duplicates.Count -gt 0) {
        throw ('Credential handoff contains duplicate names: ' + (($duplicates | Sort-Object -Unique) -join ', '))
    }

    $missing = @($required | Where-Object { -not $values.ContainsKey($_) })
    if ($missing.Count -gt 0) {
        throw ('Credential handoff is missing canonical names: ' + ($missing -join ', '))
    }
    if ($values.Count -ne $required.Count) {
        throw 'Credential handoff must contain exactly five canonical names.'
    }

    return [pscustomobject]@{
        Status = 'PASS'
        RepositoryPath = $resolvedRepository
        HandoffPath = $resolvedHandoff
        Sha256 = $observedHash
        CanonicalNames = $required
        CanonicalNameCount = $required.Count
        Values = $values
        SecretValuesWritten = $false
    }
}

function Install-CanonicalCredentialHandoff {
    param(
        [Parameter(Mandatory=$true)][pscustomobject]$Handoff,
        [Parameter(Mandatory=$true)][string]$DestinationPath
    )

    $destinationParent = Split-Path -Parent $DestinationPath
    if ($destinationParent) {
        New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    }

    $temporaryPath = $DestinationPath + '.new'
    Copy-Item -LiteralPath $Handoff.HandoffPath -Destination $temporaryPath -Force

    $temporaryHash = Get-VerifiedFileHash -Path $temporaryPath
    if ($temporaryHash -ne $Handoff.Sha256) {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        throw 'Temporary canonical environment hash does not match the handoff.'
    }

    Move-Item -LiteralPath $temporaryPath -Destination $DestinationPath -Force
    $destinationHash = Get-VerifiedFileHash -Path $DestinationPath
    if ($destinationHash -ne $Handoff.Sha256) {
        throw 'Installed canonical environment hash does not match the handoff.'
    }

    $validated = Test-CanonicalCredentials -EnvPath $DestinationPath
    return [pscustomobject]@{
        Status = 'PASS'
        DestinationPath = (Resolve-Path -LiteralPath $DestinationPath).Path
        SourceSha256 = $Handoff.Sha256
        DestinationSha256 = $destinationHash
        CanonicalNames = $validated.CanonicalNames
        CanonicalNameCount = $validated.CanonicalNames.Count
        SecretValuesWritten = $false
    }
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
