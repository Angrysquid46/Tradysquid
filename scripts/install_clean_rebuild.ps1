param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit,

    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,

    [Parameter(Mandatory = $true)]
    [string]$CredentialHandoffPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$CredentialHandoffSha256
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $PSCommandPath
$BodyPath = Join-Path $ScriptRoot 'install_clean_rebuild_body.ps1'
$RuntimeFixPath = Join-Path $ScriptRoot 'installer_runtime_fixes.ps1'
$TemporaryPath = Join-Path $ScriptRoot ('.install-clean-rebuild-patched-' + [guid]::NewGuid().ToString('N') + '.ps1')

try {
    if (-not (Test-Path -LiteralPath $BodyPath -PathType Leaf)) {
        throw "Installer body was not found: $BodyPath"
    }
    if (-not (Test-Path -LiteralPath $RuntimeFixPath -PathType Leaf)) {
        throw "Installer runtime fix was not found: $RuntimeFixPath"
    }

    $Body = Get-Content -LiteralPath $BodyPath -Raw -Encoding UTF8
    $BaseHelperLine = ". (Join-Path `$ScriptRoot 'installer_helpers.ps1')"
    $RuntimeFixLine = ". (Join-Path `$ScriptRoot 'installer_runtime_fixes.ps1')"
    $InjectedBlock = $BaseHelperLine + [Environment]::NewLine + $RuntimeFixLine

    if ($Body -notmatch [regex]::Escape($BaseHelperLine)) {
        throw 'Installer helper load marker was not found in the preserved installer body.'
    }
    if ($Body -match [regex]::Escape($RuntimeFixLine)) {
        $PatchedBody = $Body
    } else {
        $PatchedBody = [regex]::Replace(
            $Body,
            [regex]::Escape($BaseHelperLine),
            [Text.RegularExpressions.MatchEvaluator]{ param($Match) $InjectedBlock },
            1
        )
    }

    [IO.File]::WriteAllText(
        $TemporaryPath,
        $PatchedBody,
        [Text.UTF8Encoding]::new($false)
    )

    $Arguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"' + $TemporaryPath + '"')
        '-ExpectedCleanCommit'
        $ExpectedCleanCommit
        '-RepositoryPath'
        ('"' + $RepositoryPath + '"')
        '-CredentialHandoffPath'
        ('"' + $CredentialHandoffPath + '"')
        '-CredentialHandoffSha256'
        $CredentialHandoffSha256
    )
    $Process = Start-Process -FilePath 'powershell.exe' -ArgumentList $Arguments -WorkingDirectory $RepositoryPath -Wait -PassThru
    $ExitCode = [int]$Process.ExitCode
} catch {
    Write-Host ('Installer wrapper failed: ' + $_.Exception.Message) -ForegroundColor Red
    $ExitCode = 1
} finally {
    Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
}

exit $ExitCode
