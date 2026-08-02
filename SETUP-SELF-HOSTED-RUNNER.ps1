[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RegistrationToken,

    [string]$RepositoryUrl = "https://github.com/Angrysquid46/Tradysquid",

    [string]$RunnerDirectory = "C:\TradysquidRunner",

    [string]$RunnerName = "",

    [string]$Labels = "tradysquid-worker"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an Administrator PowerShell window."
    }
}

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

Assert-Administrator
if (-not $RunnerName) {
    $RunnerName = "tradysquid-worker-$($env:COMPUTERNAME.ToLowerInvariant())"
}

Write-Step "Locating the latest official GitHub Actions runner"
$release = Invoke-RestMethod `
    -Uri "https://api.github.com/repos/actions/runner/releases/latest" `
    -Headers @{ "User-Agent" = "Tradysquid-Runner-Installer" }
$asset = $release.assets | Where-Object {
    $_.name -match '^actions-runner-win-x64-[0-9.]+\.zip$'
} | Select-Object -First 1
if (-not $asset) {
    throw "GitHub did not return a Windows x64 runner asset."
}

Write-Step "Downloading $($asset.name)"
New-Item -ItemType Directory -Force -Path $RunnerDirectory | Out-Null
$archive = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive

Write-Step "Replacing the previous runner package without deleting runner diagnostics"
$configuration = Join-Path $RunnerDirectory ".runner"
if (Test-Path $configuration) {
    Push-Location $RunnerDirectory
    try {
        if (Test-Path ".\svc.cmd") {
            & .\svc.cmd stop 2>$null
            & .\svc.cmd uninstall 2>$null
        }
        & .\config.cmd remove --token $RegistrationToken 2>$null
    }
    finally {
        Pop-Location
    }
}
Get-ChildItem -LiteralPath $RunnerDirectory -Force | Where-Object {
    $_.Name -notin @("_diag")
} | Remove-Item -Recurse -Force
Expand-Archive -LiteralPath $archive -DestinationPath $RunnerDirectory -Force
Remove-Item -LiteralPath $archive -Force

Write-Step "Registering the isolated repository runner"
Push-Location $RunnerDirectory
try {
    & .\config.cmd `
        --unattended `
        --replace `
        --url $RepositoryUrl `
        --token $RegistrationToken `
        --name $RunnerName `
        --labels $Labels `
        --work "_work"
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub runner registration failed with exit code $LASTEXITCODE"
    }

    Write-Step "Installing the runner as an auto-start Windows service"
    & .\svc.cmd install
    & .\svc.cmd start
}
finally {
    Pop-Location
}

Write-Host "Self-hosted GitHub runner installed." -ForegroundColor Green
Write-Host "Runner: $RunnerName"
Write-Host "Labels: self-hosted, Windows, X64, $Labels"
Write-Host "The short-lived registration token was not stored by this script."
