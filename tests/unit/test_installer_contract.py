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
    assert "tradysquid.operations.credential_migration" not in text
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


def test_process_wait_contract_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")
    assert "ProcessStartInfo" in text
    assert "WaitForExit()" in text
    assert "UseShellExecute = $false" in text
    assert "WaitedForExit = $true" in text


def test_handoff_validation_contract_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")

    assert "Credential handoff contains an unexpected name" in text
    assert "Credential handoff contains duplicate names" in text
    assert "Credential handoff contains a blank value" in text
    assert "Credential handoff is missing canonical names" in text
    assert "Credential handoff must be stored outside the repository" in text
    assert "Credential handoff SHA-256 does not match" in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell process contract is Windows-only")
def test_wrapper_helper_waits_for_real_child_exit(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    marker = tmp_path / "child-finished.txt"
    child = tmp_path / "child.ps1"
    child.write_text(
        "$ErrorActionPreference='Stop'\n"
        "Start-Sleep -Seconds 2\n"
        f"'finished' | Set-Content -LiteralPath '{marker}' -Encoding UTF8\n"
        "exit 0\n",
        encoding="utf-8",
    )
    command = (
        f". '{HELPERS}'; "
        f"$r=Invoke-SetupProcess -SetupScript '{child}' "
        f"-WorkingDirectory '{tmp_path}'; "
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
        timeout=30,
    )
    elapsed = time.monotonic() - started
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])

    assert elapsed >= 1.8
    assert marker.exists()
    assert receipt["ExitCode"] == 0
    assert receipt["WaitedForExit"] is True


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
