Set-StrictMode -Version Latest

function Read-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Environment file was not found: $Path"
    }

    $Values = @{}
    foreach ($Line in Get-Content -LiteralPath $Path -ErrorAction Stop) {
        if ($Line -match '^\s*([^#=\s]+)\s*=(.*)$') {
            $Values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $Values
}

function Get-CanonicalCredentialNames {
    return @(
        'DISCORD_BOT_TOKEN'
        'DISCORD_GUILD_ID'
        'DISCORD_OWNER_USER_ID'
        'TRADIER_ACCESS_TOKEN'
        'TRADIER_ENVIRONMENT'
    )
}

function Get-FirstPresentName {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Values,
        [Parameter(Mandatory = $true)][string[]]$Names
    )

    foreach ($Name in $Names) {
        if ($Values.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace([string]$Values[$Name])) {
            return $Name
        }
    }
    return $null
}

function Test-MigrationSourceCredentials {
    param([Parameter(Mandatory = $true)][string]$EnvPath)

    $Values = Read-DotEnv -Path $EnvPath
    $Sources = [ordered]@{}
    $Missing = New-Object System.Collections.Generic.List[string]

    $DiscordToken = Get-FirstPresentName -Values $Values -Names @('DISCORD_BOT_TOKEN')
    if ($DiscordToken) {
        $Sources['DISCORD_BOT_TOKEN'] = $DiscordToken
    } else {
        $Missing.Add('DISCORD_BOT_TOKEN')
    }

    $DiscordGuild = Get-FirstPresentName -Values $Values -Names @('DISCORD_GUILD_ID')
    if ($DiscordGuild) {
        $Sources['DISCORD_GUILD_ID'] = $DiscordGuild
    } else {
        $Missing.Add('DISCORD_GUILD_ID')
    }

    $DiscordOwner = Get-FirstPresentName -Values $Values -Names @(
        'DISCORD_OWNER_USER_ID'
        'DISCORD_ALLOWED_USER_ID'
    )
    if ($DiscordOwner) {
        $Sources['DISCORD_OWNER_USER_ID'] = $DiscordOwner
    } elseif ($DiscordToken -and $DiscordGuild) {
        $Sources['DISCORD_OWNER_USER_ID'] = 'Discord guild owner_id lookup'
    } else {
        $Missing.Add('DISCORD_OWNER_USER_ID source')
    }

    $TradierToken = Get-FirstPresentName -Values $Values -Names @(
        'TRADIER_ACCESS_TOKEN'
        'TRADIER_TOKEN'
    )
    if ($TradierToken) {
        $Sources['TRADIER_ACCESS_TOKEN'] = $TradierToken
    } else {
        $Missing.Add('TRADIER_ACCESS_TOKEN or TRADIER_TOKEN')
    }

    $TradierEnvironment = Get-FirstPresentName -Values $Values -Names @(
        'TRADIER_ENVIRONMENT'
        'TRADIER_BASE_URL'
    )
    if ($TradierEnvironment) {
        $Sources['TRADIER_ENVIRONMENT'] = $TradierEnvironment
    } else {
        $Sources['TRADIER_ENVIRONMENT'] = 'migration default'
    }

    if ($Missing.Count -gt 0) {
        throw ('Migration source credentials are incomplete: ' + ($Missing -join ', '))
    }

    return [pscustomobject]@{
        Status = 'PASS'
        Phase = 'pre-migration'
        Sources = $Sources
        SecretValuesWritten = $false
    }
}

function Test-CanonicalCredentials {
    param([Parameter(Mandatory = $true)][string]$EnvPath)

    $Values = Read-DotEnv -Path $EnvPath
    $Required = Get-CanonicalCredentialNames
    $Missing = @(
        $Required | Where-Object {
            -not $Values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$Values[$_])
        }
    )

    if ($Missing.Count -gt 0) {
        throw ('Canonical credentials are incomplete after migration: ' + ($Missing -join ', '))
    }

    return [pscustomobject]@{
        Status = 'PASS'
        Phase = 'post-migration'
        CanonicalNames = $Required
        SecretValuesWritten = $false
    }
}

function Get-VerifiedFileHash {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "File was not found for hashing: $Path"
    }

    $Stream = [IO.File]::OpenRead($Path)
    $Sha = [Security.Cryptography.SHA256]::Create()
    try {
        $Hash = $Sha.ComputeHash($Stream)
        return ([BitConverter]::ToString($Hash)).Replace('-', '').ToLowerInvariant()
    } finally {
        $Sha.Dispose()
        $Stream.Dispose()
    }
}

