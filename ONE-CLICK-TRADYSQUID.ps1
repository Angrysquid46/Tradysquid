[CmdletBinding()]
param(
    [string]$RepositoryPath = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedRemote = 'https://github.com/Angrysquid46/Tradysquid.git'
$InstallerName = 'RUN-AUDITED-TRADYSQUID-INSTALL.ps1'
$PrivateBackup = $null

function Test-IsAdministrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-GitChecked {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $PreviousPreference = $ErrorActionPreference
    $Output = @()
    $ExitCode = 1
    try {
        $ErrorActionPreference = 'Continue'
        $Output = @(& git -C $script:Repository @Arguments 2>&1)
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($ExitCode -ne 0) {
        $Detail = ($Output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        if ([string]::IsNullOrWhiteSpace($Detail)) { $Detail = "git exit code $ExitCode" }
        throw "$FailureMessage $Detail"
    }
    return $Output
}

function Read-DotEnvNames {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Values = @{}
    foreach ($RawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $Line = $RawLine.Trim()
        if (-not $Line -or $Line.StartsWith('#') -or $Line -notmatch '^([^=]+)=(.*)$') {
            continue
        }
        $Values[$Matches[1].Trim()] = $Matches[2].Trim()
    }
    return $Values
}

function Add-CanonicalEnvironmentAliases {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Values = Read-DotEnvNames -Path $Path
    $Additions = [ordered]@{}
    if (-not $Values['DISCORD_OWNER_USER_ID'] -and $Values['DISCORD_ALLOWED_USER_ID']) {
        $Additions['DISCORD_OWNER_USER_ID'] = $Values['DISCORD_ALLOWED_USER_ID']
    }
    if (-not $Values['TRADIER_ACCESS_TOKEN'] -and $Values['TRADIER_TOKEN']) {
        $Additions['TRADIER_ACCESS_TOKEN'] = $Values['TRADIER_TOKEN']
    }
    if (-not $Values['TRADIER_ENVIRONMENT']) {
        $BaseUrl = [string]$Values['TRADIER_BASE_URL']
        $Additions['TRADIER_ENVIRONMENT'] = if ($BaseUrl -match 'sandbox') { 'paper' } else { 'production' }
    }
    if ($Additions.Count -gt 0) {
        $Lines = New-Object System.Collections.Generic.List[string]
        $Lines.Add('')
        $Lines.Add('# Canonical aliases added by the one-click installer; original names remain preserved.')
        foreach ($Name in $Additions.Keys) {
            $Lines.Add("$Name=$($Additions[$Name])")
        }
        Add-Content -LiteralPath $Path -Value $Lines -Encoding UTF8
    }

    $Validated = Read-DotEnvNames -Path $Path
    $Required = @(
        'DISCORD_APPLICATION_ID',
        'DISCORD_PUBLIC_KEY',
        'DISCORD_BOT_TOKEN',
        'DISCORD_GUILD_ID',
        'DISCORD_OWNER_USER_ID',
        'TRADIER_ACCESS_TOKEN',
        'TRADIER_BASE_URL',
        'TRADIER_ENVIRONMENT',
        'GITHUB_UPGRADE_TOKEN',
        'GITHUB_REPOSITORY',
        'SEC_USER_AGENT',
        'NGROK_AUTHTOKEN',
        'TRADINGVIEW_WEBHOOK_SECRET',
        'COMMAND_BOT_HOST',
        'COMMAND_BOT_PORT'
    )
    $Missing = @($Required | Where-Object { [string]::IsNullOrWhiteSpace([string]$Validated[$_]) })
    if ($Missing.Count -gt 0) {
        throw ('Private configuration is incomplete. Missing variable names: ' + ($Missing -join ', '))
    }
}

try {
    $Repository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path

    if (-not (Test-IsAdministrator)) {
        Write-Host 'Requesting Administrator permission...' -ForegroundColor Yellow
        $Arguments = @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', ('"' + $PSCommandPath + '"'),
            '-RepositoryPath', ('"' + $Repository + '"')
        )
        $Elevated = Start-Process -FilePath 'powershell.exe' `
            -ArgumentList $Arguments `
            -WorkingDirectory $Repository `
            -Verb RunAs `
            -Wait `
            -PassThru
        exit ([int]$Elevated.ExitCode)
    }

    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        throw 'Git for Windows is not installed or is not available on PATH.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.git'))) {
        throw "Tradysquid Git repository was not found at $Repository"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.env') -PathType Leaf)) {
        throw "Private local configuration was not found at $Repository\.env"
    }

    $EnvironmentPath = Join-Path $Repository '.env'
    $BackupParent = Split-Path -Parent $Repository
    $PrivateBackup = Join-Path $BackupParent ('Tradysquid-private-config-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $PrivateBackup | Out-Null
    Copy-Item -LiteralPath $EnvironmentPath -Destination (Join-Path $PrivateBackup '.env') -Force
    Add-CanonicalEnvironmentAliases -Path $EnvironmentPath

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host 'TRADYSQUID ONE-CLICK REPAIR AND INSTALL' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host "Repository: $Repository"
    Write-Host 'Private configuration: present (values not read or displayed)'

    $RemoteResult = & git -C $Repository remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Adding the missing GitHub origin remote...' -ForegroundColor Yellow
        Invoke-GitChecked -Arguments @('remote', 'add', 'origin', $ExpectedRemote) `
            -FailureMessage 'Could not add the GitHub origin remote.' | Out-Null
    } elseif ([string]$RemoteResult -ne $ExpectedRemote) {
        Write-Host 'Repairing the GitHub origin remote...' -ForegroundColor Yellow
        Invoke-GitChecked -Arguments @('remote', 'set-url', 'origin', $ExpectedRemote) `
            -FailureMessage 'Could not repair the GitHub origin remote.' | Out-Null
    }

    Write-Host 'Fetching GitHub main...' -ForegroundColor Cyan
    Invoke-GitChecked -Arguments @('fetch', '--prune', 'origin', 'main') `
        -FailureMessage 'Could not fetch origin/main.' | Out-Null

    $MainExists = & git -C $Repository show-ref --verify --quiet refs/heads/main
    if ($LASTEXITCODE -ne 0) {
        Invoke-GitChecked -Arguments @('branch', 'main', 'origin/main') `
            -FailureMessage 'Could not create the local main branch.' | Out-Null
    }
    Invoke-GitChecked -Arguments @('branch', '--set-upstream-to=origin/main', 'main') `
        -FailureMessage 'Could not configure main to track origin/main.' | Out-Null

    $Installer = Join-Path $Repository $InstallerName
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
        throw "Audited installer was not found: $Installer"
    }

    Write-Host 'GitHub connection and main tracking are ready.' -ForegroundColor Green
    Write-Host 'Starting the audited installer...' -ForegroundColor Green
    $InstallerArguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $Installer + '"'),
        '-RepositoryPath', ('"' + $Repository + '"')
    )
    $InstallerProcess = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList $InstallerArguments `
        -WorkingDirectory $Repository `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ([int]$InstallerProcess.ExitCode -ne 0) {
        exit ([int]$InstallerProcess.ExitCode)
    }

    Get-ChildItem -LiteralPath $Repository -File -Filter '.env.before-one-click-*.bak' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Private recovery backup: $PrivateBackup" -ForegroundColor DarkGray
    exit 0
} catch {
    Write-Host ''
    Write-Host 'TRADYSQUID ONE-CLICK INSTALLER FAILED' -ForegroundColor Red
    Write-Host ([string]$_.Exception.Message) -ForegroundColor Red
    Write-Host 'No secret values were written by this launcher.' -ForegroundColor Yellow
    Read-Host 'Press Enter after copying or photographing this result'
    exit 1
}
