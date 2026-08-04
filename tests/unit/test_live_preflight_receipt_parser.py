from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "live_preflight_receipt.ps1"
SETUP = ROOT / "scripts" / "setup.ps1"


def _run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell regression")
def test_failed_receipt_without_optional_fields_is_safe_under_strict_mode(tmp_path: Path) -> None:
    receipt_path = tmp_path / "failed-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "FAILED",
                "category": "DISCORD",
                "failed_check": "discord-guild-access",
                "error": "discord-guild-access returned HTTP 403",
                "secret_values_written": False,
            }
        ),
        encoding="utf-8",
    )

    script = f"""
Set-StrictMode -Version Latest
. '{HELPER.as_posix()}'
$Receipt = Get-Content -LiteralPath '{receipt_path.as_posix()}' -Raw | ConvertFrom-Json
$Summary = Convert-LivePreflightReceipt -Receipt $Receipt
if ($Summary.status -ne 'FAILED') {{ throw 'status was not preserved' }}
if ($Summary.tradier_live_status -ne 'NOT REPORTED') {{ throw 'missing Tradier status was not defaulted' }}
if (@($Summary.warnings).Count -ne 0) {{ throw 'missing warnings did not become an empty array' }}
if ($Summary.category -ne 'DISCORD') {{ throw 'category was not preserved' }}
if ($Summary.failed_check -ne 'discord-guild-access') {{ throw 'failed check was not preserved' }}
if ($Summary.error -ne 'discord-guild-access returned HTTP 403') {{ throw 'error was not preserved' }}
Write-Output 'PASS'
"""
    result = _run_powershell(script)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell regression")
def test_degraded_receipt_preserves_normalized_warning_under_strict_mode(tmp_path: Path) -> None:
    receipt_path = tmp_path / "degraded-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "tradier_live_status": "DEGRADED",
                "warnings": [
                    {
                        "category": "AUTHENTICATION",
                        "check": "tradier-market-clock",
                        "error": "Tradier authentication failed",
                    }
                ],
                "secret_values_written": False,
            }
        ),
        encoding="utf-8",
    )

    script = f"""
Set-StrictMode -Version Latest
. '{HELPER.as_posix()}'
$Receipt = Get-Content -LiteralPath '{receipt_path.as_posix()}' -Raw | ConvertFrom-Json
$Summary = Convert-LivePreflightReceipt -Receipt $Receipt
if ($Summary.status -ne 'PASS') {{ throw 'status was not preserved' }}
if ($Summary.tradier_live_status -ne 'DEGRADED') {{ throw 'Tradier status was not preserved' }}
if (@($Summary.warnings).Count -ne 1) {{ throw 'warning count was not preserved' }}
if ($Summary.warnings[0].check -ne 'tradier-market-clock') {{ throw 'warning check was not preserved' }}
Write-Output 'PASS'
"""
    result = _run_powershell(script)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_setup_uses_strict_mode_safe_receipt_summary() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert ". (Join-Path $PSScriptRoot 'live_preflight_receipt.ps1')" in text
    assert "Convert-LivePreflightReceipt -Receipt $LiveReceipt" in text
    assert "$LiveReceipt.tradier_live_status" not in text
    assert "$LiveReceipt.warnings" not in text
    assert "$LiveReceipt.category" not in text
    assert "$LiveReceipt.failed_check" not in text
    assert "$LiveReceipt.error" not in text