function Test-PathOutsideRepository {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryPath,
        [Parameter(Mandatory = $true)][string]$CandidatePath
    )

    $Repository = [IO.Path]::GetFullPath($RepositoryPath).TrimEnd('\', '/')
    $Candidate = [IO.Path]::GetFullPath($CandidatePath)
    $Prefix = $Repository + [IO.Path]::DirectorySeparatorChar
    if (
        $Candidate.Equals($Repository, [StringComparison]::OrdinalIgnoreCase) -or
        $Candidate.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw 'Credential handoff must be stored outside the repository.'
    }
    return $true
}

function Read-CanonicalCredentialHandoff {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryPath,
        [Parameter(Mandatory = $true)][string]$HandoffPath,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if ($ExpectedSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Credential handoff SHA-256 must contain 64 hexadecimal characters.'
    }

    $ResolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
    $ResolvedHandoff = (Resolve-Path -LiteralPath $HandoffPath -ErrorAction Stop).Path
    Test-PathOutsideRepository -RepositoryPath $ResolvedRepository -CandidatePath $ResolvedHandoff | Out-Null

    $ObservedHash = Get-VerifiedFileHash -Path $ResolvedHandoff
    if ($ObservedHash -ne $ExpectedSha256.ToLowerInvariant()) {
        throw 'Credential handoff SHA-256 does not match.'
    }

    $Required = Get-CanonicalCredentialNames
    $RequiredLookup = @{}
    foreach ($Name in $Required) {
        $RequiredLookup[$Name] = $true
    }

    $Values = @{}
    $Duplicates = New-Object System.Collections.Generic.List[string]
    foreach ($RawLine in Get-Content -LiteralPath $ResolvedHandoff -Encoding UTF8 -ErrorAction Stop) {
        $Line = $RawLine.Trim()
        if (-not $Line -or $Line.StartsWith('#')) {
            continue
        }
        if ($Line -notmatch '^([^#=\s]+)=(.*)$') {
            throw 'Credential handoff contains an invalid line.'
        }

        $Name = $Matches[1].Trim()
        $Value = $Matches[2].Trim()
        if (-not $RequiredLookup.ContainsKey($Name)) {
            throw "Credential handoff contains an unexpected name: $Name"
        }
        if ($Values.ContainsKey($Name)) {
            $Duplicates.Add($Name)
            continue
        }
        if ([string]::IsNullOrWhiteSpace($Value)) {
            throw "Credential handoff contains a blank value for $Name."
        }
        $Values[$Name] = $Value
    }

    if ($Duplicates.Count -gt 0) {
        throw ('Credential handoff contains duplicate names: ' + (($Duplicates | Sort-Object -Unique) -join ', '))
    }

    $Missing = @($Required | Where-Object { -not $Values.ContainsKey($_) })
    if ($Missing.Count -gt 0) {
        throw ('Credential handoff is missing canonical names: ' + ($Missing -join ', '))
    }
    if ($Values.Count -ne $Required.Count) {
        throw 'Credential handoff must contain exactly five canonical names.'
    }

    return [pscustomobject]@{
        Status = 'PASS'
        RepositoryPath = $ResolvedRepository
        HandoffPath = $ResolvedHandoff
        Sha256 = $ObservedHash
        CanonicalNames = $Required
        CanonicalNameCount = $Required.Count
        Values = $Values
        SecretValuesWritten = $false
    }
}

function Install-CanonicalCredentialHandoff {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Handoff,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    $DestinationParent = Split-Path -Parent $DestinationPath
    if ($DestinationParent) {
        New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
    }

    $TemporaryPath = $DestinationPath + '.new'
    Copy-Item -LiteralPath $Handoff.HandoffPath -Destination $TemporaryPath -Force

    $TemporaryHash = Get-VerifiedFileHash -Path $TemporaryPath
    if ($TemporaryHash -ne $Handoff.Sha256) {
        Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
        throw 'Temporary canonical environment hash does not match the handoff.'
    }

    Move-Item -LiteralPath $TemporaryPath -Destination $DestinationPath -Force
    $DestinationHash = Get-VerifiedFileHash -Path $DestinationPath
    if ($DestinationHash -ne $Handoff.Sha256) {
        throw 'Installed canonical environment hash does not match the handoff.'
    }

    $Validated = Test-CanonicalCredentials -EnvPath $DestinationPath
    return [pscustomobject]@{
        Status = 'PASS'
        DestinationPath = (Resolve-Path -LiteralPath $DestinationPath).Path
        SourceSha256 = $Handoff.Sha256
        DestinationSha256 = $DestinationHash
        CanonicalNames = $Validated.CanonicalNames
        CanonicalNameCount = $Validated.CanonicalNames.Count
        SecretValuesWritten = $false
    }
}

