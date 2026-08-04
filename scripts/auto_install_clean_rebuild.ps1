param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCleanCommit,

    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$LegacyCommit = 'ba75aae5f34f3889404bfe0c7c0b96663a92a657'
$ExpectedRemote = 'Angrysquid46/Tradysquid'
$CleanBranch = 'clean-rebuild'
$ArchiveBranch = 'archive/current-failed-implementation'
$InstallerRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'installer_helpers.ps1')

$Repository = $null
$OriginalBranch = $null
$OriginalCommit = $null
$BackupRoot = $null
$AttemptId = [guid]::NewGuid().ToString()
$Status = 'FAILED'
$FailedStage = 'initialization'
$ErrorMessage = $null
$SetupReceipt = $null
$SetupExitCode = 1
$StartedAt = Get-Date
$StopFlag = $null
$ResultPath = $null
$ExternalResultPath = $null
$RollbackFailures = New-Object System.Collections.Generic.List[string]

function Write-InstallerProgress {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $Stamp = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$Stamp] $Message" -ForegroundColor $Color

    if ($Repository) {
        try {
            $ProgressPath = Join-Path $Repository 'state\clean-rebuild-auto-progress.json'
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ProgressPath) | Out-Null
            [ordered]@{
                attempt_id = $AttemptId
                status = $Status
                stage = $FailedStage
                message = $Message
                observed_at = (Get-Date).ToString('o')
                expected_clean_commit = $ExpectedCleanCommit
                secret_values_written = $false
            } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ProgressPath -Encoding UTF8
        } catch {}
    }
}

function ConvertTo-CommandLineArgument {
    param([AllowNull()][string]$Value)

    if ($null -eq $Value) { return '""' }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [string]$WorkingDirectory = $null,
        [int[]]$AllowedExitCodes = @(0)
    )

    $Info = New-Object System.Diagnostics.ProcessStartInfo
    $Info.FileName = $FilePath
    $Info.Arguments = (($Arguments | ForEach-Object { ConvertTo-CommandLineArgument -Value $_ }) -join ' ')
    if ($WorkingDirectory) { $Info.WorkingDirectory = $WorkingDirectory }
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $Info
    if (-not $Process.Start()) {
        throw "Could not start process: $FilePath"
    }

    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $Process.Kill() } catch {}
        throw "Process timed out after $TimeoutSeconds seconds: $FilePath"
    }

    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $ExitCode = [int]$Process.ExitCode
    if ($AllowedExitCodes -notcontains $ExitCode) {
        $Detail = (($Stderr + "`n" + $Stdout).Trim())
        if ($Detail.Length -gt 1500) { $Detail = $Detail.Substring($Detail.Length - 1500) }
        throw "Process exited with code $ExitCode`: $FilePath $Detail"
    }

    return [pscustomobject]@{
        ExitCode = $ExitCode
        Stdout = $Stdout
        Stderr = $Stderr
    }
}

function Invoke-GitChecked {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Output = @(& git -C $Repository @Arguments 2>&1)
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }

    foreach ($Line in $Output) {
        $Text = [string]$Line
        if ($Text) { Write-Host $Text }
    }
    if ($ExitCode -ne 0) {
        throw $FailureMessage
    }
    return @($Output)
}

function Write-AutoResult {
    param([Parameter(Mandatory = $true)][string]$CurrentStatus)

    $ObservedBranch = $null
    $ObservedCommit = $null
    if ($Repository) {
        $PreviousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $ObservedBranch = (& git -C $Repository branch --show-current 2>$null).Trim()
            $ObservedCommit = (& git -C $Repository rev-parse HEAD 2>$null).Trim()
        } catch {
            $ObservedBranch = $null
            $ObservedCommit = $null
        } finally {
            $ErrorActionPreference = $PreviousPreference
        }
    }

    $Payload = [ordered]@{
        status = $CurrentStatus
        attempt_id = $AttemptId
        started_at = $StartedAt.ToString('o')
        observed_at = (Get-Date).ToString('o')
        failed_stage = $FailedStage
        error = $ErrorMessage
        repository_path = $Repository
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        expected_clean_commit = $ExpectedCleanCommit
        final_branch = $ObservedBranch
        final_commit = $ObservedCommit
        setup_exit_code = $SetupExitCode
        setup_receipt_status = if ($SetupReceipt) { [string]$SetupReceipt.status } else { $null }
        setup_failed_stage = if ($SetupReceipt) { [string]$SetupReceipt.failed_stage } else { $null }
        setup_error = if ($SetupReceipt) { [string]$SetupReceipt.error } else { $null }
        backup_root = $BackupRoot
        rollback_failures = @($RollbackFailures)
        full_environment_preserved = $true
        secret_values_written = $false
    }

    $Json = $Payload | ConvertTo-Json -Depth 8
    foreach ($Path in @($ResultPath, $ExternalResultPath)) {
        if ([string]::IsNullOrWhiteSpace([string]$Path)) { continue }
        try {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
            $Json | Set-Content -LiteralPath $Path -Encoding UTF8
        } catch {}
    }
}

