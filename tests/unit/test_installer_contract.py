from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "install_clean_rebuild.ps1"
HELPERS = ROOT / "scripts" / "installer_helpers.ps1"
SETUP_ENTRY = ROOT / "scripts" / "setup_entry.ps1"
SETUP = ROOT / "scripts" / "setup.ps1"
START = ROOT / "scripts" / "start.ps1"
UPDATE = ROOT / "scripts" / "update.ps1"


def _canonical_handoff_text() -> str:
    return (
        "DISCORD_BOT_TOKEN=test-discord-token\n"
        "DISCORD_GUILD_ID=123456789\n"
        "DISCORD_OWNER_USER_ID=987654321\n"
        "TRADIER_ACCESS_TOKEN=test-tradier-token\n"
        "TRADIER_ENVIRONMENT=production\n"
    )


def test_wrapper_requires_explicit_canonical_handoff_parameters() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "[string]$RepositoryPath" in text
    assert "[string]$CredentialHandoffPath" in text
    assert "[string]$CredentialHandoffSha256" in text
    assert "Read-CanonicalCredentialHandoff" in text
    assert "Install-CanonicalCredentialHandoff" in text


def test_wrapper_uses_handoff_instead_of_stale_legacy_env() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    handoff_check = text.index("Read-CanonicalCredentialHandoff")
    branch_switch = text.index("git -C $Repository switch --force-create")
    canonical_install = text.index("Install-CanonicalCredentialHandoff")
    setup_process = text.index("Invoke-SetupProcess")

    assert handoff_check < branch_switch < canonical_install < setup_process
    assert "Test-MigrationSourceCredentials -EnvPath" not in text
    assert "Original .env restored unchanged before migration" not in text


def test_wrapper_preserves_and_restores_env_by_verified_hash() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "env_sha256" in text
    assert "Get-VerifiedFileHash" in text
    assert "Restore-PreviousInstallation" in text
    assert "Restore-FileExact" in text
    assert "secret_values_written = $false" in text


def test_wrapper_receipt_proves_handoff_and_destination_identity() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    for field in (
        "requested_repository_path",
        "credential_handoff_path",
        "credential_handoff_sha256_verified",
        "canonical_names_present",
        "canonical_name_count",
        "destination_env_path",
        "source_destination_hashes_match",
    ):
        assert field in text


def test_clean_runtime_uses_isolated_virtual_environment() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (SETUP, START, UPDATE)
    )
    assert ".venv-tradysquid" in combined
    assert "Join-Path $Root '.venv\\Scripts\\python.exe'" not in combined


def test_setup_entry_guards_parse_time_failures() -> None:
    text = SETUP_ENTRY.read_text(encoding="utf-8")
    assert "Parser]::ParseFile" in text
    assert "setup-script-parse-validation" in text
    assert "setup-process-before-receipt" in text
    assert "attempt_id = $AttemptId" in text
    assert "setup_body_started = $false" in text


def test_setup_receipt_is_attempt_aware() -> None:
    text = SETUP.read_text(encoding="utf-8")
    for field in (
        "attempt_id = $AttemptId",
        "setup_commit = $SetupCommit",
        "repository_path = $Root",
        "process_id = $PID",
        "parent_process_id = $ParentProcessId",
    ):
        assert field in text
    assert "SETUP ATTEMPT" not in text
    assert "START: $Name" in text


def test_process_capture_and_wait_contract_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")
    assert "Start-Process @ProcessParameters" in text
    assert "RedirectStandardOutput" in text
    assert "RedirectStandardError" in text
    assert "WaitForExit()" in text
    assert "WaitedForExit = $true" in text
    assert "Archive-PreviousSetupArtifacts" in text
    assert "Write-SetupHeartbeat" in text
    assert "TimedOutStage" in text


def test_current_attempt_receipt_validation_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")
    assert "Read-CurrentSetupReceipt" in text
    assert "$Receipt.attempt_id -ne $AttemptId" in text
    assert "$Receipt.setup_commit -ne $ExpectedCleanCommit" in text
    assert "[datetime]$Receipt.observed_at -lt $ProcessStartedAt" in text
    assert "Current setup receipt is missing or invalid" in WRAPPER.read_text(
        encoding="utf-8"
    )


def test_failure_evidence_is_preserved_before_rollback() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    evidence = text.index("Copy-SanitizedSetupEvidence")
    rollback = text.index("Restore-PreviousInstallation", evidence)
    assert evidence < rollback
    assert "failed-setup" in HELPERS.read_text(encoding="utf-8")


def test_no_powershell_continuation_backtick_has_trailing_whitespace() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.ps1"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.rstrip("\r\n").endswith("`"):
                continue
            stripped = line.rstrip(" \t")
            if stripped.endswith("`") and stripped != line:
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == []


def test_handoff_validation_contract_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")

    assert "Credential handoff contains an unexpected name" in text
    assert "Credential handoff contains duplicate names" in text
    assert "Credential handoff contains a blank value" in text
    assert "Credential handoff is missing canonical names" in text
    assert "Credential handoff must be stored outside the repository" in text
    assert "Credential handoff SHA-256 does not match" in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell process contract is Windows-only")