function Restore-FileExact {
    param(
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    $DestinationParent = Split-Path -Parent $DestinationPath
    if ($DestinationParent) {
        New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
    }
    Copy-Item -LiteralPath $BackupPath -Destination $DestinationPath -Force

    $BackupHash = Get-VerifiedFileHash -Path $BackupPath
    $RestoredHash = Get-VerifiedFileHash -Path $DestinationPath
    if ($BackupHash -ne $RestoredHash) {
        throw 'Restored file hash does not match the backup.'
    }
    return $RestoredHash
}

function Get-SanitizedText {
    param([AllowNull()][string]$Text)

    if ($null -eq $Text) {
        return ''
    }

    $Sanitized = $Text
    $SecretNames = @(
        'DISCORD_BOT_TOKEN'
        'TRADIER_ACCESS_TOKEN'
        'TRADIER_TOKEN'
        'OPENAI_API_KEY'
        'GITHUB_UPGRADE_TOKEN'
        'NGROK_AUTHTOKEN'
        'TRADINGVIEW_WEBHOOK_SECRET'
    )
    foreach ($Name in $SecretNames) {
        $Pattern = '(?im)(' + [regex]::Escape($Name) + '\s*=\s*)[^\r\n]+'
        $Sanitized = [regex]::Replace($Sanitized, $Pattern, '$1<redacted>')
    }
    $Sanitized = [regex]::Replace($Sanitized, '(?im)(Authorization\s*:\s*)(Bot|Bearer)\s+[^\s\r\n]+', '$1$2 <redacted>')
    return $Sanitized
}

function Test-PowerShellScriptSyntax {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "PowerShell script was not found: $Path"
    }

    $Tokens = $null
    $Errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$Tokens,
        [ref]$Errors
    )

    if ($Errors.Count -gt 0) {
        $SafeErrors = @(
            $Errors | ForEach-Object {
                [pscustomobject]@{
                    message = $_.Message
                    line = $_.Extent.StartLineNumber
                    column = $_.Extent.StartColumnNumber
                    text = $_.Extent.Text
                }
            }
        )
        throw ('PowerShell syntax validation failed: ' + ($SafeErrors | ConvertTo-Json -Compress))
    }

    return [pscustomobject]@{
        Status = 'PASS'
        Path = (Resolve-Path -LiteralPath $Path).Path
        ParseErrorCount = 0
    }
}