function Stop-RepositoryPython {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Escaped = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match $Escaped -and
            $_.Name -in @('python.exe', 'pythonw.exe')
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Invoke-RobocopyMirror {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [int]$TimeoutSeconds = 300
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $Result = Invoke-BoundedProcess `
        -FilePath 'robocopy.exe' `
        -Arguments @($Source, $Destination, '/MIR', '/R:1', '/W:1', '/XJ', '/NFL', '/NDL', '/NJH', '/NJS', '/NP') `
        -TimeoutSeconds $TimeoutSeconds `
        -AllowedExitCodes @(0, 1, 2, 3, 4, 5, 6, 7)
    return $Result.ExitCode
}

function Copy-RuntimeSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $EnvironmentPath = Join-Path $Root '.env'
    $EnvironmentBackup = Join-Path $Destination '.env'
    Copy-Item -LiteralPath $EnvironmentPath -Destination $EnvironmentBackup -Force

    foreach ($Name in @('data', 'state', 'logs')) {
        $Source = Join-Path $Root $Name
        if (-not (Test-Path -LiteralPath $Source -PathType Container)) { continue }
        Write-InstallerProgress -Message "Backing up runtime directory: $Name" -Color Cyan
        Invoke-RobocopyMirror -Source $Source -Destination (Join-Path $Destination $Name) -TimeoutSeconds 300 | Out-Null
    }

    if (-not (Test-Path -LiteralPath $EnvironmentBackup -PathType Leaf)) {
        throw 'The complete local .env was not preserved in the external handoff backup.'
    }
    return Get-VerifiedFileHash -Path $EnvironmentBackup
}

function Restore-RuntimeSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Source
    )

    $EnvironmentBackup = Join-Path $Source '.env'
    if (Test-Path -LiteralPath $EnvironmentBackup -PathType Leaf) {
        Write-InstallerProgress -Message 'Restoring .env from the external backup.' -Color Cyan
        Restore-FileExact -BackupPath $EnvironmentBackup -DestinationPath (Join-Path $Root '.env') | Out-Null
    }

    foreach ($Name in @('data', 'state', 'logs')) {
        $BackupItem = Join-Path $Source $Name
        if (-not (Test-Path -LiteralPath $BackupItem -PathType Container)) { continue }
        Write-InstallerProgress -Message "Restoring runtime directory: $Name" -Color Cyan
        Invoke-RobocopyMirror -Source $BackupItem -Destination (Join-Path $Root $Name) -TimeoutSeconds 300 | Out-Null
    }
}

function Export-TradysquidScheduledTasks {
    param([Parameter(Mandatory = $true)][string]$Destination)

    $TaskDirectory = Join-Path $Destination 'scheduled-tasks'
    New-Item -ItemType Directory -Force -Path $TaskDirectory | Out-Null
    $Records = @()
    $Index = 0
    foreach ($Task in @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $_.TaskName -like '*Tradysquid*'
    })) {
        $FileName = ('task-{0:D3}.xml' -f $Index)
        $XmlPath = Join-Path $TaskDirectory $FileName
        Export-ScheduledTask -TaskName $Task.TaskName -TaskPath $Task.TaskPath |
            Set-Content -LiteralPath $XmlPath -Encoding Unicode
        $Records += [pscustomobject]@{
            task_name = [string]$Task.TaskName
            task_path = [string]$Task.TaskPath
            xml_file = $FileName
        }
        $Index++
    }
    $Records | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $TaskDirectory 'manifest.json') -Encoding UTF8
}