def test_wrapper_helper_waits_for_real_child_exit_and_captures_streams(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    marker = tmp_path / "child-finished.txt"
    body = tmp_path / "setup.ps1"
    body.write_text(
        "param([string]$AttemptId,[string]$ExpectedCleanCommit)\n"
        "Write-Host 'body'\n",
        encoding="utf-8",
    )
    entry = tmp_path / "setup_entry.ps1"
    entry.write_text(
        "param([string]$AttemptId,[string]$ExpectedCleanCommit)\n"
        "Write-Host 'START: repository-verification'\n"
        "Start-Sleep -Seconds 2\n"
        f"'finished' | Set-Content -LiteralPath '{marker}' -Encoding UTF8\n"
        "Write-Host 'PASS: repository-verification'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    attempt_id = "11111111-1111-1111-1111-111111111111"
    commit = "a" * 40
    command = (
        f". '{HELPERS}'; "
        f"$r=Invoke-SetupProcess -SetupEntryScript '{entry}' "
        f"-SetupBodyScript '{body}' -WorkingDirectory '{tmp_path}' "
        f"-AttemptId '{attempt_id}' -ExpectedCleanCommit '{commit}'; "
        "$r | ConvertTo-Json -Compress"
    )

    started = time.monotonic()
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    elapsed = time.monotonic() - started
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])

    assert elapsed >= 1.8
    assert marker.exists()
    assert receipt["ExitCode"] == 0
    assert receipt["WaitedForExit"] is True
    assert receipt["AttemptId"] == attempt_id
    stdout = Path(receipt["StdoutPath"]).read_text(encoding="utf-8")
    assert "START: repository-verification" in stdout
    assert "PASS: repository-verification" in stdout
    assert Path(receipt["StderrPath"]).exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell parser contract is Windows-only")
def test_powershell_parse_failure_reports_line_and_column(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    broken = tmp_path / "broken.ps1"
    broken.write_text("if ($true) {\n  Write-Host 'broken'\n", encoding="utf-8")
    command = f". '{HELPERS}'; Test-PowerShellScriptSyntax -Path '{broken}'"
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "PowerShell syntax validation failed" in output
    assert '"line"' in output
    assert '"column"' in output


@pytest.mark.skipif(os.name != "nt", reason="PowerShell handoff contract is Windows-only")
def test_verified_handoff_installs_all_five_canonical_names(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = tmp_path / "canonical-credential-handoff.env"
    handoff.write_text(_canonical_handoff_text(), encoding="utf-8", newline="\n")
    destination = repository / ".env"
    expected_hash = hashlib.sha256(handoff.read_bytes()).hexdigest()

    command = (
        f". '{HELPERS}'; "
        f"$h=Read-CanonicalCredentialHandoff -RepositoryPath '{repository}' "
        f"-HandoffPath '{handoff}' -ExpectedSha256 '{expected_hash}'; "
        f"$r=Install-CanonicalCredentialHandoff -Handoff $h "
        f"-DestinationPath '{destination}'; "
        "$r | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])

    assert receipt["Status"] == "PASS"
    assert receipt["CanonicalNameCount"] == 5
    assert destination.read_text(encoding="utf-8-sig").splitlines() == (
        _canonical_handoff_text().splitlines()
    )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell handoff contract is Windows-only")
@pytest.mark.parametrize(
    "content,error_fragment",
    [
        (
            "DISCORD_BOT_TOKEN=x\n"
            "DISCORD_GUILD_ID=1\n"
            "DISCORD_OWNER_USER_ID=2\n"
            "TRADIER_ACCESS_TOKEN=y\n",
            "missing canonical names",
        ),
        (
            _canonical_handoff_text() + "TRADIER_ENVIRONMENT=production\n",
            "duplicate names",
        ),
        (
            _canonical_handoff_text().replace(
                "TRADIER_ACCESS_TOKEN=test-tradier-token",
                "TRADIER_ACCESS_TOKEN=",
            ),
            "blank value",
        ),
    ],
)
def test_invalid_canonical_handoff_fails_before_install(
    tmp_path: Path, content: str, error_fragment: str
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = tmp_path / "handoff.env"
    handoff.write_text(content, encoding="utf-8", newline="\n")
    expected_hash = hashlib.sha256(handoff.read_bytes()).hexdigest()

    command = (
        f". '{HELPERS}'; "
        f"Read-CanonicalCredentialHandoff -RepositoryPath '{repository}' "
        f"-HandoffPath '{handoff}' -ExpectedSha256 '{expected_hash}'"
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode != 0
    assert error_fragment.lower() in (completed.stdout + completed.stderr).lower()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell handoff contract is Windows-only")
def test_handoff_inside_repository_is_rejected(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = repository / "handoff.env"
    handoff.write_text(_canonical_handoff_text(), encoding="utf-8", newline="\n")
    expected_hash = hashlib.sha256(handoff.read_bytes()).hexdigest()

    command = (
        f". '{HELPERS}'; "
        f"Read-CanonicalCredentialHandoff -RepositoryPath '{repository}' "
        f"-HandoffPath '{handoff}' -ExpectedSha256 '{expected_hash}'"
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode != 0
    assert "outside the repository" in (completed.stdout + completed.stderr)


@pytest.mark.skipif(os.name != "nt", reason="PowerShell restore contract is Windows-only")
def test_wrapper_helper_restores_original_env_exactly(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    backup = tmp_path / "backup.env"
    destination = tmp_path / "app" / ".env"
    destination.parent.mkdir(parents=True)
    original = b"DISCORD_BOT_TOKEN=abc\r\nTRADIER_TOKEN=xyz\r\n"
    backup.write_bytes(original)
    destination.write_bytes(b"changed=true\n")

    command = (
        f". '{HELPERS}'; "
        f"Restore-FileExact -BackupPath '{backup}' "
        f"-DestinationPath '{destination}'"
    )
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert destination.read_bytes() == original