function Archive-PreviousSetupArtifacts {
    param([Parameter(Mandatory = $true)][string]$Root)

    $ArchiveRoot = Join-Path $Root ('logs\previous-setup-attempts\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $Artifacts = @(
        (Join-Path $Root 'SETUP-RESULT.json')
        (Join-Path $Root 'SETUP-RESULT.txt')
        (Join-Path $Root 'logs\setup.log')
        (Join-Path $Root 'logs\setup-child-stdout.log')
        (Join-Path $Root 'logs\setup-child-stderr.log')
        (Join-Path $Root 'state\setup-heartbeat.json')
        (Join-Path $Root 'state\setup-stage-state.json')
    )

    $Existing = @($Artifacts | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($Existing.Count -eq 0) {
        return $null
    }

    New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null
    foreach ($Artifact in $Existing) {
        Move-Item -LiteralPath $Artifact -Destination (Join-Path $ArchiveRoot (Split-Path -Leaf $Artifact)) -Force
    }
    return $ArchiveRoot
}

function Write-SetupHeartbeat {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$AttemptId,
        [Parameter(Mandatory = $true)][string]$CurrentStage,
        [Parameter(Mandatory = $true)][datetime]$StageStartedAt,
        [Parameter(Mandatory = $true)][int]$ProcessId
    )

    $Parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    [ordered]@{
        attempt_id = $AttemptId
        current_stage = $CurrentStage
        stage_started_at = $StageStartedAt.ToString('o')
        last_heartbeat_at = (Get-Date).ToString('o')
        process_id = $ProcessId
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-SetupStageTimeoutSeconds {
    param([Parameter(Mandatory = $true)][string]$Stage)

    $Timeouts = @{
        'setup-script-parse-validation' = 30
        'setup-attempt-initialization' = 60
        'repository-verification' = 60
        'backup-created' = 300
        'canonical-credential-migration' = 120
        'canonical-credential-validation' = 120
        'previous-runtime-cleanup' = 120
        'isolated-virtual-environment' = 300
        'pip-upgrade' = 300
        'dependency-installation' = 600
        'editable-project-installation' = 300
        'dependency-integrity-check' = 120
        'package-import-check' = 120
        'source-compilation' = 300
        'automated-test-suite' = 600
        'installation-verification' = 120
        'live-read-only-verification' = 120
        'startup-task-registration' = 120
        'application-start-and-readiness' = 300
        'final-health-verification' = 120
    }
    if ($Timeouts.ContainsKey($Stage)) {
        return [int]$Timeouts[$Stage]
    }
    return 600
}

function Invoke-SetupProcess {
    param(
        [Parameter(Mandatory = $true)][string]$SetupEntryScript,
        [Parameter(Mandatory = $true)][string]$SetupBodyScript,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$AttemptId,
        [Parameter(Mandatory = $true)][string]$ExpectedCleanCommit
    )

    Test-PowerShellScriptSyntax -Path $SetupEntryScript | Out-Null
    Test-PowerShellScriptSyntax -Path $SetupBodyScript | Out-Null
    $PreviousArtifacts = Archive-PreviousSetupArtifacts -Root $WorkingDirectory

    $LogDirectory = Join-Path $WorkingDirectory 'logs'
    $StateDirectory = Join-Path $WorkingDirectory 'state'
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null

    $StdoutPath = Join-Path $LogDirectory 'setup-child-stdout.log'
    $StderrPath = Join-Path $LogDirectory 'setup-child-stderr.log'
    $HeartbeatPath = Join-Path $StateDirectory 'setup-heartbeat.json'
    $StageStatePath = Join-Path $StateDirectory 'setup-stage-state.json'

    $Arguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"' + $SetupEntryScript + '"')
        '-AttemptId'
        $AttemptId
        '-ExpectedCleanCommit'
        $ExpectedCleanCommit
    )

    $StartedAt = Get-Date
    $ProcessParameters = @{
        FilePath = (Get-Command powershell.exe -ErrorAction Stop).Source
        ArgumentList = $Arguments
        WorkingDirectory = $WorkingDirectory
        NoNewWindow = $true
        PassThru = $true
        RedirectStandardOutput = $StdoutPath
        RedirectStandardError = $StderrPath
    }
    $Process = Start-Process @ProcessParameters
    if ($null -eq $Process) {
        throw 'Could not start the clean setup process.'
    }

    $CurrentStage = 'setup-attempt-initialization'
    $StageStartedAt = $StartedAt
    $LastHeartbeatAt = [datetime]::MinValue
    $LastConsoleUpdateAt = [datetime]::MinValue
    $TimedOutStage = $null

    while (-not $Process.HasExited) {
        Start-Sleep -Seconds 2
        $Process.Refresh()

        if (Test-Path -LiteralPath $StageStatePath -PathType Leaf) {
            try {
                $StageState = Get-Content -LiteralPath $StageStatePath -Raw | ConvertFrom-Json
                if ($StageState.attempt_id -eq $AttemptId -and $StageState.current_stage) {
                    if ($CurrentStage -ne [string]$StageState.current_stage) {
                        $CurrentStage = [string]$StageState.current_stage
                        $StageStartedAt = [datetime]$StageState.stage_started_at
                    }
                }
            } catch {
                $null = $_
            }
        }

        $Now = Get-Date
        if (($Now - $LastHeartbeatAt).TotalSeconds -ge 10) {
            Write-SetupHeartbeat -Path $HeartbeatPath -AttemptId $AttemptId -CurrentStage $CurrentStage -StageStartedAt $StageStartedAt -ProcessId $Process.Id
            $LastHeartbeatAt = $Now
        }
        if (($Now - $LastConsoleUpdateAt).TotalSeconds -ge 15) {
            $Elapsed = [Math]::Round(($Now - $StageStartedAt).TotalSeconds)
            Write-Host "Still running: $CurrentStage - $Elapsed seconds"
            $LastConsoleUpdateAt = $Now
        }

        $TimeoutSeconds = Get-SetupStageTimeoutSeconds -Stage $CurrentStage
        if (($Now - $StageStartedAt).TotalSeconds -gt $TimeoutSeconds) {
            $TimedOutStage = $CurrentStage
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            break
        }
    }

    $Process.WaitForExit()
    $ExitedAt = Get-Date

    $Stdout = ''
    $Stderr = ''
    if (Test-Path -LiteralPath $StdoutPath -PathType Leaf) {
        $Stdout = Get-SanitizedText -Text (Get-Content -LiteralPath $StdoutPath -Raw)
        [IO.File]::WriteAllText($StdoutPath, $Stdout, [Text.UTF8Encoding]::new($false))
    }
    if (Test-Path -LiteralPath $StderrPath -PathType Leaf) {
        $Stderr = Get-SanitizedText -Text (Get-Content -LiteralPath $StderrPath -Raw)
        [IO.File]::WriteAllText($StderrPath, $Stderr, [Text.UTF8Encoding]::new($false))
    }

    foreach ($Line in @($Stdout -split "`r?`n" | Select-Object -Last 30)) {
        if (-not [string]::IsNullOrWhiteSpace($Line)) {
            Write-Host $Line
        }
    }
    foreach ($Line in @($Stderr -split "`r?`n" | Select-Object -Last 30)) {
        if (-not [string]::IsNullOrWhiteSpace($Line)) {
            Write-Host "STDERR: $Line" -ForegroundColor Red
        }
    }

    $ExitCode = $Process.ExitCode
    if ($TimedOutStage) {
        $ExitCode = 124
    }

    return [pscustomobject]@{
        ProcessId = $Process.Id
        StartedAt = $StartedAt.ToString('o')
        ExitedAt = $ExitedAt.ToString('o')
        ExitCode = $ExitCode
        WaitedForExit = $true
        AttemptId = $AttemptId
        StdoutPath = $StdoutPath
        StderrPath = $StderrPath
        PreviousArtifacts = $PreviousArtifacts
        TimedOutStage = $TimedOutStage
        LastObservedStage = $CurrentStage
    }
}

function Read-CurrentSetupReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$AttemptId,
        [Parameter(Mandatory = $true)][datetime]$ProcessStartedAt,
        [Parameter(Mandatory = $true)][string]$ExpectedRepositoryPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCleanCommit
    )

    $Path = Join-Path $Root 'SETUP-RESULT.json'
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    try {
        $Receipt = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return $null
    }

    if ($Receipt.attempt_id -ne $AttemptId) {
        return $null
    }
    if (-not $Receipt.observed_at -or [datetime]$Receipt.observed_at -lt $ProcessStartedAt) {
        return $null
    }
    if ([IO.Path]::GetFullPath([string]$Receipt.repository_path) -ne [IO.Path]::GetFullPath($ExpectedRepositoryPath)) {
        return $null
    }
    if ($Receipt.setup_commit -ne $ExpectedCleanCommit) {
        return $null
    }
    return $Receipt
}