function Restore-TradysquidScheduledTasks {
    param([Parameter(Mandatory = $true)][string]$Source)

    $TaskDirectory = Join-Path $Source 'scheduled-tasks'
    $ManifestPath = Join-Path $TaskDirectory 'manifest.json'
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { return }
    $Raw = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    foreach ($Record in @($Raw)) {
        $XmlPath = Join-Path $TaskDirectory ([string]$Record.xml_file)
        if (-not (Test-Path -LiteralPath $XmlPath -PathType Leaf)) { continue }
        $TaskPath = [string]$Record.task_path
        if (-not $TaskPath.StartsWith('\')) { $TaskPath = '\' + $TaskPath }
        if (-not $TaskPath.EndsWith('\')) { $TaskPath += '\' }
        $FullTaskName = $TaskPath + [string]$Record.task_name
        Write-InstallerProgress -Message "Restoring scheduled task: $FullTaskName" -Color Cyan
        Invoke-BoundedProcess `
            -FilePath 'schtasks.exe' `
            -Arguments @('/Create', '/TN', $FullTaskName, '/XML', $XmlPath, '/F') `
            -TimeoutSeconds 30 `
            -AllowedExitCodes @(0) | Out-Null
    }
}

function Start-LegacySupervisor {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Launcher = Join-Path $Root 'START-SUPERVISOR.cmd'
    if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { return }
    $CommandShell = if ($env:ComSpec) { $env:ComSpec } else { 'cmd.exe' }
    Start-Process `
        -FilePath $CommandShell `
        -ArgumentList @('/d', '/c', 'start', '""', '/min', ('"' + $Launcher + '"')) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden | Out-Null
}

function Invoke-CleanStopBounded {
    param([Parameter(Mandatory = $true)][string]$Root)

    $CleanStop = Join-Path $Root 'scripts\stop.ps1'
    if (-not (Test-Path -LiteralPath $CleanStop -PathType Leaf)) { return }
    Write-InstallerProgress -Message 'Stopping the partial clean runtime before rollback.' -Color Cyan
    Invoke-BoundedProcess `
        -FilePath 'powershell.exe' `
        -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $CleanStop) `
        -WorkingDirectory $Root `
        -TimeoutSeconds 90 `
        -AllowedExitCodes @(0) | Out-Null
}

function Invoke-CleanSetupVisible {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BackupDirectory
    )

    $SetupEntry = Join-Path $Root 'scripts\setup_entry.ps1'
    $StdoutPath = Join-Path $BackupDirectory 'setup-entry-stdout.log'
    $StderrPath = Join-Path $BackupDirectory 'setup-entry-stderr.log'
    $StagePath = Join-Path $Root 'state\setup-stage-state.json'

    $Arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $SetupEntry,
        '-AttemptId', $AttemptId,
        '-ExpectedCleanCommit', $ExpectedCleanCommit
    )

    $Process = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -PassThru

    $Deadline = (Get-Date).AddMinutes(45)
    $LastStage = ''
    while (-not $Process.WaitForExit(5000)) {
        if ((Get-Date) -gt $Deadline) {
            try { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue } catch {}
            throw 'Clean setup exceeded the 45-minute hard timeout.'
        }

        if (Test-Path -LiteralPath $StagePath -PathType Leaf) {
            try {
                $Stage = Get-Content -LiteralPath $StagePath -Raw | ConvertFrom-Json
                if ($Stage.attempt_id -eq $AttemptId -and [string]$Stage.current_stage -ne $LastStage) {
                    $LastStage = [string]$Stage.current_stage
                    Write-InstallerProgress -Message "Setup stage: $LastStage [$($Stage.stage_status)]" -Color Yellow
                }
            } catch {}
        }
    }
    $Process.WaitForExit()

    if (Test-Path -LiteralPath $StdoutPath -PathType Leaf) {
        Write-Host ''
        Write-Host '=== CURRENT SETUP OUTPUT ===' -ForegroundColor Cyan
        Get-Content -LiteralPath $StdoutPath -Tail 100
    }
    if (Test-Path -LiteralPath $StderrPath -PathType Leaf) {
        $ErrorTail = @(Get-Content -LiteralPath $StderrPath -Tail 100 -ErrorAction SilentlyContinue)
        if ($ErrorTail.Count -gt 0) {
            Write-Host ''
            Write-Host '=== CURRENT SETUP ERRORS ===' -ForegroundColor Red
            $ErrorTail | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        }
    }

    return [int]$Process.ExitCode
}

try {
    $FailedStage = 'repository-verification'
    $Repository = (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
    $ResultPath = Join-Path $Repository 'state\clean-rebuild-auto-handoff.json'
    $StopFlag = Join-Path $Repository 'state\supervisor-stop.flag'

    if (-not (Test-Path -LiteralPath (Join-Path $Repository '.git'))) {
        throw 'Repository path is not a Git working tree.'
    }
    $Remote = (& git -C $Repository remote get-url origin 2>$null)
    if ($LASTEXITCODE -ne 0 -or $Remote -notmatch [regex]::Escape($ExpectedRemote)) {
        throw 'Repository remote is unexpected or unreadable.'
    }

    $OriginalBranch = (& git -C $Repository branch --show-current).Trim()
    if (-not $OriginalBranch) { $OriginalBranch = 'main' }
    $OriginalCommit = (& git -C $Repository rev-parse HEAD).Trim()

    Write-InstallerProgress -Message "Install attempt $AttemptId started." -Color Green

    $FailedStage = 'complete-environment-preflight'
    $EnvironmentPath = Join-Path $Repository '.env'
    Test-MigrationSourceCredentials -EnvPath $EnvironmentPath | Out-Null

    $FailedStage = 'external-runtime-backup'
    $Parent = Split-Path -Parent $Repository
    $BackupRoot = Join-Path $Parent ('Tradysquid-auto-handoff-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $AttemptId.Substring(0, 8))
    $ExternalResultPath = Join-Path $BackupRoot 'clean-rebuild-auto-handoff.json'
    Write-InstallerProgress -Message "Creating external backup: $BackupRoot" -Color Cyan
    $EnvironmentHash = Copy-RuntimeSnapshot -Root $Repository -Destination $BackupRoot
    Export-TradysquidScheduledTasks -Destination $BackupRoot
    [ordered]@{
        status = 'PASS'
        repository = $Repository
        original_branch = $OriginalBranch
        original_commit = $OriginalCommit
        environment_sha256 = $EnvironmentHash
        complete_environment_preserved = $true
        secret_values_written = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BackupRoot 'backup-receipt.json') -Encoding UTF8

    $FailedStage = 'runtime-stop'
    Write-InstallerProgress -Message 'Stopping legacy runtime and scheduled tasks.' -Color Cyan
    Stop-RepositoryPython -Root $Repository
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like '*Tradysquid*' } |
        Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

    $FailedStage = 'clean-branch-verification'
    Write-InstallerProgress -Message 'Fetching and verifying exact clean branch.' -Color Cyan
    Invoke-GitChecked `
        -Arguments @('fetch', 'origin', "+refs/heads/$CleanBranch`:refs/remotes/origin/$CleanBranch", "+refs/heads/$ArchiveBranch`:refs/remotes/origin/$ArchiveBranch") `
        -FailureMessage 'Git fetch for clean-rebuild failed.' | Out-Null

    $ObservedArchive = (& git -C $Repository rev-parse "refs/remotes/origin/$ArchiveBranch").Trim()
    if ($ObservedArchive -ne $LegacyCommit) {
        throw "Archive branch mismatch. Expected $LegacyCommit but received $ObservedArchive."
    }
    $ObservedClean = (& git -C $Repository rev-parse "refs/remotes/origin/$CleanBranch").Trim()
    if ($ObservedClean -ne $ExpectedCleanCommit) {
        throw "Clean branch mismatch. Expected $ExpectedCleanCommit but received $ObservedClean."
    }

    $FailedStage = 'clean-branch-switch'
    Write-InstallerProgress -Message 'Switching laptop checkout to clean-rebuild.' -Color Cyan
    Invoke-GitChecked `
        -Arguments @('switch', '--force-create', $CleanBranch, "origin/$CleanBranch") `
        -FailureMessage 'Could not switch the laptop checkout to clean-rebuild.' | Out-Null

    $FailedStage = 'complete-environment-restore'
    Write-InstallerProgress -Message 'Restoring verified .env into clean-rebuild.' -Color Cyan
    $EnvironmentBackup = Join-Path $BackupRoot '.env'
    $RestoredHash = Restore-FileExact -BackupPath $EnvironmentBackup -DestinationPath (Join-Path $Repository '.env')
    if ($RestoredHash -ne $EnvironmentHash) {
        throw 'The restored complete environment does not match the external backup.'
    }

    $FailedStage = 'clean-setup'
    Write-InstallerProgress -Message 'Running clean setup in the foreground.' -Color Green
    $SetupExitCode = Invoke-CleanSetupVisible -Root $Repository -BackupDirectory $BackupRoot

    $ReceiptPath = Join-Path $Repository 'SETUP-RESULT.json'
    if (Test-Path -LiteralPath $ReceiptPath -PathType Leaf) {
        $SetupReceipt = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json
    }
    if ($SetupExitCode -ne 0) {
        $SetupStage = if ($SetupReceipt -and $SetupReceipt.failed_stage) { [string]$SetupReceipt.failed_stage } else { 'setup-process' }
        $SetupError = if ($SetupReceipt -and $SetupReceipt.error) { [string]$SetupReceipt.error } else { "exit code $SetupExitCode" }
        throw "Clean setup failed at $SetupStage`: $SetupError"
    }
    if (-not $SetupReceipt -or [string]$SetupReceipt.attempt_id -ne $AttemptId -or [string]$SetupReceipt.status -ne 'PASS') {
        throw 'Clean setup did not produce a current PASS receipt.'
    }

    $FailedStage = $null
    $Status = 'PASS'
    $ErrorMessage = $null
    Write-AutoResult -CurrentStatus $Status
    Write-InstallerProgress -Message 'TRADYSQUID CLEAN INSTALLATION PASSED.' -Color Green
} catch {
    $ErrorMessage = [string]$_.Exception.Message
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host "SETUP FAILED AT: $FailedStage" -ForegroundColor Red
    Write-Host "ERROR: $ErrorMessage" -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red

    $Status = 'ROLLBACK IN PROGRESS'
    Write-AutoResult -CurrentStatus $Status
    Write-InstallerProgress -Message 'Failure receipt written. Starting bounded rollback.' -Color Yellow

    if ($Repository -and $OriginalCommit) {
        try {
            Invoke-CleanStopBounded -Root $Repository
        } catch {
            $RollbackFailures.Add("clean runtime stop: $($_.Exception.Message)")
            Write-InstallerProgress -Message "Rollback warning: $($_.Exception.Message)" -Color Yellow
        }

        try {
            Write-InstallerProgress -Message "Returning checkout to $OriginalBranch at $OriginalCommit." -Color Cyan
            try {
                Invoke-GitChecked -Arguments @('switch', '--force', $OriginalBranch) -FailureMessage "Could not switch to $OriginalBranch." | Out-Null
            } catch {
                Invoke-GitChecked -Arguments @('switch', '--force', 'main') -FailureMessage 'Could not switch to main during rollback.' | Out-Null
            }
            Invoke-GitChecked -Arguments @('reset', '--hard', $OriginalCommit) -FailureMessage 'Could not reset the original checkout during rollback.' | Out-Null
        } catch {
            $RollbackFailures.Add("branch restore: $($_.Exception.Message)")
            Write-InstallerProgress -Message "Rollback failure: $($_.Exception.Message)" -Color Red
        }

        if ($BackupRoot) {
            try {
                Restore-RuntimeSnapshot -Root $Repository -Source $BackupRoot
            } catch {
                $RollbackFailures.Add("runtime snapshot restore: $($_.Exception.Message)")
                Write-InstallerProgress -Message "Rollback failure: $($_.Exception.Message)" -Color Red
            }
            try {
                Restore-TradysquidScheduledTasks -Source $BackupRoot
            } catch {
                $RollbackFailures.Add("scheduled task restore: $($_.Exception.Message)")
                Write-InstallerProgress -Message "Rollback failure: $($_.Exception.Message)" -Color Red
            }
        }
    } else {
        $RollbackFailures.Add('original repository state was unavailable')
    }

    $Status = if ($RollbackFailures.Count -eq 0) { 'ROLLED BACK' } else { 'FAILED' }
    Write-AutoResult -CurrentStatus $Status
    Write-InstallerProgress -Message "Final installer status: $Status" -Color $(if ($Status -eq 'ROLLED BACK') { 'Yellow' } else { 'Red' })

    if ($Repository) {
        try {
            Write-InstallerProgress -Message 'Restarting legacy supervisor after final receipt.' -Color Yellow
            Start-LegacySupervisor -Root $Repository
        } catch {
            $RollbackFailures.Add("legacy restart: $($_.Exception.Message)")
            $Status = 'FAILED'
            Write-AutoResult -CurrentStatus $Status
            Write-InstallerProgress -Message "Legacy restart failed: $($_.Exception.Message)" -Color Red
        }
    }
} finally {
    if ($StopFlag -and (Test-Path -LiteralPath $StopFlag)) {
        Remove-Item -LiteralPath $StopFlag -Force -ErrorAction SilentlyContinue
    }
}

if ($Status -ne 'PASS') { exit 1 }
