from __future__ import annotations

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


def test_wrapper_orders_source_validation_before_migration_and_canonical_check() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    source_check = text.index("Test-MigrationSourceCredentials")
    branch_switch = text.index("git -C $Repository switch --force-create")
    migration = text.index("tradysquid.operations.credential_migration")
    canonical_check = text.index("Test-CanonicalCredentials")
    setup_process = text.index("Invoke-SetupProcess")

    assert source_check < branch_switch < migration < canonical_check < setup_process


def test_wrapper_preserves_and_restores_env_by_verified_hash() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "env_sha256" in text
    assert "Get-VerifiedFileHash" in text
    assert text.count("Restore-FileExact") >= 2
    assert "secret_values_written = $false" in text


def test_clean_runtime_uses_isolated_virtual_environment() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (SETUP, START, UPDATE)
    )
    assert ".venv-tradysquid" in combined
    assert "Join-Path $Root '.venv\\Scripts\\python.exe'" not in combined


def test_process_wait_contract_is_present() -> None:
    text = HELPERS.read_text(encoding="utf-8")
    assert "Start-Process" in text
    assert "-Wait" in text
    assert "-PassThru" in text
    assert "WaitedForExit = $true" in text


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