function Copy-SanitizedSetupEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BackupRoot,
        [Parameter(Mandatory = $true)][string]$AttemptId,
        [Parameter(Mandatory = $true)][string]$ExpectedCleanCommit
    )

    $Destination = Join-Path $BackupRoot ("failed-setup\$AttemptId")
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    $Files = @(
        (Join-Path $Root 'SETUP-RESULT.json')
        (Join-Path $Root 'SETUP-RESULT.txt')
        (Join-Path $Root 'logs\setup.log')
        (Join-Path $Root 'logs\setup-child-stdout.log')
        (Join-Path $Root 'logs\setup-child-stderr.log')
        (Join-Path $Root 'state\setup-heartbeat.json')
        (Join-Path $Root 'state\setup-stage-state.json')
    )

    foreach ($File in $Files) {
        if (Test-Path -LiteralPath $File -PathType Leaf) {
            $SafeText = Get-SanitizedText -Text (Get-Content -LiteralPath $File -Raw)
            [IO.File]::WriteAllText(
                (Join-Path $Destination (Split-Path -Leaf $File)),
                $SafeText,
                [Text.UTF8Encoding]::new($false)
            )
        }
    }

    $SetupScript = Join-Path $Root 'scripts\setup.ps1'
    [ordered]@{
        attempt_id = $AttemptId
        expected_clean_commit = $ExpectedCleanCommit
        active_branch_at_capture = (& git -C $Root branch --show-current).Trim()
        setup_script_sha256 = if (Test-Path -LiteralPath $SetupScript -PathType Leaf) {
            Get-VerifiedFileHash -Path $SetupScript
        } else {
            $null
        }
        captured_at = (Get-Date).ToString('o')
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Destination 'evidence-receipt.json') -Encoding UTF8

    return $Destination
}
