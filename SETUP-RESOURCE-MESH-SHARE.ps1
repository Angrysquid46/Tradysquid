[CmdletBinding()]
param(
    [string]$MeshPath = "C:\TradysquidMesh",
    [string]$ShareName = "TradysquidMesh",
    [string]$WorkerUser = "TradysquidWorker"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

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

function Set-EnvValue(
    [string]$Path,
    [string]$Name,
    [string]$Value
) {
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -LiteralPath $Path
    }
    $escaped = [Regex]::Escape($Name)
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$escaped=") {
            $found = $true
            "$Name=$Value"
        }
        else {
            $line
        }
    }
    if (-not $found) {
        $updated += "$Name=$Value"
    }
    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
}

Assert-Administrator

Write-Step "Creating the dedicated resource-worker Windows account"
$existingUser = Get-LocalUser -Name $WorkerUser -ErrorAction SilentlyContinue
$createdPassword = $null
if (-not $existingUser) {
    $createdPassword = Read-Host `
        "Enter a strong password for the local $WorkerUser account" `
        -AsSecureString
    New-LocalUser `
        -Name $WorkerUser `
        -Password $createdPassword `
        -Description "Tradysquid resource-mesh file worker" `
        -PasswordNeverExpires:$true `
        -UserMayNotChangePassword:$false | Out-Null
}
Enable-LocalUser -Name $WorkerUser

Write-Step "Creating the resource-mesh directory"
New-Item -ItemType Directory -Force -Path $MeshPath | Out-Null
foreach ($name in @("inbox", "processing", "outbox", "failed", "archive", "dedupe", "cache")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $MeshPath $name) | Out-Null
}

Write-Step "Applying least-privilege NTFS access"
$account = "$env:COMPUTERNAME\$WorkerUser"
$acl = Get-Acl -LiteralPath $MeshPath
$rule = New-Object Security.AccessControl.FileSystemAccessRule(
    $account,
    "Modify",
    "ContainerInherit,ObjectInherit",
    "None",
    "Allow"
)
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $MeshPath -AclObject $acl

Write-Step "Creating the authenticated SMB share"
$existingShare = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existingShare) {
    if ($existingShare.Path -ne $MeshPath) {
        throw "SMB share $ShareName already points to $($existingShare.Path), not $MeshPath."
    }
    Grant-SmbShareAccess -Name $ShareName -AccountName $account -AccessRight Change -Force | Out-Null
}
else {
    New-SmbShare `
        -Name $ShareName `
        -Path $MeshPath `
        -ChangeAccess $account `
        -CachingMode None `
        -FolderEnumerationMode AccessBased `
        -Description "Tradysquid optional second-PC resource mesh" | Out-Null
}

Write-Step "Pointing the production Tradysquid process at the local mesh path"
$envPath = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $RepoRoot ".env.example") $envPath
    Write-Warning "A new .env was created from .env.example. Existing production secrets still need to be filled in before Tradysquid can run."
}
Set-EnvValue -Path $envPath -Name "RESOURCE_MESH_ROOT" -Value $MeshPath
Set-EnvValue -Path $envPath -Name "RESOURCE_MESH_LOCAL_FALLBACK" -Value "true"

Write-Step "Verifying the share"
$unc = "\\$env:COMPUTERNAME\$ShareName"
Get-SmbShare -Name $ShareName | Format-Table Name, Path, Description -AutoSize

Write-Host "`nResource mesh share is ready." -ForegroundColor Green
Write-Host "Production path: $MeshPath"
Write-Host "Worker UNC path: $unc"
Write-Host "Worker account: $account"
Write-Host "Use the password entered above when SETUP-RESOURCE-WORKER.ps1 asks for the share credential."
Write-Host "The share is not granted to Everyone and contains no Tradier or Discord credentials."
